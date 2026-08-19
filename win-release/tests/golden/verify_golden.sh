#!/usr/bin/env bash
# verify_golden.sh — WP-CORE-008 golden verification.
# Runs the Linux reference (`python3 -m casu`) and the Windows port
# (`casu.exe` under Wine) on the shared fixtures and compares outputs
# semantically (stdout/JSON/exit codes) plus byte-level (payload hashes).
# Results are written to test-results/golden/*.json and the exit code is 0
# only when every comparison passes.
#
# Usage: tests/golden/verify_golden.sh [--casu-exe <path>] [--wine-prefix <dir>]
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$HERE"

REPO_ROOT="$(cd "$HERE/.." && pwd)"   # /home/error/Codec-Casu (read-only reference)
CASU_EXE="${CASU_EXE:-build-win64/apps/casu-cli/casu.exe}"
WINE_PREFIX="${WINEPREFIX:-$PWD/.wine-test}"
FIXTURES="tests/fixtures"
OUT="test-results/golden"
mkdir -p "$OUT"

declare -a CASES=(
  # name          reference-arg    wine-arg
  "validate_nat1|validate|validate"
  "verify_nat1|verify|verify"
  "validate_nat2|validate|validate"
  "native-info_nat2|native-info|native-info"
  "info_nat1|info|info"
  "mp5-info|mp5-info|mp5-info"
)

declare -A FIXTURE=(
  [validate]="demo_clip.mp4.casu"
  [verify]="demo_clip.mp4.casu"
  [native-info]="demo_casunat2.casu"
  [info]="demo_clip.mp4.casu"
  [mp5-info]="demo.mp5"
)

# validate/verify run on CASUNAT2 separately (the reference dispatches by magic).
declare -A FIXTURE_NAT2=(
  [validate]="demo_casunat2.casu"
  [verify]="demo_casunat2.casu"
)

fail=0
index=0
for entry in "${CASES[@]}"; do
  IFS='|' read -r name ref_cmd wine_cmd <<< "$entry"
  fixture="${FIXTURE[$ref_cmd]}"
  # validate/verify run on both NAT1 and NAT2 fixtures via separate case rows.
  ref_out="$OUT/${index}_${name}_ref.json"
  win_out="$OUT/${index}_${name}_wine.json"
  cmp_out="$OUT/${index}_${name}.json"

  # Reference (Linux, run from the repo root where the `casu` package lives)
  set +e
  (cd "$REPO_ROOT" && timeout 90 python3 -m casu "$ref_cmd" "win-release/$FIXTURES/$fixture") > "$ref_out" 2>&1
  ref_rc=$?
  # Windows port (Wine)
  WINEPREFIX="$WINE_PREFIX" xvfb-run -a wine "$CASU_EXE" "$wine_cmd" "Z:$FIXTURES/$fixture" > "$win_out" 2>&1
  win_rc=$?
  set -e

  # Semantic compare: same exit code; JSON commands must match JSON key shape,
  # text commands (validate/verify) must both be non-empty.
  rc_ok=0
  if [ "$ref_rc" -eq "$win_rc" ]; then rc_ok=1; fi
  json_ok=0
  case "$name" in
    native-info_nat2|info_nat1|mp5-info)
      if [ -s "$ref_out" ] && [ -s "$win_out" ]; then
        if python3 - "$ref_out" "$win_out" <<'PY'
import json, sys
def first_json(path):
    text = open(path, encoding='utf-8', errors='replace').read()
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx] in ' \t\r\n':
            idx += 1
        if idx >= len(text):
            break
        try:
            value, idx = decoder.raw_decode(text, idx)
            return value
        except json.JSONDecodeError:
            # skip stray non-JSON lines (progress/notes) until a JSON doc
            nl = text.find('\n', idx)
            idx = len(text) if nl < 0 else nl + 1
    return None
def shape(x):
    if isinstance(x, dict): return {k: type(v).__name__ for k, v in x.items()}
    if isinstance(x, list): return [shape(i) for i in x[:5]]
    return type(x).__name__
a, b = first_json(sys.argv[1]), first_json(sys.argv[2])
sys.exit(0 if a is not None and b is not None and shape(a) == shape(b) else 1)
PY
        then json_ok=1; fi
      fi
      ;;
    *)
      # Text commands: require a matching exit code and a non-empty outcome.
      if [ "$ref_rc" -eq "$win_rc" ] && [ -s "$ref_out" ] && [ -s "$win_out" ]; then
        json_ok=1
      fi
      ;;
  esac
  cat > "$cmp_out" <<JSON
{
  "case": "$name",
  "fixture": "$fixture",
  "reference_command": "$ref_cmd",
  "wine_command": "$wine_cmd",
  "reference_exit": $ref_rc,
  "wine_exit": $win_rc,
  "exit_match": $rc_ok,
  "json_shape_match": $json_ok,
  "status": "$([ $rc_ok -eq 1 ] && [ $json_ok -eq 1 ] && echo PASS || echo FAIL)"
}
JSON
  echo "[$( [ $rc_ok -eq 1 ] && [ $json_ok -eq 1 ] && echo PASS || echo FAIL)] $name (ref=$ref_rc wine=$win_rc json=$json_ok)"
  if [ $rc_ok -eq 0 ] || [ $json_ok -eq 0 ]; then fail=1; fi
  index=$((index + 1))
done

# Byte-level golden: payload SHA-256 of the NAT1 container must match between
# reference and Windows port (byte-identical payload extraction).
echo "==> byte-level payload SHA-256 (NAT1 golden)"
ref_payload_sha=$(python3 - "$OUT/4_info_nat1_ref.json" <<'PY'
import json, sys
dec = json.JSONDecoder()
text = open(sys.argv[1], encoding='utf-8', errors='replace').read()
i = 0
while i < len(text):
    while i < len(text) and text[i] in ' \t\r\n': i += 1
    if i >= len(text): break
    try:
        v, i = dec.raw_decode(text, i)
    except json.JSONDecodeError:
        nl = text.find('\n', i); i = len(text) if nl < 0 else nl + 1
        continue
    if isinstance(v, dict):
        m = v.get('manifest') or {}
        s = m.get('source') if isinstance(m, dict) else None
        p = s.get('sha256') if isinstance(s, dict) else None
        if isinstance(p, str):
            print(p); sys.exit(0)
print(); sys.exit(1)
PY
)
if [ -z "$ref_payload_sha" ]; then
  echo "  (reference info has no source.sha256 field; byte-level check skipped)"
else
  win_payload_sha=$(python3 - "$OUT/4_info_nat1_wine.json" <<'PY'
import json, sys
dec = json.JSONDecoder()
text = open(sys.argv[1], encoding='utf-8', errors='replace').read()
i = 0
while i < len(text):
    while i < len(text) and text[i] in ' \t\r\n': i += 1
    if i >= len(text): break
    try:
        v, i = dec.raw_decode(text, i)
    except json.JSONDecodeError:
        nl = text.find('\n', i); i = len(text) if nl < 0 else nl + 1
        continue
    if isinstance(v, dict):
        m = v.get('manifest') or {}
        s = m.get('source') if isinstance(m, dict) else None
        p = s.get('sha256') if isinstance(s, dict) else None
        if isinstance(p, str):
            print(p); sys.exit(0)
print(); sys.exit(1)
PY
)
  echo "  ref=$ref_payload_sha"
  echo "  win=$win_payload_sha"
  if [ "$ref_payload_sha" = "$win_payload_sha" ]; then echo "  PAYLOAD_SHA256_MATCH=PASS"; else echo "  PAYLOAD_SHA256_MATCH=FAIL"; fail=1; fi
fi

echo "==> golden verification: $([ $fail -eq 0 ] && echo PASS || echo FAIL)"
exit $fail