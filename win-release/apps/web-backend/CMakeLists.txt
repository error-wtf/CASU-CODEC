# CASU-Web-Backend — Windows-native web-casu loopback server (Phase C4).
# Native Windows executable that hosts the web-casu API (REQ-WEB-001/002):
# binds 127.0.0.1, serves the unmodified web/ frontend and the casu_webapi
# endpoints via the shared libraries.
add_executable(casu_web_backend main.cpp)
find_package(Qt6 REQUIRED COMPONENTS Core Network)
target_link_libraries(casu_web_backend PRIVATE
    casu_webapi casu_network casu_codec casu_media casu_core
    Qt6::Network Qt6::Core)
target_compile_features(casu_web_backend PRIVATE cxx_std_20)
set_target_properties(casu_web_backend PROPERTIES RUNTIME_OUTPUT_NAME "CASU-Web-Backend")
casu_stage_app("CASU-Web-Backend.exe" casu_web_backend)

# Application icon resource (embedded into the exe; same icon as the Start
# Menu shortcut and the Linux desktop entry).
find_program(MINGW_WINDRES x86_64-w64-mingw32-windres)
if(MINGW_WINDRES)
  add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/app_res.o
    COMMAND ${MINGW_WINDRES}
      ${CMAKE_CURRENT_SOURCE_DIR}/app.rc -O coff
      -o ${CMAKE_CURRENT_BINARY_DIR}/app_res.o
    DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/app.rc
            ${CMAKE_CURRENT_SOURCE_DIR}/assets/web_casu_icon.ico)
  target_sources(casu_web_backend PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/app_res.o)
endif()

# Shortcut/installer icon shipped inside the package (setup.nsi references it).
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/assets/web_casu_icon.ico
        DESTINATION assets COMPONENT web)

# Stage the Qt + MinGW runtime DLLs next to the exe so Wine can run it
# directly from the build tree (same pattern as the test harness).
set(CASU_QT_BIN_DIR "${CASU_THIRD_PARTY}/qt/6.8.3/mingw_64/bin")
if(CMAKE_CROSSCOMPILING)
  add_custom_command(TARGET casu_web_backend POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      $<TARGET_RUNTIME_DLLS:casu_web_backend>
      $<TARGET_FILE_DIR:casu_web_backend>
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      "${CASU_QT_BIN_DIR}/libgcc_s_seh-1.dll"
      "${CASU_QT_BIN_DIR}/libstdc++-6.dll"
      "${CASU_QT_BIN_DIR}/libwinpthread-1.dll"
      "${CASU_QT_BIN_DIR}/libssl-3-x64.dll"
      "${CASU_QT_BIN_DIR}/libcrypto-3-x64.dll"
      $<TARGET_FILE_DIR:casu_web_backend>
    COMMAND_EXPAND_LISTS)

  # Byte-identical frontend deployed as web/ + assets/ next to the exe (the
  # site root, mirroring web_casu.py: site_root = web_root.parent).
  add_custom_command(TARGET casu_web_backend POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
      "${CMAKE_CURRENT_SOURCE_DIR}/web" "$<TARGET_FILE_DIR:casu_web_backend>/web"
    COMMAND ${CMAKE_COMMAND} -E copy_directory
      "${CMAKE_CURRENT_SOURCE_DIR}/assets" "$<TARGET_FILE_DIR:casu_web_backend>/assets"
    COMMAND_EXPAND_LISTS)
endif()

# Package layout (CPack component "web"): web/ + assets/ next to the exe.
install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/web/" DESTINATION web COMPONENT web)
install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/assets/" DESTINATION assets COMPONENT web)
