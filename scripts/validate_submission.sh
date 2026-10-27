#!/usr/bin/env bash
# Reproduce the disqualification checklist (CLAUDE.md "Hard rules") end to end.
#
#     make validate                 # or: bash scripts/validate_submission.sh
#     VALIDATE_DOCKER=0 make validate   # skip the Docker build even if a daemon is up
#
# Validates what is COMMITTED: it works in a fresh local clone of HEAD, with no .env,
# Zetaris and Nightshift pointed at a closed port, and every HTTP proxy variable pointed at
# a dead one -- so any network call from the app fails instead of quietly succeeding. That
# is the judge's path: SAMPLE_MODE=true must run real agent logic with no Zetaris, no
# Nightshift and no network (rule 8).
#
# Reuses this checkout's .venv (no network to install a fresh one). Prints PASS / FAIL /
# SKIP per check and exits non-zero if anything failed. Never prints a secret value.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
WORK="$(mktemp -d)"
CLONE="${WORK}/clone"
SERVER_PID=""
FAILED=0
PASSED=0
SKIPPED=0

cleanup() {
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
  rm -rf -- "$WORK"
}
trap cleanup EXIT

pass() { echo "  PASS  $1"; PASSED=$((PASSED + 1)); }
fail() { echo "  FAIL  $1"; [ -n "${2:-}" ] && echo "        $2"; FAILED=$((FAILED + 1)); }
skip() { echo "  SKIP  $1"; [ -n "${2:-}" ] && echo "        $2"; SKIPPED=$((SKIPPED + 1)); }
section() { echo; echo "== $1"; }

# The judge's environment: no services, no network, no .env.
offline_env() {
  env -i PATH="$PATH" HOME="$WORK" LANG=C.UTF-8 \
    SAMPLE_MODE=true \
    ZETARIS_REST_URL="http://127.0.0.1:9/api/v1.0" \
    METERLESS_BASE_URL="http://127.0.0.1:9/v1" \
    HTTP_PROXY="http://127.0.0.1:9" HTTPS_PROXY="http://127.0.0.1:9" ALL_PROXY="http://127.0.0.1:9" \
    http_proxy="http://127.0.0.1:9" https_proxy="http://127.0.0.1:9" all_proxy="http://127.0.0.1:9" \
    NO_PROXY="" no_proxy="" \
    "$@"
}

echo "MedTrace submission check -- $(git -C "$ROOT" rev-parse --short HEAD) ($(git -C "$ROOT" rev-parse --abbrev-ref HEAD))"
if [ -n "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]; then
  echo "note: uncommitted changes are NOT validated -- this checks the committed HEAD"
fi

section "Fresh clone, no .env"
if git clone -q --no-hardlinks "$ROOT" "$CLONE" 2>"${WORK}/clone.err"; then
  pass "fresh clone of HEAD"
else
  fail "fresh clone of HEAD" "$(head -c 300 "${WORK}/clone.err")"
  echo; echo "cannot continue without a clone"; exit 1
fi
[ ! -e "${CLONE}/.env" ] && pass "no .env in the clone (it is gitignored)" || fail "a .env is committed"
cd "$CLONE" || exit 1

section "Rule 5 -- secrets only from environment variables"
if [ -z "$(git ls-files .env)" ] && [ -n "$(git ls-files .env.example)" ]; then
  pass ".env not tracked; .env.example tracked"
else
  fail ".env must be untracked and .env.example tracked"
fi
if out="$("$PY" scripts/secret_scan.py --all 2>&1)"; then
  pass "secret scan over every tracked file"
else
  fail "secret scan" "$(echo "$out" | tail -3)"
fi
# The NVIDIA key lives only in Nightshift (rule 3). Report file names, never the match.
hits="$(git grep -l -I -E 'nvapi-[A-Za-z0-9_-]{20,}' -- . ':!scripts/validate_submission.sh' 2>/dev/null || true)"
[ -z "$hits" ] && pass "no NVIDIA API key in any tracked file" || fail "NVIDIA API key pattern found" "$hits"

section "Rule 4 -- AI coding tools declared, one rules file"
[ -f CLAUDE.md ] && pass "CLAUDE.md is the rules file" || fail "CLAUDE.md missing"
if [ -e .cursorrules ] || [ -e .cursor/rules ]; then fail "a mirrored rules file exists (.cursor)"; else pass "no mirrored rules file"; fi
[ -s docs/AI_TOOLS_USAGE.md ] && pass "docs/AI_TOOLS_USAGE.md present" || fail "docs/AI_TOOLS_USAGE.md missing"

section "Rule 2 -- Meterless engines: conformance"
if out="$(offline_env "$PY" -m pytest -q tests/engines 2>&1)"; then
  pass "World Model + H-MEM conformance ($(echo "$out" | grep -E -o '[0-9]+ passed' | tail -1))"
else
  fail "engine conformance" "$(echo "$out" | tail -5)"
fi

section "Rule 7 -- data documented"
for f in docs/DATA_SOURCES.md docs/DATA_LICENCES.md docs/PREEXISTING.md; do
  [ -s "$f" ] && pass "$f" || fail "$f missing"
done
"$PY" -c "import json; json.load(open('metadata.json'))" 2>/dev/null && pass "metadata.json is valid JSON" \
  || fail "metadata.json missing or invalid"

section "Rules 6, 8, 9 -- SAMPLE_MODE: real agent logic, no Zetaris, no Nightshift, no network"
# example -> extra run.py args (the identity confirmations input_examples/README.md documents)
declare -A ARGS=(
  [example_1]="--confirm patient:INT00015"
  [example_2]=""
  [example_3]="--confirm patient:INT00013"
  [example_4_learning_teach]=""
  [example_5_learning_learn]=""
)
ok_runs=0
for name in example_1 example_2 example_3 example_4_learning_teach example_5_learning_learn; do
  # shellcheck disable=SC2086
  if offline_env "$PY" run.py --input "input_examples/${name}.json" ${ARGS[$name]} \
       >"${WORK}/${name}.json" 2>"${WORK}/${name}.err"; then
    verdict="$("$PY" - "${WORK}/${name}.json" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1]))
problems = []
if r["status"] != "success":
    problems.append(f"status {r['status']}")
if not any("Not medical advice" in c for c in r["output"]["caveats"]):
    problems.append("no 'not medical advice' disclaimer")
models = {c["routed_model"] for c in r["model_calls"]}
if models - {"offline-heuristic"}:
    problems.append(f"a model other than offline-heuristic answered: {sorted(models)}")
if not r["sample_mode"]:
    problems.append("response not marked sample_mode")
print("; ".join(problems) or f"ok {len(r['findings'])} findings")
EOF
)"
    if [[ "$verdict" == ok* ]]; then
      pass "run.py ${name}: ${verdict#ok }"; ok_runs=$((ok_runs + 1))
    else
      fail "run.py ${name}" "$verdict"
    fi
  else
    fail "run.py ${name} exited non-zero" "$(tail -3 "${WORK}/${name}.err")"
  fi
done
[ "$ok_runs" -ge 3 ] && pass "at least 3 sample inputs run with real outputs (${ok_runs})" \
  || fail "fewer than 3 sample inputs succeeded (${ok_runs})"
distinct="$("$PY" - "$WORK" <<'EOF'
import glob, json, sys
seen = set()
for p in glob.glob(f"{sys.argv[1]}/example_*.json"):
    try:
        r = json.load(open(p))
    except ValueError:
        continue
    seen.add(json.dumps(sorted(f["id"] for f in r["findings"])))
print(len(seen))
EOF
)"
[ "${distinct:-0}" -ge 3 ] && pass "outputs change with inputs (${distinct} distinct finding sets)" \
  || fail "outputs do not change with inputs (${distinct:-0} distinct)"

section "Rule 8 -- POST /run works (SAMPLE_MODE server from the clone)"
PORT=8799
offline_env HOST=127.0.0.1 PORT="$PORT" "$PY" run.py serve >"${WORK}/serve.log" 2>&1 &
SERVER_PID=$!
api="$("$PY" - "$PORT" <<'EOF'
import json, sys, time, urllib.request
base = f"http://127.0.0.1:{sys.argv[1]}"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # talk to our server directly
for _ in range(60):
    try:
        status = json.load(opener.open(f"{base}/status", timeout=2))
        break
    except Exception:
        time.sleep(1)
else:
    print("server did not start"); sys.exit()
body = json.dumps({"patient_id": "MRN0000089"}).encode()
req = urllib.request.Request(f"{base}/run?wait=true", data=body, headers={"content-type": "application/json"})
r = json.load(opener.open(req, timeout=120))
print(f"ok status={r['status']} findings={len(r['findings'])} zetaris={status['zetaris']}"
      if r["status"] == "success" else f"run status {r['status']}")
EOF
)"
kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; SERVER_PID=""
[[ "$api" == ok* ]] && pass "POST /run?wait=true: ${api#ok }" || fail "POST /run" "${api} $(tail -3 "${WORK}/serve.log")"

section "Rule 6 -- output_examples from real runs"
if out="$(offline_env "$PY" -m pytest -q tests/unit/test_output_examples.py 2>&1)"; then
  pass "output_examples: real, differ by input, match the code ($(echo "$out" | grep -E -o '[0-9]+ passed' | tail -1))"
else
  fail "output_examples" "$(echo "$out" | tail -5)"
fi

section "Full test suite (offline)"
if out="$(offline_env "$PY" -m pytest -q 2>&1)"; then
  pass "pytest ($(echo "$out" | grep -E -o '[0-9]+ passed.*' | tail -1))"
else
  fail "pytest" "$(echo "$out" | grep -E '^(FAILED|ERROR)' | head -5)"
fi

section "Rule 8 -- Docker builds"
if [ "${VALIDATE_DOCKER:-1}" = "0" ]; then
  skip "docker build" "VALIDATE_DOCKER=0"
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if out="$(docker build -q -t medtrace-validate . 2>&1)"; then
    pass "docker build ($(echo "$out" | tail -1 | cut -c1-19))"
  else
    fail "docker build" "$(echo "$out" | tail -5)"
  fi
else
  skip "docker build" "no Docker daemon reachable here; run 'docker compose build' where Docker is available"
fi

echo
echo "== ${PASSED} passed, ${FAILED} failed, ${SKIPPED} skipped"
[ "$FAILED" -eq 0 ]
