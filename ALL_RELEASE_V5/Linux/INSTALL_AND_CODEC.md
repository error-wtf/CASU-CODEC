# INSTALL_AND_CODEC — Installation + Dateitypen (Linux)

## Installation
```sh
sudo apt install ./dist/casu-codec_3.0.0_all.deb \
                 ./dist/casu-converter_3.0.0_all.deb \
                 ./dist/mpcasu_3.0.0_all.deb \
                 ./dist/web-casu_3.0.0_all.deb
```
(Abhängigkeiten löst apt ggf. mit `sudo apt -f install`.)

## Verifikation nach Installation
- `mpcasu` startet (Qt-Player); `casu kind <datei>.mp5` (CLI).
- `.casu`/`.mp5`-Doppelklick im Dateimanager → MPCASU
  (MIME-DB: `update-mime-database` + `update-desktop-database` im postinst).
- `web-casu` → `http://127.0.0.1:8497/web/` (Pure Web).

## Media-Codec (CODEC-001, geplant für v5.0)
- GStreamer-Dezimal-/Playback-Filter für CASU/MP5 geplant (Linux-Pendant zum
  Windows-MF/DirectShow-Decoder). Status: nicht gebaut (BLOCKER-005).

## Dateitypen
- `.casu` (CASU-Container), `.mp5` (MP5) → application/x-casu → MPCASU.
- Definition: `packaging/casu-codec-mime.xml`; Desktop-Entry im Paket.