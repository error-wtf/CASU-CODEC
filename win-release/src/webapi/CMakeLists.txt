# casu_webapi — shared loopback web API core (Phase B5).
# HTTP server skeleton (QTcpServer, loopback + host validation + size caps),
# endpoint-handler contract, TranscodeStore and Range/HEAD media planning
# (reusing casu_network's HTTP Range/206 primitives).
add_library(casu_webapi STATIC
    casu/webapi/http.cpp
    casu/webapi/security.cpp
    casu/webapi/media_serve.cpp
    casu/webapi/transcode_store.cpp
    casu/webapi/server.cpp
)

find_package(Qt6 REQUIRED COMPONENTS Core Network)

target_link_libraries(casu_webapi PUBLIC Qt6::Network Qt6::Core)
target_link_libraries(casu_webapi PRIVATE casu_core casu_network casu_codec)
target_include_directories(casu_webapi PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../codec)
target_include_directories(casu_webapi PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_features(casu_webapi PUBLIC cxx_std_20)