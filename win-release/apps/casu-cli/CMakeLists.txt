# casu-cli — Windows-native CASU command line tool (Phase C1).
add_executable(casu_cli
    main.cpp
    cli_util.cpp
    commands_inspect.cpp
    commands_pack.cpp
    commands_media.cpp
)
target_link_libraries(casu_cli PRIVATE casu_core casu_codec casu_media)
target_compile_features(casu_cli PRIVATE cxx_std_20)
set_target_properties(casu_cli PROPERTIES RUNTIME_OUTPUT_NAME "casu")
casu_stage_app(casu.exe casu_cli)

# casu_codec uses Qt6Core (QProcess) for the ffmpeg/ffprobe subprocess layer;
# stage the runtime DLLs next to casu.exe so the cross-built app runs under
# Wine and in the packaged zip (mirrors the test harness staging).
if(CMAKE_CROSSCOMPILING)
  add_custom_command(TARGET casu_cli POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      $<TARGET_RUNTIME_DLLS:casu_cli>
      $<TARGET_FILE_DIR:casu_cli>
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      "${QT_BIN_DIR}/libgcc_s_seh-1.dll"
      "${QT_BIN_DIR}/libstdc++-6.dll"
      "${QT_BIN_DIR}/libwinpthread-1.dll"
      "${QT_BIN_DIR}/libssl-3-x64.dll"
      "${QT_BIN_DIR}/libcrypto-3-x64.dll"
      $<TARGET_FILE_DIR:casu_cli>
    COMMAND_EXPAND_LISTS)
endif()
