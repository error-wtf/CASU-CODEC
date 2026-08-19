# casu_playback — shared playback library (M-PCASU-3).
# CppPlaybackController state machine + abstract backend + LibVLCBackend
# (in-process libVLC 3.0 via the bundled ABI bindings). Links casu_core for
# CASU container extraction and the bundled libvlc.a import library.
add_library(casu_playback STATIC
    casu/playback/controller.cpp
    casu/playback/libvlc_backend.cpp
)

target_link_libraries(casu_playback PUBLIC casu_core)
target_link_libraries(casu_playback PRIVATE "${CASU_THIRD_PARTY}/vlc/libvlc.a")
target_include_directories(casu_playback PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_features(casu_playback PUBLIC cxx_std_20)
