# BLOCKERS — offene Blocker während des Ports

Eintrag pro Blocker:
```
ID: BLOCKER-001
Blocker: ...
Betroffene WPs: ...
Research performed: ...
Next action: ...
```

Aktuell:
- **BLOCKER-000 (offen, kein Design-Blocker):** Windows-Runtime-Binaries
  (Qt6-MinGW, libVLC-Windows, ffmpeg/ffprobe/yt-dlp.exe) müssen beschafft
  werden, bevor Paketierung/Playback-Wine-Tests möglich. Kein
  Implementierungs-Blocker für die C++-Core-Arbeit.
  → Details + Bezugsquellen: `win-release/PREREQUISITES.md`.
  → In der neuen Session als SCHRITT 0 abarbeiten.
