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

The decode boundary is guarded separately: FFprobe JSON runs under monitored
output/time budgets and STRICT frames have dimension/byte ceilings. Unit tests
force both excessive probe output and timeout and verify that the child process
is killed.

This closes the bounded Gate-C campaign defined by the supplied plan. Larger
Atheris/libFuzzer runs and network-input stress remain useful ongoing security
work; they are not misrepresented as having run here.
