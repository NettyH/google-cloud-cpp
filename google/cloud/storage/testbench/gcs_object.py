#!/usr/bin/env python
# Copyright 2018 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Implement a class to simulate GCS objects."""


import base64
import error_response
import hashlib
import json
import testbench_utils
import time


class GcsObjectVersion(object):
    """Represent a single revision of a GCS Object."""

    def __init__(self, gcs_url, bucket_name, name, generation, request, media):
        """Initialize a new object revision.

        :param gcs_url:str the base URL for the GCS service.
        :param bucket_name:str the name of the bucket that contains the object.
        :param name:str the name of the object.
        :param generation:int the generation number for this object.
        :param request:flask.Request the contents of the HTTP request.
        :param media:str the contents of the object.
        """
        self.gcs_url = gcs_url
        self.bucket_name = bucket_name
        self.name = name
        self.generation = generation
        self.object_id = bucket_name + '/o/' + name + '/' + str(generation)
        now = time.gmtime(time.time())
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', now)
        self.media = media
        instructions = request.headers.get('x-goog-testbench-instructions')
        if instructions == 'inject-upload-data-error':
            self.media = testbench_utils.corrupt_media(media)

        self.metadata = {
            'timeCreated': timestamp,
            'updated': timestamp,
            'metageneration': 0,
            'generation': generation,
            'location': 'US',
            'storageClass': 'STANDARD',
            'size': len(self.media),
            'etag': 'XYZ=',
            'owner': {
                'entity': 'project-owners-123456789',
                'entityId': '',
            },
            'md5Hash': base64.b64encode(hashlib.md5(self.media).digest()),
        }
        if request.headers.get('content-type') is not None:
            self.metadata['contentType'] = request.headers.get('content-type')
        # Update the derived metadata attributes (e.g.: id, kind, selfLink)
        self.update_from_metadata({})
        # Capture any encryption key headers.
        self._capture_customer_encryption(request)
        self._update_predefined_acl(request.args.get('predefinedAcl'))
        acl2json_mapping = {
            'authenticated-read': 'authenticatedRead',
            'bucket-owner-full-control': 'bucketOwnerFullControl',
            'bucket-owner-read': 'bucketOwnerRead',
            'private': 'private',
            'project-private': 'projectPrivate',
            'public-read': 'publicRead',
        }
        if request.headers.get('x-goog-acl') is not None:
            acl = request.headers.get('x-goog-acl')
            predefined = acl2json_mapping.get(acl)
            if predefined is not None:
                self._update_predefined_acl(predefined)
            else:
                raise error_response.ErrorResponse(
                    'Invalid predefinedAcl value %s' % acl, status_code=400)

    def update_from_metadata(self, metadata):
        """Update from a metadata dictionary.

        :param metadata:dict a dictionary with new metadata values.
        :rtype:NoneType
        """
        tmp = self.metadata.copy()
        tmp.update(metadata)
        tmp['bucket'] = tmp.get('bucket', self.name)
        tmp['name'] = tmp.get('name', self.name)
        now = time.gmtime(time.time())
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', now)
        # Some values cannot be changed via updates, so we always reset them.
        tmp.update({
            'kind': 'storage#object',
            'bucket': self.bucket_name,
            'name': self.name,
            'id': self.object_id,
            'selfLink': self.gcs_url + self.name,
            'projectNumber': '123456789',
            'updated': timestamp,
        })
        tmp['metageneration'] = tmp.get('metageneration', 0) + 1
        self.metadata = tmp
        self._validate_hashes()

    def _validate_hashes(self):
        """Validate the md5Hash field against the stored media."""
        actual = self.metadata.get('md5Hash', '')
        expected = base64.b64encode(hashlib.md5(self.media).digest())
        if actual != expected:
            raise error_response.ErrorResponse(
                'Mismatched MD5 hash expected=%s, actual=%s' % (expected,
                                                                actual))

    def validate_encryption_for_read(self, request,
                                     prefix='x-goog-encryption'):
        """Verify that the request includes the correct encryption keys.

        :param request:flask.Request the http request.
        :param prefix: str the prefix shared by the encryption headers,
            typically 'x-goog-encryption', but for rewrite requests it can be
            'x-good-copy-source-encryption'.
        :rtype:NoneType
        """
        key_header = prefix + '-key'
        hash_header = prefix + '-key-sha256'
        algo_header = prefix + '-algorithm'
        encryption = self.metadata.get('customerEncryption')
        if encryption is None:
            # The object is not encrypted, no key is needed.
            if request.headers.get(key_header) is None:
                return
            else:
                # The data is not encrypted, sending an encryption key is an
                # error.
                testbench_utils.raise_csek_error()
        # The data is encrypted, the key must be present, match, and match its
        # hash.
        key_header_value = request.headers.get(key_header)
        hash_header_value = request.headers.get(hash_header)
        algo_header_value = request.headers.get(algo_header)
        testbench_utils.validate_customer_encryption_headers(
            key_header_value, hash_header_value, algo_header_value)
        if encryption.get('keySha256') != hash_header_value:
            testbench_utils.raise_csek_error()

    def _capture_customer_encryption(self, request):
        """Capture the customer-supplied encryption key, if any.

        :param request:flask.Request the http request.
        :rtype:NoneType
        """
        if request.headers.get('x-goog-encryption-key') is None:
            return
        prefix = 'x-goog-encryption'
        key_header = prefix + '-key'
        hash_header = prefix + '-key-sha256'
        algo_header = prefix + '-algorithm'
        key_header_value = request.headers.get(key_header)
        hash_header_value = request.headers.get(hash_header)
        algo_header_value = request.headers.get(algo_header)
        testbench_utils.validate_customer_encryption_headers(
            key_header_value, hash_header_value, algo_header_value)
        self.metadata['customerEncryption'] = {
            "encryptionAlgorithm": algo_header_value,
            "keySha256": hash_header_value,
        }

    def _update_predefined_acl(self, predefined_acl):
        """Update the ACL based on the given request parameter value."""
        if predefined_acl is None:
            predefined_acl = 'projectPrivate'
        self.insert_acl(
            testbench_utils.canonical_entity_name('project-owners-123456789'), 'OWNER')
        bucket = testbench_utils.lookup_bucket(self.bucket_name)
        owner = bucket.metadata.get('owner')
        if owner is None:
            owner_entity = 'project-owners-123456789'
        else:
            owner_entity = owner.get('entity')
        if predefined_acl == 'authenticatedRead':
            self.insert_acl('allAuthenticatedUsers', 'READER')
        elif predefined_acl == 'bucketOwnerFullControl':
            self.insert_acl(owner_entity, 'OWNER')
        elif predefined_acl == 'bucketOwnerRead':
            self.insert_acl(owner_entity, 'READER')
        elif predefined_acl == 'private':
            self.insert_acl('project-owners', 'OWNER')
        elif predefined_acl == 'projectPrivate':
            self.insert_acl(
                testbench_utils.canonical_entity_name('project-editors-123456789'), 'OWNER')
            self.insert_acl(
                testbench_utils.canonical_entity_name('project-viewers-123456789'), 'READER')
        elif predefined_acl == 'publicRead':
            self.insert_acl(
                testbench_utils.canonical_entity_name('allUsers'), 'READER')
        else:
            raise error_response.ErrorResponse(
                'Invalid predefinedAcl value', status_code=400)

    def reset_predefined_acl(self, predefined_acl):
        """Reset the ACL based on the given request parameter value."""
        self.metadata['acl'] = []
        self._update_predefined_acl(predefined_acl)

    def insert_acl(self, entity, role):
        """Insert (or update) a new AccessControl entry for this object.

        :param entity:str the name of the entity to insert.
        :param role:str the new role
        :return: the dictionary representing the new AccessControl metadata.
        :rtype:dict
        """
        entity = testbench_utils.canonical_entity_name(entity)
        email = ''
        if entity.startswith('user-'):
            email = entity
        # Replace or insert the entry.
        indexed = testbench_utils.index_acl(self.metadata.get('acl', []))
        indexed[entity] = {
            'bucket': self.bucket_name,
            'email': email,
            'entity': entity,
            'entity_id': '',
            'etag': self.metadata.get('etag', 'XYZ='),
            'generation': self.generation,
            'id': self.metadata.get('id', '') + '/' + entity,
            'kind': 'storage#objectAccessControl',
            'object': self.name,
            'role': role,
            'selfLink': self.metadata.get('selfLink') + '/acl/' + entity
        }
        self.metadata['acl'] = indexed.values()
        return indexed[entity]

    def delete_acl(self, entity):
        """Delete a single AccessControl entry from the Object revision.

        :param entity:str the name of the entity.
        :rtype:NoneType
        """
        entity = testbench_utils.canonical_entity_name(entity)
        indexed = testbench_utils.index_acl(self.metadata.get('acl', []))
        indexed.pop(entity)
        self.metadata['acl'] = indexed.values()

    def get_acl(self, entity):
        """Get a single AccessControl entry from the Object revision.

        :param entity:str the name of the entity.
        :return: with the contents of the ObjectAccessControl.
        :rtype:dict
        """
        entity = testbench_utils.canonical_entity_name(entity)
        for acl in self.metadata.get('acl', []):
            if acl.get('entity', '') == entity:
                return acl
        raise error_response.ErrorResponse(
            'Entity %s not found in object %s' % (entity, self.name))

    def update_acl(self, entity, role):
        """Update a single AccessControl entry in this Object revision.

        :param entity:str the name of the entity.
        :param role:str the new role for the entity.
        :return: with the contents of the ObjectAccessControl.
        :rtype: dict
        """
        return self.insert_acl(entity, role)

    def patch_acl(self, entity, request):
        """Patch a single AccessControl entry in this Object revision.

        :param entity:str the name of the entity.
        :param request:flask.Request the parameters for this request.
        :return: with the contents of the ObjectAccessControl.
        :rtype: dict
        """
        acl = self.get_acl(entity)
        payload = json.loads(request.data)
        request_entity = payload.get('entity')
        if request_entity is not None and request_entity != entity:
            raise error_response.ErrorResponse(
                'Entity mismatch in ObjectAccessControls: patch, expected=%s, got=%s'
                % (entity, request_entity))
        etag_match = request.headers.get('if-match')
        if etag_match is not None and etag_match != acl.get('etag'):
            raise error_response.ErrorResponse(
                'Precondition Failed', status_code=412)
        etag_none_match = request.headers.get('if-none-match')
        if (etag_none_match is not None
                and etag_none_match != acl.get('etag')):
            raise error_response.ErrorResponse(
                'Precondition Failed', status_code=412)
        role = payload.get('role')
        if role is None:
            raise error_response.ErrorResponse('Missing role value')
        return self.insert_acl(entity, role)


class GcsObject(object):
    """Represent a GCS Object, including all its revisions."""

    def __init__(self, bucket_name, name):
        """Initialize a fake GCS Blob.

        :param bucket_name:str the bucket that will contain the new object.
        :param name:str the name of the new object.
        """
        self.bucket_name = bucket_name
        self.name = name
        # Define the current generation for the object, will use this as a
        # simple counter to increment on each object change.
        self.generation = 0
        self.revisions = {}
        self.rewrite_token_generator = 0
        self.rewrite_operations = {}

    def get_revision(self, request, version_field_name='generation'):
        """Get the information about a particular object revision or raise.

        :param request:flask.Request the contents of the http request.
        :param version_field_name:str the name of the generation
            parameter, typically 'generation', but sometimes 'sourceGeneration'.
        :return: the object revision.
        :rtype: GcsObjectVersion
        :raises:ErrorResponse if the request contains an invalid generation
            number.
        """
        generation = request.args.get(version_field_name)
        if generation is None:
            return self.get_latest()
        version = self.revisions.get(int(generation))
        if version is None:
            raise error_response.ErrorResponse(
                'Precondition Failed: generation %s not found' % generation)
        return version

    def del_revision(self, request):
        """Delete a version of a fake GCS Blob.

        :param request:flask.Request the contents of the HTTP request.
        :return: True if the object entry in the Bucket should be deleted.
        :rtype: bool
        """
        generation = request.args.get('generation')
        if generation is None:
            generation = self.generation
        self.revisions.pop(int(generation))
        if len(self.revisions) == 0:
            self.generation = None
            return True
        if generation == self.generation:
            self.generation = sorted(self.revisions.keys())[-1]
        return False

    def update_revision(self, request):
        """Update the metadata of particular object revision or raise.

        :param request:flask.Request
        :return: the object revision updated revision.
        :rtype: GcsObjectVersion
        :raises:ErrorResponse if the request contains an invalid generation
            number.
        """
        generation = request.args.get('generation')
        if generation is None:
            version = self.get_latest()
        else:
            version = self.revisions.get(int(generation))
            if version is None:
                raise error_response.ErrorResponse(
                    'Precondition Failed: generation %s not found' %
                    generation)
        metadata = json.loads(request.data)
        version.update_from_metadata(metadata)
        return version

    def patch_revision(self, request):
        """Patch the metadata of particular object revision or raise.

        :param request:flask.Request
        :return: the object revision.
        :rtype:GcsObjectRevision
        :raises:ErrorResponse if the request contains an invalid generation
            number.
        """
        generation = request.args.get('generation')
        if generation is None:
            version = self.get_latest()
        else:
            version = self.revisions.get(int(generation))
            if version is None:
                raise error_response.ErrorResponse(
                    'Precondition Failed: generation %s not found' %
                    generation)
        patch = json.loads(request.data)
        writeable_keys = {
            'acl', 'cacheControl', 'contentDisposition', 'contentEncoding',
            'contentLanguage', 'contentType', 'metadata'
        }
        for key, value in patch.iteritems():
            if key not in writeable_keys:
                raise error_response.ErrorResponse(
                    'Invalid metadata change. %s is not writeable' % key,
                    status_code=503)
        patched = testbench_utils.json_api_patch(
            version.metadata, patch, recurse_on={'metadata'})
        patched['metageneration'] = patched.get('metageneration', 0) + 1
        version.metadata = patched
        return version

    def get_revision_by_generation(self, generation):
        """Get object revision by generation or None if not found.

        :param generation:int
        :return: the object revision by generation or None.
        :rtype:GcsObjectRevision
        """
        return self.revisions.get(generation, None)

    def get_latest(self):
        return self.revisions.get(self.generation, None)

    def check_preconditions_by_value(
            self, generation_match, generation_not_match, metageneration_match,
            metageneration_not_match):
        """Verify that the given precondition values are met."""
        if (generation_match is not None
                and int(generation_match) != self.generation):
            raise error_response.ErrorResponse(
                'Precondition Failed', status_code=412)
        # This object does not exist (yet), testing in this case is special.
        if (generation_not_match is not None
                and int(generation_not_match) == self.generation):
            raise error_response.ErrorResponse(
                'Precondition Failed', status_code=412)

        if self.generation == 0:
            if (metageneration_match is not None
                    or metageneration_not_match is not None):
                raise error_response.ErrorResponse(
                    'Precondition Failed', status_code=412)
        else:
            current = self.revisions.get(self.generation)
            if current is None:
                raise error_response.ErrorResponse(
                    'Object not found', status_code=404)
            metageneration = current.metadata.get('metageneration')
            if (metageneration_not_match is not None
                    and int(metageneration_not_match) == metageneration):
                raise error_response.ErrorResponse(
                    'Precondition Failed', status_code=412)
            if (metageneration_match is not None
                    and int(metageneration_match) != metageneration):
                raise error_response.ErrorResponse(
                    'Precondition Failed', status_code=412)

    def check_preconditions(
            self,
            request,
            if_generation_match='ifGenerationMatch',
            if_generation_not_match='ifGenerationNotMatch',
            if_metageneration_match='ifMetagenerationMatch',
            if_metageneration_not_match='ifMetagenerationNotMatch'):
        """Verify that the preconditions in request are met.

        :param request:flask.Request the http request.
        :param if_generation_match:str the name of the generation match
            parameter name, typically 'ifGenerationMatch', but sometimes
            'ifSourceGenerationMatch'.
        :param if_generation_not_match:str the name of the generation not-match
            parameter name, typically 'ifGenerationNotMatch', but sometimes
            'ifSourceGenerationNotMatch'.
        :param if_metageneration_match:str the name of the metageneration match
            parameter name, typically 'ifMetagenerationMatch', but sometimes
            'ifSourceMetagenerationMatch'.
        :param if_metageneration_not_match:str the name of the metageneration
            not-match parameter name, typically 'ifMetagenerationNotMatch', but
            sometimes 'ifSourceMetagenerationNotMatch'.
        :rtype:NoneType
        """
        generation_match = request.args.get(if_generation_match)
        generation_not_match = request.args.get(if_generation_not_match)
        metageneration_match = request.args.get(if_metageneration_match)
        metageneration_not_match = request.args.get(
            if_metageneration_not_match)
        self.check_preconditions_by_value(
            generation_match, generation_not_match, metageneration_match,
            metageneration_not_match)

    def _insert_revision(self, revision):
        """Insert a new revision that has been initialized and checked.

        :param revision: GcsObjectVersion the new revision to insert.
        :rtype:NoneType
        """
        update = {self.generation: revision}
        bucket = testbench_utils.lookup_bucket(self.bucket_name)
        if not bucket.versioning_enabled():
            self.revisions = update
        else:
            self.revisions.update(update)

    def insert(self, gcs_url, request):
        """Insert a new revision based on the give flask request.

        :param gcs_url:str the root URL for the fake GCS service.
        :param request:flask.Request the contents of the HTTP request.
        :return: the newly created object version.
        :rtype: GcsObjectVersion
        """
        media = testbench_utils.extract_media(request)
        self.generation += 1
        revision = GcsObjectVersion(
            gcs_url, self.bucket_name, self.name, self.generation, request,
            media)
        meta = revision.metadata.setdefault('metadata', {})
        meta['x_testbench_upload'] = 'simple'
        self._insert_revision(revision)
        return revision

    def _parse_part(self, multipart_upload_part):
        """Parse a portion of a multipart breaking out the headers and payload.

        :param multipart_upload_part:str a portion of the multipart upload body.
        :return: a tuple with the headers and the payload.
        :rtype: (dict, str)
        """
        headers = dict()
        index = 0
        next_line = multipart_upload_part.find('\r\n', index)
        while next_line != index:
            header_line = multipart_upload_part[index:next_line]
            key, value = header_line.split(': ', 2)
            # This does not work for repeated headers, but we do not expect
            # those in the testbench.
            headers[key.encode('ascii', 'ignore')] = value
            index = next_line + 2
            next_line = multipart_upload_part.find('\r\n', index)
        return headers, multipart_upload_part[next_line + 2:]

    def insert_multipart(self, gcs_url, request):
        """Insert a new revision based on the give flask request.

        :param gcs_url:str the root URL for the fake GCS service.
        :param request:flask.Request the contents of the HTTP request.
        :return: the newly created object version.
        :rtype: GcsObjectVersion
        """
        content_type = request.headers.get('content-type')
        if content_type is None or not content_type.startswith(
                'multipart/related'):
            raise error_response.ErrorResponse(
                'Missing or invalid content-type header in multipart upload')
        _, _, boundary = content_type.partition('boundary=')
        if boundary is None:
            raise error_response.ErrorResponse(
                'Missing boundary (%s) in content-type header in multipart upload'
                % boundary)

        marker = '--' + boundary + '\r\n'
        body = testbench_utils.extract_media(request)
        parts = body.split(marker)
        # parts[0] is the empty string, `multipart` should start with the boundary
        # parts[1] is the JSON resource object part, with some headers
        resource_headers, resource_body = self._parse_part(parts[1])
        # parts[2] is the media, with some headers
        media_headers, media_body = self._parse_part(parts[2])
        end = media_body.find('\r\n--' + boundary + '--\r\n')
        if end == -1:
            raise error_response.ErrorResponse(
                'Missing end marker (--%s--) in media body' % boundary)
        media_body = media_body[:end]
        self.generation += 1
        revision = GcsObjectVersion(
            gcs_url, self.bucket_name, self.name, self.generation, request,
            media_body)
        resource = json.loads(resource_body)
        meta = revision.metadata.setdefault('metadata', {})
        meta['x_testbench_upload'] = 'multipart'
        meta['x_testbench_md5'] = resource.get('md5Hash', '')
        # Apply any overrides from the resource object part.
        revision.update_from_metadata(resource)
        # The content-type needs to be patched up, yuck.
        if media_headers.get('content-type') is not None:
            revision.update_from_metadata({
                'contentType':
                    media_headers.get('content-type')
            })
        self._insert_revision(revision)
        return revision

    def insert_xml(self, gcs_url, request):
        """Implement the insert operation using the XML API.

        :param gcs_url:str the root URL for the fake GCS service.
        :param request:flask.Request the contents of the HTTP request.
        :return: the newly created object version.
        :rtype: GcsObjectVersion
        """
        media = testbench_utils.extract_media(request)
        self.generation += 1
        goog_hash = request.headers.get('x-goog-hash')
        md5hash = None
        if goog_hash is not None:
            for hash in goog_hash.split(','):
                if hash.startswith('md5='):
                    md5hash = hash[4:]
        revision = GcsObjectVersion(
            gcs_url, self.bucket_name, self.name, self.generation, request,
            media)
        meta = revision.metadata.setdefault('metadata', {})
        meta['x_testbench_upload'] = 'xml'
        if md5hash is not None:
            meta['x_testbench_md5'] = md5hash
            revision.update_from_metadata({
                'md5Hash': md5hash,
            })
        self._insert_revision(revision)
        return revision

    def copy_from(self, gcs_url, request, source_revision):
        """Insert a new revision based on the give flask request.

        :param gcs_url:str the root URL for the fake GCS service.
        :param request:flask.Request the contents of the HTTP request.
        :param source_revision:GcsObjectVersion the source object version to
            copy from.
        :return: the newly created object version.
        :rtype: GcsObjectVersion
        """
        self.generation += 1
        source_revision.validate_encryption_for_read(request)
        revision = GcsObjectVersion(
            gcs_url, self.bucket_name, self.name, self.generation, request,
            source_revision.media)
        revision.reset_predefined_acl(
            request.args.get('destinationPredefinedAcl'))
        metadata = json.loads(request.data)
        revision.update_from_metadata(metadata)
        self._insert_revision(revision)
        return revision

    def compose_from(self, gcs_url, request, composed_media):
        """Compose a new revision based on the give flask request.

        :param gcs_url:str the root URL for the fake GCS service.
        :param request:flask.Request the contents of the HTTP request.
        :param composed_media:str contents of the composed object
        :return: the newly created object version.
        :rtype: GcsObjectVersion
        """
        self.generation += 1
        revision = GcsObjectVersion(
            gcs_url, self.bucket_name, self.name, self.generation, request,
            composed_media)
        revision.reset_predefined_acl(
            request.args.get('destinationPredefinedAcl'))
        payload = json.loads(request.data)
        if payload.get('destination') is not None:
            revision.update_from_metadata(payload.get('destination'))
        self._insert_revision(revision)
        return revision

    @classmethod
    def rewrite_fixed_args(cls):
        """The arguments that should not change between requests for the same
        rewrite operation."""
        return [
            'destinationKmsKeyName', 'destinationPredefinedAcl',
            'ifGenerationMatch', 'ifGenerationNotMatch',
            'ifMetagenerationMatch', 'ifMetagenerationNotMatch',
            'ifSourceGenerationMatch', 'ifSourceGenerationNotMatch',
            'ifSourceMetagenerationMatch', 'ifSourceMetagenerationNotMatch',
            'maxBytesRewrittenPerCall', 'projection', 'sourceGeneration',
            'userProject'
        ]

    @classmethod
    def capture_rewrite_operation_arguments(cls, request, destination_bucket,
                                            destination_object):
        """Captures the arguments used to validate related rewrite calls.

        :rtype:dict
        """
        original_arguments = {}
        for arg in GcsObject.rewrite_fixed_args():
            original_arguments[arg] = request.args.get(arg)
        original_arguments.update({
            'destination_bucket': destination_bucket,
            'destination_object': destination_object,
        })
        return original_arguments

    @classmethod
    def make_rewrite_token(cls, operation, destination_bucket,
                           destination_object, generation):
        """Create a new rewrite token for the given operation."""
        return base64.b64encode('/'.join([
            str(operation.get('id')),
            destination_bucket,
            destination_object,
            str(generation),
            str(operation.get('bytes_rewritten')),
        ]))

    def make_rewrite_operation(self, request, destination_bucket,
                               destination_object):
        """Create a new rewrite token for `Objects: rewrite`."""
        generation = request.args.get('sourceGeneration')
        if generation is None:
            generation = self.generation
        else:
            generation = int(generation)

        self.rewrite_token_generator = self.rewrite_token_generator + 1
        body = json.loads(request.data)
        original_arguments = self.capture_rewrite_operation_arguments(
            request, destination_object, destination_object)
        operation = {
            'id': self.rewrite_token_generator,
            'original_arguments': original_arguments,
            'actual_generation': generation,
            'bytes_rewritten': 0,
            'body': body,
        }
        token = GcsObject.make_rewrite_token(operation, destination_bucket,
                                             destination_object, generation)
        return token, operation

    def rewrite_finish(self, gcs_url, request, body, source):
        """Complete a rewrite from `source` into this object.

        :param gcs_url:str the root URL for the fake GCS service.
        :param request:flask.Request the contents of the HTTP request.
        :param body:dict the HTTP payload, parsed via json.loads()
        :param source:GcsObjectVersion the source object version.
        :return: the newly created object version.
        :rtype: GcsObjectVersion
        """
        media = source.media
        self.check_preconditions(request)
        self.generation += 1
        revision = GcsObjectVersion(
            gcs_url, self.bucket_name, self.name, self.generation, request,
            media)
        revision.update_from_metadata(body)
        self._insert_revision(revision)
        return revision

    def rewrite_step(self, gcs_url, request, destination_bucket,
                     destination_object):
        """Execute an iteration of `Objects: rewrite.

        Objects: rewrite may need to be called multiple times before it
        succeeds. Only objects in the same location, with the same encryption,
        are guaranteed to complete in a single request.

        The implementation simulates some, but not all, the behaviors of the
        server, in particular, only rewrites within the same bucket and smaller
        than 1MiB complete immediately.

        :param gcs_url:str the root URL for the fake GCS service.
        :param request:flask.Request the contents of the HTTP request.
        :param destination_bucket:str where will the object be placed after the
            rewrite operation completes.
        :param destination_object:str the name of the object when the rewrite
            operation completes.
        :return: a dictionary prepared for JSON encoding of a
            `Objects: rewrite` response.
        :rtype:dict
        """
        body = json.loads(request.data)
        rewrite_token = request.args.get('rewriteToken')
        if rewrite_token is not None and rewrite_token != '':
            # Note that we remove the rewrite operation, not just look it up.
            # That way if the operation completes in this call, and/or fails,
            # it is already removed. We need to insert it with a new token
            # anyway, so this makes sense.
            rewrite = self.rewrite_operations.pop(rewrite_token, None)
            if rewrite is None:
                raise error_response.ErrorResponse(
                    'Invalid or expired token in rewrite', status_code=410)
        else:
            rewrite_token, rewrite = self.make_rewrite_operation(
                request, destination_bucket, destination_bucket)

        # Compare the difference to the original arguments, on the first call
        # this is a waste, but the code is easier to follow.
        current_arguments = self.capture_rewrite_operation_arguments(
            request, destination_bucket, destination_object)
        diff = set(current_arguments) ^ set(rewrite.get('original_arguments'))
        if len(diff) != 0:
            raise error_response.ErrorResponse(
                'Mismatched arguments to rewrite', status_code=412)

        # This will raise if the version is deleted while the operation is in
        # progress.
        source = self.get_revision_by_generation(
            rewrite.get('actual_generation'))
        source.validate_encryption_for_read(
            request, prefix='x-goog-copy-source-encryption')
        bytes_rewritten = rewrite.get('bytes_rewritten')
        bytes_rewritten += (1024 * 1024)
        result = {
            'kind': 'storage#rewriteResponse',
            'objectSize': len(source.media),
        }
        if bytes_rewritten >= len(source.media):
            bytes_rewritten = len(source.media)
            rewrite['bytes_rewritten'] = bytes_rewritten
            # Success, the operation completed. Return the new object:
            object_path, destination = testbench_utils.get_object(
                destination_bucket, destination_object,
                GcsObject(destination_bucket, destination_object))
            revision = destination.rewrite_finish(gcs_url, request, body,
                                                  source)
            testbench_utils.insert_object(object_path, destination)
            result['done'] = True
            result['resource'] = revision.metadata
            rewrite_token = ''
        else:
            rewrite['bytes_rewritten'] = bytes_rewritten
            rewrite_token = GcsObject.make_rewrite_token(
                rewrite, destination_bucket, destination_object,
                source.generation)
            self.rewrite_operations[rewrite_token] = rewrite
            result['done'] = False

        result.update({
            'totalBytesRewritten': bytes_rewritten,
            'rewriteToken': rewrite_token,
        })
        return result