# Fuzz report

Status: **PASS for the bounded CASUNAT2 parser campaign**.

The native readers have bounded manifest/chunk/file sizes and fail closed on
truncation, unknown chunk types, invalid lengths, invalid recovery offsets and
integrity mismatches.
A deterministic dependency-free corruption campaign is now available at
`tools/fuzz_native_v2.py`; it mutates truncation, headers, lengths and payload
bytes and asserts that only fully integrity-verified containers are accepted.
The unit test executes 500 mutations. On 2026-08-09 the reproducible
10,000-iteration run after per-chunk hash integration with explicit seed
`20260809` produced 9,352 rejected mutations, 648 still-valid fully
integrity-verified mutations and **0 unexpected accepts/crashes/hangs**. The
seed container includes video config/key/tile chunks, PCM audio and a valid
typed, compressed bitmap-subtitle chunk.

On 2026-08-13, after strict manifest/stream/chunk validation, strict JSON,
complete seek/hash coverage and hash-bound recovery checkpoints were added,
`python3 tools/fuzz_native_v2.py --iterations 10000 --seed 20260813`
completed in 3.0 seconds: **9,986 rejected, 14 still-valid fully verified,
0 unexpected**. The production writer now creates valid typed seed payloads
rather than opaque placeholder bytes.

The release-scale campaign was then split into 30 independent deterministic
processes so every individual command retained the required 60-second ceiling:
`--iterations 100000` with seeds `2026081301` through `2026081330`.
All 3,000,000 executions completed; **2,994,529 were rejected, 5,471 mutations
remained structurally valid and were fully integrity-verified, and 0 were
unexpectedly accepted, crashed or hung**. Individual processes completed in
roughly 31–34 seconds. This satisfies the supplied Gate-C several-million
parser-execution budget while keeping the exact seed range reproducible.

The decode boundary is guarded separately: FFprobe JSON runs under monitored
output/time budgets and STRICT frames have dimension/byte ceilings. Unit tests
force both excessive probe output and timeout and verify that the child process
is killed.

This closes the bounded Gate-C parser campaign defined by the supplied plan.
Coverage-guided Atheris/libFuzzer and third-party decoder campaigns remain
useful ongoing defense-in-depth work; they are not misrepresented as having
run here.
