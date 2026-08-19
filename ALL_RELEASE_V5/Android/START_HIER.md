# START_HIER — Start-Prompt für die Android-Session (v5.0)

Öffne eine NEUE Session in `/home/error/Codec-Casu` und gib den folgenden Text
als ersten Prompt ein.

================================================================================
PROMPT:
================================================================================

Starte den Android-Port von CASU-CODEC / MPCASU (Version **v5.0.0**; v4.x wird
übersprungen). Ziel: `.apk`/`.aab` (arm64-v8a + armeabi-v7a + x86_64),
Qt 6 for Android, QtWebEngine-Browser (voll), libVLC-Android.

Lies ZUERST:
1. `ALL_RELEASE_V5/README.md` — Versionspolitik + Struktur
2. `ALL_RELEASE_V5/Android/PORT_STATUS.md` — Stand + Entscheidungsbedarf
3. `ALL_RELEASE_V5/Android/PREREQUISITES.md` — Beschaffung (SCHRITT 0)
4. `ALL_RELEASE_V5/Android/RUN_CHECKLIST.md` — Gates
5. `win-release/` als Portierungs-Vorlage (C++20/Qt6, bereits fertig)

Grundregeln:
- Vor jeder Änderung Backup; nach jeder Änderung Tests; nie Release ohne grüne
  Gates. Keine falschen PASS.
- Secrets: Token NUR in `/home/error/gittoken.env` (nie loggen, nie committen).
- Nutzer-Entscheidungen zuerst einholen: YouTube-Transport auf Android,
  Play-Store vs Sideload, Touch-UI-Umfang (siehe PORT_STATUS).
- Erst Hello-APK (läuft auf Emulator), dann Core-Libs (.so), dann Player-APK.

Nächster Schritt: PREREQUISITES (SDK/NDK/JDK/Qt-for-Android) + Nutzer-Entscheidungen.
================================================================================
ENDE PROMPT
================================================================================