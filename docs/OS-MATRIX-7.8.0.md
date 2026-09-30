# OS-Matrix 7.8.0 — finaler Stand (30.09. Abend)

| OS | Build | Release-Asset | Test | Status |
|----|-------|---------------|------|--------|
| Linux (Debian-DEBs) | ✅ gebaut | ✅ 4 Debs (CODEC) + 1 Deb (Player) | 530+28 pytest grün; installiert & läuft | PERFEKT |
| Windows x86_64 | ✅ gebaut (MingW-cross, Wine-verifiziert) | ✅ Zip (277 MB) + Setup.exe (214 MB) | core/network/cli ALL PASS unter Wine | PERFEKT |
| Android (APK) | ✅ gebaut (Gradle, 4 ABIs) | ✅ debug-APK (100 MB) | dex-Verifikation (kein spotify/tidal) | PERFEKT* (*debug-signed) |
| Web (pure web-casu) | ✅ Teil der Debs/Windows-Paket | ✅ web-casu.deb + im Zip | js-syntax + Endpunkte | PERFEKT |
| macOS | ❌ VM bootet kein macOS (Linux-rescue im bash-3.2, kein sw_vers/System) | ❌ | — | BLOCKIERT: VM-Reparatur nötig |
| iOS | ❌ baut nur auf macOS-Xcode (project.yml) | ❌ | — | BLOCKIERT: folgt macOS |

## macOS-VM-Untersuchung (30.09. ~21:40)
Die OSX-KVM bootet die **Big-Sur-BaseSystem-Installationsumgebung** (RAMdisk,
/dev/disk1s1 1,9 Gi, "Install macOS Big Sur.app" in /Applications). Das
eigentliche macOS auf mac_hdd_ng.img (33 GB) wurde **nie installiert** — der
Setup-Assistent von gestern lief im Installer, nicht im fertigen OS.
Deshalb: kein sw_vers, keine LaunchDaemons, kein buildfähiges macOS.

### Um macOS zu bauen, fehlt (Reihenfolge):
1. macOS-Installation auf Macintosh HD aus dem Installer heraus (30–60 min)
2. Xcode Command Line Tools (~1–2 GB Download in der VM)
3. Python 3.13 + PySide6 6.10.2 + PyInstaller in der VM
4. apple/macos/build_mpcasu.sh ausführen (erzeugt MPCASU.app/.dmg)
5. iOS: zusätzlich Xcode + project.yml (xcodegen) — nur nach macOS-Build

### Alternativpfad (ohne VM): MacBoston-Build-Service o.ä. — nicht kostenlos,
damit gegen die OBERSTE MAXIME (alles kostenlos) verstoßend → nicht verfolgt.
