# casu_core — shared container-format core (Phase B).
# Pure C++20, no external deps (self-contained SHA-256), cross-compiles to
# Windows/MinGW. Drives kind detection, header/chunk parsing and validation.
add_library(casu_core STATIC
    casu/sha256.cpp
    casu/formats.cpp
    casu/json.cpp
    casu/manifest.cpp
    casu/native.cpp
    casu/native_v2.cpp
    casu/mp5.cpp
    casu/sidecar.cpp
    casu/journal.cpp
)
# Link zlib STATICALLY (libz.a) so the package stays self-contained (no
# zlib1.dll dependency, REQ-PORT-002). The default `z` target would pick the
# shared import lib (libz.dll.a -> zlib1.dll).
find_library(CASU_ZLIB_STATIC NAMES libz.a PATHS /usr/x86_64-w64-mingw32/lib NO_DEFAULT_PATH)
if(NOT CASU_ZLIB_STATIC)
  find_library(CASU_ZLIB_STATIC NAMES libz.a)
endif()
target_link_libraries(casu_core PUBLIC "${CASU_ZLIB_STATIC}")

# WP-CORE-007: link libzstd STATICALLY (libzstd.a) for MP5 zstd-decompress
# support (reader tries zstd first, falls back to zlib like the reference
# `casu/mp5/reader.py _decompress`). The writer keeps zlib output so the
# byte-level golden fixtures (frozen reference without the zstd package) stay
# byte-identical.
find_library(CASU_ZSTD_STATIC NAMES libzstd.a PATHS /usr/x86_64-w64-mingw32/lib NO_DEFAULT_PATH)
if(NOT CASU_ZSTD_STATIC)
  find_library(CASU_ZSTD_STATIC NAMES libzstd.a)
endif()
if(CASU_ZSTD_STATIC)
  target_link_libraries(casu_core PUBLIC "${CASU_ZSTD_STATIC}")
  target_compile_definitions(casu_core PUBLIC CASU_HAVE_ZSTD=1)
endif()
target_include_directories(casu_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_features(casu_core PUBLIC cxx_std_20)
