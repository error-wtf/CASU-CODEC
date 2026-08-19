# casu_network — shared network library (Phase B3).
# HTTP client (Qt6Network), URL/scheme handling, yt-dlp + spotDL wrappers,
# web-provider URL builders and the shared HTTP Range/206 primitives.
# Links casu_core (JSON parsing for yt-dlp output, token digests).
add_library(casu_network STATIC
    casu/network/url.cpp
    casu/network/range.cpp
    casu/network/http.cpp
    casu/network/ytdlp.cpp
    casu/network/spotify.cpp
    casu/network/providers.cpp
    casu/web/webproviders.cpp
)

find_package(Qt6 REQUIRED COMPONENTS Core Network)

target_link_libraries(casu_network PUBLIC Qt6::Network Qt6::Core)
target_link_libraries(casu_network PRIVATE casu_core)
target_include_directories(casu_network PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_features(casu_network PUBLIC cxx_std_20)