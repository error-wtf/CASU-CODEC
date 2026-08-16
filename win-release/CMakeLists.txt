cmake_minimum_required(VERSION 3.20)
project(casu_codec_windows LANGUAGES CXX)

# Cross toolchain for Windows x86_64.
#   cmake -S . -B build-win64 -G Ninja \
#     -DCMAKE_TOOLCHAIN_FILE=cmake/mingw64-toolchain.cmake \
#     -DCMAKE_BUILD_TYPE=Release
#   cmake --build build-win64

if(NOT WIN32)
  # Guard: only meaningful as a cross build to Windows via the toolchain file.
  message(FATAL_ERROR "This tree must be built for Windows using cmake/mingw64-toolchain.cmake")
endif()

# Shared libraries (added step-by-step during the port; each own CMakeLists)
add_subdirectory(src/core)          # casu_core
# add_subdirectory(src/codec)       # casu_codec   (Phase B)
# add_subdirectory(src/media)       # casu_media
# add_subdirectory(src/network)     # casu_network
# add_subdirectory(src/playback)    # casu_playback
# add_subdirectory(src/webapi)      # casu_webapi

# Apps (Phase C)
# add_subdirectory(apps/mpcasu)
# add_subdirectory(apps/converter)
# add_subdirectory(apps/web-backend)
# add_subdirectory(apps/casu-cli)
