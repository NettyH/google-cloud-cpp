// Copyright 2018 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include "google/cloud/storage/object_access_control.h"
#include <gmock/gmock.h>

namespace google {
namespace cloud {
namespace storage {
inline namespace STORAGE_CLIENT_NS {
namespace {

/// @test Verify that we parse JSON objects into ObjectAccessControl objects.
TEST(ObjectAccessControlTest, Parse) {
  std::string text = R"""({
      "bucket": "foo-bar",
      "domain": "example.com",
      "email": "foobar@example.com",
      "entity": "user-foobar",
      "entityId": "user-foobar-id-123",
      "etag": "XYZ=",
      "generation": 42,
      "id": "object-foo-bar-baz-acl-234",
      "kind": "storage#objectAccessControl",
      "object": "baz",
      "projectTeam": {
        "projectNumber": "3456789",
        "team": "a-team"
      },
      "role": "OWNER"
})""";
  auto actual = ObjectAccessControl::ParseFromString(text).value();

  EXPECT_EQ("foo-bar", actual.bucket());
  EXPECT_EQ("example.com", actual.domain());
  EXPECT_EQ("foobar@example.com", actual.email());
  EXPECT_EQ("user-foobar", actual.entity());
  EXPECT_EQ("user-foobar-id-123", actual.entity_id());
  EXPECT_EQ("XYZ=", actual.etag());
  EXPECT_EQ(42, actual.generation());
  EXPECT_EQ("object-foo-bar-baz-acl-234", actual.id());
  EXPECT_EQ("storage#objectAccessControl", actual.kind());
  EXPECT_EQ("baz", actual.object());
  EXPECT_EQ("3456789", actual.project_team().project_number);
  EXPECT_EQ("a-team", actual.project_team().team);
  EXPECT_EQ("OWNER", actual.role());
}

/// @test Verify that the IOStream operator works as expected.
TEST(ObjectAccessControlTest, IOStream) {
  // The iostream operator is mostly there to support EXPECT_EQ() so it is
  // rarely called, and that breaks our code coverage metrics.
  std::string text = R"""({
      "bucket": "foo-bar",
      "domain": "example.com",
      "email": "foobar@example.com",
      "entity": "user-foobar",
      "entityId": "user-foobar-id-123",
      "etag": "XYZ=",
      "generation": 42,
      "id": "object-foo-bar-baz-acl-234",
      "kind": "storage#objectAccessControl",
      "object": "baz",
      "projectTeam": {
        "projectNumber": "3456789",
        "team": "a-team"
      },
      "role": "OWNER"
})""";

  auto meta = ObjectAccessControl::ParseFromString(text).value();
  std::ostringstream os;
  os << meta;
  auto actual = os.str();
  using ::testing::HasSubstr;
  EXPECT_THAT(actual, HasSubstr("ObjectAccessControl"));
  EXPECT_THAT(actual, HasSubstr("bucket=foo-bar"));
  EXPECT_THAT(actual, HasSubstr("object=baz"));
  EXPECT_THAT(actual, HasSubstr("id=object-foo-bar-baz-acl-234"));
}

/// @test Verify ObjectAccessControl::set_entity() works as expected.
TEST(ObjectAccessControlTest, SetEntity) {
  ObjectAccessControl tested;

  EXPECT_TRUE(tested.entity().empty());
  tested.set_entity("user-foo");
  EXPECT_EQ("user-foo", tested.entity());
}

/// @test Verify ObjectAccessControl::set_role() works as expected.
TEST(ObjectAccessControlTest, SetRole) {
  ObjectAccessControl tested;

  EXPECT_TRUE(tested.role().empty());
  tested.set_role(ObjectAccessControl::ROLE_READER());
  EXPECT_EQ("READER", tested.role());
}

/// @test Verify that comparison operators work as expected.
TEST(ObjectAccessControlTest, Compare) {
  std::string text = R"""({
      "bucket": "foo-bar",
      "domain": "example.com",
      "email": "foobar@example.com",
      "entity": "user-foobar",
      "entityId": "user-foobar-id-123",
      "etag": "XYZ=",
      "generation": 42,
      "id": "object-foo-bar-baz-acl-234",
      "kind": "storage#objectAccessControl",
      "object": "baz",
      "projectTeam": {
        "projectNumber": "3456789",
        "team": "a-team"
      },
      "role": "OWNER"
})""";
  auto original = ObjectAccessControl::ParseFromString(text).value();
  EXPECT_EQ(original, original);

  auto modified = original;
  modified.set_role(ObjectAccessControl::ROLE_READER());
  EXPECT_NE(original, modified);
}

}  // namespace
}  // namespace STORAGE_CLIENT_NS
}  // namespace storage
}  // namespace cloud
}  // namespace google
