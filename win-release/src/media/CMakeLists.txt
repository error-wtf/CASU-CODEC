# casu_media — probe/thumbnail/waveform/tags/kind on top of casu_codec and
# casu_core (Phase B2). Qt usage is inherited from casu_codec's process layer.
add_library(casu_media STATIC
    casu/media/probe.cpp
    casu/media/waveform.cpp
    casu/media/thumbnail.cpp
    casu/media/tags.cpp
    casu/media/kind.cpp
)

target_link_libraries(casu_media PUBLIC casu_codec casu_core)
target_include_directories(casu_media PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_features(casu_media PUBLIC cxx_std_20)
