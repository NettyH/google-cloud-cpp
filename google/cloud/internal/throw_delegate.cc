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

#include "google/cloud/internal/throw_delegate.h"
#include "google/cloud/internal/port_platform.h"
#include "google/cloud/terminate_handler.h"
#include <iostream>
#include <sstream>
#include <stdexcept>

namespace {
template <typename Exception>
[[noreturn]] void RaiseException(char const* msg) {
#ifdef GOOGLE_CLOUD_CPP_HAVE_EXCEPTIONS
  throw Exception(msg);
#else
  google::cloud::Terminate(msg);
#endif  // GOOGLE_CLOUD_CPP_HAVE_EXCEPTIONS
}

template <typename Exception>
[[noreturn]] void RaiseException(std::error_code ec, char const* msg) {
#ifdef GOOGLE_CLOUD_CPP_HAVE_EXCEPTIONS
  throw Exception(ec, msg);
#else
  std::string full_msg = ec.message();
  full_msg += ": ";
  full_msg += msg;
  google::cloud::Terminate(full_msg.c_str());
#endif  // GOOGLE_CLOUD_CPP_HAVE_EXCEPTIONS
}
}  // namespace

namespace google {
namespace cloud {
inline namespace GOOGLE_CLOUD_CPP_NS {
namespace internal {

void RaiseInvalidArgument(char const* msg) {
  RaiseException<std::invalid_argument>(msg);
}

void RaiseInvalidArgument(std::string const& msg) {
  RaiseException<std::invalid_argument>(msg.c_str());
}

void RaiseRangeError(char const* msg) { RaiseException<std::range_error>(msg); }

void RaiseRangeError(std::string const& msg) {
  RaiseException<std::range_error>(msg.c_str());
}

void RaiseRuntimeError(char const* msg) {
  RaiseException<std::runtime_error>(msg);
}

void RaiseRuntimeError(std::string const& msg) {
  RaiseException<std::runtime_error>(msg.c_str());
}

void RaiseSystemError(std::error_code ec, char const* msg) {
  RaiseException<std::system_error>(ec, msg);
}

void RaiseSystemError(std::error_code ec, std::string const& msg) {
  RaiseException<std::system_error>(ec, msg.c_str());
}

void RaiseLogicError(char const* msg) { RaiseException<std::logic_error>(msg); }

void RaiseLogicError(std::string const& msg) {
  RaiseException<std::logic_error>(msg.c_str());
}

[[noreturn]] void ThrowStatus(Status status) {
#ifdef GOOGLE_CLOUD_CPP_HAVE_EXCEPTIONS
  throw RuntimeStatusError(std::move(status));
#else
  std::ostringstream os;
  os << status;
  google::cloud::Terminate(os.str().c_str());
#endif  // GOOGLE_CLOUD_CPP_HAVE_EXCEPTIONS
}

}  // namespace internal
}  // namespace GOOGLE_CLOUD_CPP_NS
}  // namespace cloud
}  // namespace google
