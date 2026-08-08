# Fuzz report

Status: **PARTIAL**.

The native readers have bounded manifest/chunk/file sizes and fail closed on
truncation, unknown chunk types, invalid lengths, invalid recovery offsets and
integrity mismatches.
A deterministic dependency-free corruption campaign is now available at
`tools/fuzz_native_v2.py`; it mutates truncation, headers, lengths and payload
bytes and asserts that only fully integrity-verified containers are accepted.
The unit test executes 500 mutations; a local 10,000-iteration campaign is
also reproducible with `python tools/fuzz_native_v2.py --iterations 10000`.
A several-million-execution Atheris campaign and a checked-in corpus remain
required before Format Robustness can be marked PASS.
