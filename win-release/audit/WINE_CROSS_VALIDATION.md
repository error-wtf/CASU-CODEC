# Wine Cross-Validation — Windows C++ Core (2026-09-29)

## Ergebnis: PASS

Der Qt-freie Kern (`src/core`, casu_core: CASUNAT1 + CASUNAT2 Reader/Writer,
Integritätsprüfung, Seek-Index, Recovery) wurde mit dem MinGW-w64-Cross-Toolchain
zu einer nativen Windows-Binärdatei (PE32+) kompiliert und unter Wine 10.0
ausgeführt.

## Durchgeführt

1. `cmake` + `ninja` mit `cmake/mingw64-toolchain.cmake` (nur `src/core` +
   `src/hello`; `src/codec`+ benötigen Qt6-Header aus third_party, siehe unten)
2. `wine_core_test.exe`: liest eine vom Linux-Python-Codec
   (`casu.native_v2.converter.convert_media_to_native_v2`) erzeugte
   CASUNAT2-Datei (WAV → CASUNAT2, 3979 Bytes) mit dem C++-Reader
   `casu::casunat2::read_native_v2()`
3. Ausgabe: `WIN_CORE_TEST=PASS chunks=5 integrity=1` — Chunk-Anzahl und
   SHA-256-Integritätstabelle stimmen zwischen Python-Writer und C++-Reader
   überein

## Bekannte Grenzen (ehrlich)

- `src/codec` und `src/media` kompilieren aktuell NICHT Qt-frei: `analyze.cpp`,
  `strict_frames.cpp`, `native_convert.cpp` includen `<QProcess>`/`<QDateTime>`
  bedingungslos (der "_popen fallback" im CMake greift nur beim Linken).
  Port-Aufgabe: QProcess→popen/_wspawn, QDateTime→std::chrono (siehe ROADMAP).
- Der vollständige MPCASU-Windows-Build (Qt-GUI) benötigt das gebündelte
  third_party (Qt 6.8.3 MinGW, libVLC, ffmpeg.exe) — siehe README_WINDOWS.md.
- macOS/iOS-Builds sind auf Linux nicht möglich (Apple-EULA verbietet
  macOS-VMs auf Nicht-Apple-Hardware; Xcode existiert nur für macOS).

## Port-Aufgabe codec/media (konkret vermessen)

| Datei | Zeilen | Qt-Nutzungen | Ersetzung |
|---|---|---|---|
| analyze.cpp | 736 | 6 (QProcess-PipeReader, QTemporaryFile, QFile) | _popen + tempnam oder posix_spawn/Win32 CreatePipe |
| strict_frames.cpp | 606 | 10 (QDateTime für Zeitstempel) | std::chrono + strftime |
| native_convert.cpp | 1.837 | 24 (QProcess, QString-Argumente, QByteArray-Piping) | Prozess-Wrapper-Klasse (portabel, ~150 Z.) |

Die QString/QByteArray-Nutzung ist argumentativ (Kommandozeilen + Binary-Piping);
eine portabile `ProcessRunner`-Abstraktion (popen unter POSIX, _popen unter
Windows) ersetzt QProcess vollständig. Geschätzter Aufwand: 1–2 focussierte
Sessions inkl. Tests unter Wine.
