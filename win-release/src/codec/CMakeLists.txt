# casu_codec — FFmpeg/FFprobe wrappers, conversion presets and CASU export
# (Phase B2). Uses Qt6Core for QProcess (argument arrays, never shell
# strings); falls back to a _popen implementation with Windows argv quoting
# when Qt is unavailable. Links casu_core.
add_library(casu_codec STATIC
    casu/codec/subprocess.cpp
    casu/codec/tools.cpp
    casu/codec/ffprobe.cpp
    casu/codec/ffmpeg.cpp
    casu/codec/presets.cpp
    casu/codec/export.cpp
)

target_link_libraries(casu_codec PUBLIC casu_core)
target_include_directories(casu_codec PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_features(casu_codec PUBLIC cxx_std_20)

# Qt6 is bundled under third_party (CMAKE_PREFIX_PATH set by dependencies.cmake).
find_package(Qt6 COMPONENTS Core QUIET)
if(Qt6_FOUND)
  target_compile_definitions(casu_codec PUBLIC CASU_HAS_QT=1)
  target_link_libraries(casu_codec PUBLIC Qt6::Core)
  message(STATUS "casu_codec: using Qt6 QProcess (Qt6Core found)")
else()
  message(STATUS "casu_codec: Qt6 not found, using _popen fallback (Qt-free)")
endif()
