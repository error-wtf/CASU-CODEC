# packaging.cmake — self-contained Windows package via CPack zip.
# Layout (REQ-PKG-001, see README_WINDOWS.md):
#   MPCASU-Windows-x86_64.zip
#     MPCASU.exe, CASU-Converter.exe, CASU-Web-Backend.exe, casu.exe
#     Qt6*.dll
#     plugins/platforms/qwindows.dll
#     vlc/  (libvlc.dll, libvlccore.dll, plugins/)
#     tools/ (ffmpeg.exe, ffprobe.exe, yt-dlp.exe)
#     web/pure/
#     LICENSE, THIRD_PARTY_LICENSES/, README_WINDOWS.md
#
# Included from the top-level CMakeLists.txt once the modular targets exist.

get_filename_component(CASU_THIRD_PARTY "${CMAKE_CURRENT_LIST_DIR}/../third_party"
                       ABSOLUTE)

set(CPACK_GENERATOR ZIP)
set(CPACK_PACKAGE_NAME "MPCASU-Windows")
set(CPACK_PACKAGE_FILE_NAME "MPCASU-Windows-x86_64")
set(CPACK_PACKAGE_VERSION "7.0.0")
# Single self-contained zip (all components installed into one archive).
set(CPACK_ARCHIVE_COMPONENT_INSTALL OFF)

# --- Qt runtime -----------------------------------------------------------
# The whole Qt bin dir is staged (contains Qt6Core/Gui/Widgets/Network/… DLLs
# plus the toolchain-support DLLs). The platform plugin is staged separately.
install(DIRECTORY "${CASU_THIRD_PARTY}/qt/6.8.3/mingw_64/bin/"
        DESTINATION .
        COMPONENT qt
        FILES_MATCHING PATTERN "*.dll")
install(DIRECTORY "${CASU_THIRD_PARTY}/qt/6.8.3/mingw_64/plugins/"
        DESTINATION plugins
        COMPONENT qt
        FILES_MATCHING PATTERN "*.dll")

# --- Microsoft Edge WebView2 runtime loader -------------------------------
if(EXISTS "${CASU_THIRD_PARTY}/webview2/x64/WebView2Loader.dll")
  install(FILES "${CASU_THIRD_PARTY}/webview2/x64/WebView2Loader.dll"
          DESTINATION . COMPONENT qt)
endif()

# --- libVLC ---------------------------------------------------------------
# The DLLs live at the package root (Windows loads them next to the exe); the
# plugin module tree stays in vlc/plugins and is found via VLC_PLUGIN_PATH
# (set by apps/mpcasu/main.cpp).
install(FILES "${CASU_THIRD_PARTY}/vlc/libvlc.dll"
              "${CASU_THIRD_PARTY}/vlc/libvlccore.dll"
        DESTINATION . COMPONENT vlc)
install(DIRECTORY "${CASU_THIRD_PARTY}/vlc/plugins/"
        DESTINATION vlc/plugins COMPONENT vlc)

# --- bundled helper tools -------------------------------------------------
install(FILES "${CASU_THIRD_PARTY}/tools/ffmpeg.exe"
              "${CASU_THIRD_PARTY}/tools/ffprobe.exe"
              "${CASU_THIRD_PARTY}/tools/yt-dlp.exe"
        DESTINATION tools COMPONENT tools)

# --- docs + licenses ------------------------------------------------------
install(FILES "${CMAKE_CURRENT_LIST_DIR}/../README_WINDOWS.md"
        DESTINATION . COMPONENT docs)
install(DIRECTORY "${CASU_THIRD_PARTY}/THIRD_PARTY_LICENSES/"
        DESTINATION THIRD_PARTY_LICENSES COMPONENT docs)

# --- Pure Web (frozen, byte-identical; WP-PURE-002/005) -------------------
# Copy of the published MPCASU-PURE-WEB-3.0.0 release (verified SHA256
# b71b5d0b3ecde8dd7d2098665f94c4381abd6815a9727019adcc009f68ebf8de). Never
# edit these files; packaging-only concerns go in README_WINDOWS.md.
install(DIRECTORY "${CMAKE_CURRENT_LIST_DIR}/../web/pure/"
        DESTINATION web/pure COMPONENT web)

set(CPACK_COMPONENTS_ALL apps qt vlc tools docs web)
set(CPACK_COMPONENT_APPS_DESCRIPTION "Application executables")
set(CPACK_COMPONENT_QT_DESCRIPTION "Qt 6 runtime (DLLs + plugins)")
set(CPACK_COMPONENT_VLC_DESCRIPTION "libVLC runtime (DLLs + plugins)")
set(CPACK_COMPONENT_TOOLS_DESCRIPTION "Bundled helper executables")
set(CPACK_COMPONENT_DOCS_DESCRIPTION "Documentation + third-party licenses")
set(CPACK_COMPONENT_WEB_DESCRIPTION "Bundled web assets")

include(CPack)
