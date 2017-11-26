#!/bin/sh
# Copyright 2017 Google Inc.
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

set -e

if [ "${TRAVIS_OS_NAME}" != "osx" ]; then
  echo "Not a Mac OS X build, exit successfully"
  exit 0
fi

# On my local workstation I prefer to keep all the build artifacts in
# a sub-directory, not so important for Travis builds, but that makes
# this script easier to test.
test -d .build || mkdir .build

cd .build
cmake ..
make -j ${NCPU:-2}
make -j ${NCPU:-2} test || ( cat Testing/Temporary/LastTest.log; exit 1 )
