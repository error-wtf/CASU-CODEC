# MPCASU feature completion matrix

This matrix distinguishes visible controls from capabilities that are really
implemented. A control is not marked complete merely because a widget exists.

| Feature | Backend | UI | Tested | Status |
|---|---|---:|---:|---|
| In-process legacy playback via libVLC | yes | yes | smoke | PARTIAL |
| Native CASU manifest validation and source integrity | yes | yes | unit | COMPLETE |
| Play / pause / resume / stop | yes | yes | smoke | PARTIAL |
| Seek and timeline position | yes | yes | smoke | PARTIAL |
| Volume and mute | yes | yes | smoke | PARTIAL |
| Supplied MPCASU logo and red layout | n/a | yes | compile/manual | COMPLETE |
| Original + CASU playlist comparison | yes | yes | manual | COMPLETE |
| Runtime libVLC capability report | yes | not yet exposed | unit | PARTIAL |
| URL source opening in backend | yes | not yet exposed | unit | PARTIAL |
| Audio track selection | libVLC track count/select | cycle control | unit/smoke | PARTIAL |
| Subtitle track selection | optional libVLC SPU count/select | cycle control | unit/smoke | PARTIAL |
| Embedded/external subtitles | embedded selection partial; external not yet exposed | cycle control only | no | OPEN |
| Native CASU segment scheduler and renderer | not yet present | diagnostic unavailable | no | OPEN |
| PCM waveform / spectrum | not implemented | unavailable state | no | OPEN |
| Energy measurement | not implemented | unavailable state | no | OPEN |
| Persistent media library and settings | not implemented | minimal queue only | no | OPEN |
| Source-resolution STRICT state builder | exact multi-plane unit core | no UI | unit | PARTIAL |
| CASUNAT2 binary chunks/index/integrity primitive | yes | n/a | unit | PARTIAL |

`PARTIAL` and `OPEN` are deliberate release truthfulness: the player is a
working in-process prototype, not a claim of feature parity with VLC.
