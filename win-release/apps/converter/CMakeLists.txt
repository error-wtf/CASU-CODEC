# CASU-Converter — Qt Widgets GUI converter (REQ-CONV-001, full GUI not CLI).
find_package(Qt6 REQUIRED COMPONENTS Widgets Gui Core)

add_executable(casu_converter
    main.cpp
    mainwindow.cpp
    worker.cpp
    engine.cpp
    manifest.cpp
    theme.cpp
)
target_compile_features(casu_converter PRIVATE cxx_std_20)
target_include_directories(casu_converter PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(casu_converter PRIVATE
    casu_media casu_codec casu_core casu_network
    Qt6::Widgets Qt6::Gui Qt6::Core)
set_target_properties(casu_converter PROPERTIES RUNTIME_OUTPUT_NAME "CASU-Converter")

casu_stage_app("CASU-Converter.exe" casu_converter)

# Application icon resource (embedded into the exe; same icon as the Start
# Menu shortcut and the Linux desktop entry).
find_program(MINGW_WINDRES x86_64-w64-mingw32-windres)
if(MINGW_WINDRES)
  add_custom_command(OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/app_res.o
    COMMAND ${MINGW_WINDRES}
      ${CMAKE_CURRENT_SOURCE_DIR}/app.rc -O coff
      -o ${CMAKE_CURRENT_BINARY_DIR}/app_res.o
    DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/app.rc
            ${CMAKE_CURRENT_SOURCE_DIR}/assets/casu_converter_icon.ico)
  target_sources(casu_converter PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/app_res.o)
endif()

# Shortcut/installer icon shipped inside the package (setup.nsi references it).
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/assets/casu_converter_icon.ico
        DESTINATION assets COMPONENT apps)

if(CMAKE_CROSSCOMPILING)
  # Stage the Qt runtime (DLLs + platform plugin) next to the exe so it runs
  # under Wine and in the packaged zip without a PATH/registry dependency.
  add_custom_command(TARGET casu_converter POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      $<TARGET_RUNTIME_DLLS:casu_converter>
      $<TARGET_FILE_DIR:casu_converter>
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      "${QT_BIN_DIR}/libgcc_s_seh-1.dll"
      "${QT_BIN_DIR}/libstdc++-6.dll"
      "${QT_BIN_DIR}/libwinpthread-1.dll"
      "${QT_BIN_DIR}/libssl-3-x64.dll"
      "${QT_BIN_DIR}/libcrypto-3-x64.dll"
      $<TARGET_FILE_DIR:casu_converter>
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      "${CASU_THIRD_PARTY}/qt/6.8.3/mingw_64/plugins/platforms/qwindows.dll"
      "$<TARGET_FILE_DIR:casu_converter>/platforms/qwindows.dll"
    COMMAND_EXPAND_LISTS)
endif()