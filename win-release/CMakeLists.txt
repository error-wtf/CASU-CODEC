cmake_minimum_required(VERSION 3.20)
project(casu_codec_windows LANGUAGES CXX)
enable_testing()

# Cross toolchain for Windows x86_64.
#   cmake -S . -B build-win64 -G Ninja \
#     -DCMAKE_TOOLCHAIN_FILE=cmake/mingw64-toolchain.cmake \
#     -DCMAKE_BUILD_TYPE=Release
#   cmake --build build-win64

if(NOT WIN32)
  # Guard: only meaningful as a cross build to Windows via the toolchain file.
  message(FATAL_ERROR "This tree must be built for Windows using cmake/mingw64-toolchain.cmake")
endif()

# STEP-002: bundled runtime dependencies (Qt6-MinGW, libVLC, helpers) and the
# self-contained CPack zip layout.
include(cmake/dependencies.cmake)

# Shared libraries (added step-by-step during the port; each own CMakeLists)
add_subdirectory(src/core)          # casu_core
add_subdirectory(src/codec)         # casu_codec  (Phase B2)
add_subdirectory(src/media)         # casu_media  (Phase B2)
add_subdirectory(src/playback)      # casu_playback (M-PCASU-3)
add_subdirectory(src/network)       # casu_network (Phase B3)
add_subdirectory(src/webapi)        # casu_webapi  (Phase B5)

# STEP-001 gate: Hello-Windows EXE (builds PE32+, runs under Wine)
add_subdirectory(src/hello)         # casu_hello

# Phase B/C tests (cross-compiled; run under Wine)
add_subdirectory(tests)             # casu_core_test, ...

# Apps (Phase C)
add_subdirectory(apps/casu-cli)     # casu_cli
add_subdirectory(apps/mpcasu)       # MPCASU.exe
add_subdirectory(apps/converter)    # CASU-Converter.exe (Qt GUI)
add_subdirectory(apps/web-backend)  # CASU-Web-Backend

# STEP-002: CPack packaging rules (included last so all install() rules from
# app targets are registered first).
include(cmake/packaging.cmake)
