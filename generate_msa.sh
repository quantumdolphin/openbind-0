#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: generate_msa.sh REFERENCE_QUERY_JSON MSA_DIRECTORY" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUERY="$(realpath "$1")"
MSA_DIR="$(realpath -m "$2")"
IMAGE="openbind-dgx-spark:0.5.0"

if [[ ! -f "$QUERY" ]]; then
  echo "Reference query not found: $QUERY" >&2
  exit 1
fi
python3 - "$QUERY" <<'PY'
import json
import sys

with open(sys.argv[1]) as stream:
    queries = json.load(stream).get("queries", {})
if len(queries) != 1:
    raise SystemExit("Reference JSON must contain exactly one complex")
chains = next(iter(queries.values())).get("chains", [])
if sum(chain.get("molecule_type") == "protein" for chain in chains) != 2:
    raise SystemExit("Reference complex must contain exactly two protein chains")
PY
if [[ -e "$MSA_DIR/query_msa.json" ]]; then
  python3 "$ROOT/prepare_msa_queries.py" "$QUERY" "$MSA_DIR"
  echo "Saved MSAs already exist in: $MSA_DIR"
  exit 0
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Docker image not found: $IMAGE" >&2
  exit 1
fi

mkdir -p "$MSA_DIR" "$ROOT/workspace/cache"
echo "Generating MSAs for the reference complex with the ColabFold server..."
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/workspace -e OPENFOLD_CACHE=/workspace/cache \
  -v "$ROOT/workspace/cache:/workspace/cache" \
  -v "$QUERY:/input/query.json:ro" \
  -v "$MSA_DIR:/msas" \
  "$IMAGE" \
  run_openfold align-msa-server --query-json /input/query.json --output-dir /msas

python3 "$ROOT/prepare_msa_queries.py" "$QUERY" "$MSA_DIR"
echo "Saved MSAs and query_msa.json in: $MSA_DIR"
