# Fuzz report

Status: **OPEN**.

The native readers have bounded manifest/chunk sizes and fail closed on
truncation, unknown chunk types, invalid lengths and integrity mismatches.
An Atheris/Hypothesis campaign and corruption corpus are still required for
the CASUNAT2 reader before Format Robustness can be marked PASS.
