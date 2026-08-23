cmake_minimum_required(VERSION 3.22.1)
project(casu-android CXX)

set(CASU_CORE_DIR "${CASU_CORE_DIR}" CACHE PATH "win-release/src/core")

add_library(casucore SHARED
    casu_jni.cpp
    ${CASU_CORE_DIR}/casu/sha256.cpp
    ${CASU_CORE_DIR}/casu/formats.cpp
    ${CASU_CORE_DIR}/casu/json.cpp
    ${CASU_CORE_DIR}/casu/manifest.cpp
    ${CASU_CORE_DIR}/casu/native.cpp
    ${CASU_CORE_DIR}/casu/native_v2.cpp
    ${CASU_CORE_DIR}/casu/native_v2_payloads.cpp
    ${CASU_CORE_DIR}/casu/mp5.cpp
    ${CASU_CORE_DIR}/casu/sidecar.cpp
    ${CASU_CORE_DIR}/casu/journal.cpp
)
target_include_directories(casucore PRIVATE ${CASU_CORE_DIR})
target_compile_features(casucore PUBLIC cxx_std_20)
find_library(log-lib log)
target_link_libraries(casucore PRIVATE z ${log-lib})
