# dependencies.cmake — locates the bundled Windows runtime dependencies under
# win-release/third_party/ for the cross build. Everything needed to build and
# stage a self-contained package comes from third_party (no dev PATH reliance).
#
# Usage from a target's CMakeLists:
#   include(../../cmake/dependencies.cmake)   # once, from top level
#   casu_qt_deploy_targets(MPCASU casu_mpcasu)

# Root of the bundled third-party binaries relative to the top-level build.
get_filename_component(CASU_THIRD_PARTY "${CMAKE_CURRENT_LIST_DIR}/../third_party"
                       ABSOLUTE)

# The cross toolchain restricts package/include/library lookup to
# CMAKE_FIND_ROOT_PATH (ONLY modes); the bundled Qt lives under third_party,
# so it must be added to the search roots for find_package(Qt6) to succeed.
list(APPEND CMAKE_FIND_ROOT_PATH "${CASU_THIRD_PARTY}")

# --- Qt 6 (MinGW) ---------------------------------------------------------
set(QT_PREFIX "${CASU_THIRD_PARTY}/qt/6.8.3/mingw_64")
set(QT_INCLUDE_DIR "${QT_PREFIX}/include")
set(QT_LIB_DIR "${QT_PREFIX}/lib")
set(QT_BIN_DIR "${QT_PREFIX}/bin")

set(CMAKE_PREFIX_PATH "${QT_PREFIX}" ${CMAKE_PREFIX_PATH})
# The mingw64 toolchain sets CMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY, which
# would hide the bundled Qt package config; make it findable from the root.
set(CMAKE_FIND_ROOT_PATH "${QT_PREFIX}" ${CMAKE_FIND_ROOT_PATH})

# --- libVLC (Windows) -----------------------------------------------------
set(LIBVLC_PREFIX "${CASU_THIRD_PARTY}/vlc")
set(LIBVLC_INCLUDE_DIR "${CASU_THIRD_PARTY}/vlc/sdk/include")
set(LIBVLC_LIB_DIR "${CASU_THIRD_PARTY}/vlc/sdk/lib")

# --- bundled helper executables -------------------------------------------
set(FFMPEG_EXE "${CASU_THIRD_PARTY}/tools/ffmpeg.exe")
set(FFPROBE_EXE "${CASU_THIRD_PARTY}/tools/ffprobe.exe")
set(YTDLP_EXE "${CASU_THIRD_PARTY}/tools/yt-dlp.exe")

# --- zstd ------------------------------------------------------------------
set(ZSTD_PREFIX "${CASU_THIRD_PARTY}/zstd")
set(ZSTD_LIB_DIR "${CASU_THIRD_PARTY}/zstd")
set(ZSTD_INCLUDE_DIR "${CASU_THIRD_PARTY}/zstd/include")

# --- helper: enumerate Qt DLLs a target links against ---------------------
# Records into CASU_STAGED_QT_DLLS the Qt6*.dll files needed for a target's
# linked Qt modules (Core/Gui/Widgets/Network/…).
set(CASU_STAGED_QT_DLLS "" CACHE INTERNAL "")

function(casu_qt_deploy_targets)
  # Targets are documented for packaging; DLL staging is handled by the
  # packaging rules in packaging.cmake (CPack install() of the whole Qt bin).
endfunction()

# --- MinGW runtime DLLs ----------------------------------------------------
# GCC runtime for the self-contained package (libgcc_s_seh-1.dll,
# libstdc++-6.dll, libwinpthread-1.dll). Resolved at packaging time; the
# exes are built with -static-libgcc/-static-libstdc++ but winpthreads may
# still be dynamic.
find_program(MINGW_GCC_DUMPBIN x86_64-w64-mingw32-gcc)

# --- app staging helper -----------------------------------------------------
# Registers an application executable for the CPack zip (defined here so app
# subdirectories can call it; packaging.cmake installs the collected set).
set(CASU_APPS "" CACHE INTERNAL "")
function(casu_stage_app exe_name target)
  list(APPEND CASU_APPS "${exe_name}")
  set(CASU_APPS "${CASU_APPS}" CACHE INTERNAL "" FORCE)
  install(TARGETS ${target} RUNTIME DESTINATION . COMPONENT apps)
endfunction()
