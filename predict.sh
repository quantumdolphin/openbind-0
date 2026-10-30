#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: predict.sh [--check] [--msa-dir DIRECTORY] QUERY_JSON [OUTPUT_DIRECTORY]

Run an OpenBind-0 prediction with the local OpenFold3 Docker image.
  --check  Validate the input, checkpoint, Docker, and image without predicting.
  --msa-dir DIRECTORY  Reuse MSAs saved by generate_msa.sh for two protein chains.
  --help   Show this help.

If OUTPUT_DIRECTORY is omitted, results go to a timestamped folder under
workspace/outputs/.
EOF
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  usage
  exit 0
fi

CHECK_ONLY=false
MSA_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK_ONLY=true; shift ;;
    --msa-dir)
      if [[ $# -lt 2 ]]; then
        echo "--msa-dir requires a directory" >&2
        exit 2
      fi
      MSA_DIR="$2"
      shift 2
      ;;
    *) break ;;
  esac
done
if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUERY="$1"
OUTPUT="${2:-$ROOT/workspace/outputs/$(date +%Y%m%d-%H%M%S)}"
CHECKPOINT="$ROOT/weights/of3-ob-2025-06-30-174k.pt"
IMAGE="openbind-dgx-spark:0.5.0"
EXPECTED_SHA256="bd43301c011d5f87580d3e8b548658869433e4488399feb03035ba248f8e29e4"

echo "[1/6] Checking input and checkpoint"
if [[ ! -f "$QUERY" ]]; then
  echo "Query JSON not found: $QUERY" >&2
  exit 1
fi
if [[ ! -f "$CHECKPOINT" ]]; then
  echo "OpenBind checkpoint not found: $CHECKPOINT" >&2
  echo "Download it with: python3 $ROOT/download_weights.py" >&2
  exit 1
fi
if ! python3 -m json.tool "$QUERY" >/dev/null; then
  echo "Query is not valid JSON: $QUERY" >&2
  exit 1
fi
if ! printf '%s  %s\n' "$EXPECTED_SHA256" "$CHECKPOINT" | sha256sum --check --status; then
  echo "OpenBind checkpoint failed SHA-256 verification: $CHECKPOINT" >&2
  exit 1
fi

echo "[2/6] Checking Docker image"
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Docker is unavailable. Start Docker and check access to its daemon." >&2
  exit 1
fi
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Docker image not found: $IMAGE" >&2
  echo "Build it with: docker build --progress=plain -t $IMAGE $ROOT" >&2
  exit 1
fi

QUERY="$(realpath "$QUERY")"
OUTPUT="$(realpath -m "$OUTPUT")"
if [[ -n "$MSA_DIR" ]]; then
  MSA_DIR="$(realpath "$MSA_DIR")"
  python3 "$ROOT/prepare_msa_queries.py" "$QUERY" "$MSA_DIR"
fi
if [[ $CHECK_ONLY == true ]]; then
  echo "Preflight passed. Input: $QUERY"
  echo "Image: $IMAGE"
  echo "Checkpoint: $CHECKPOINT"
  echo "Output: $OUTPUT"
  if [[ -n "$MSA_DIR" ]]; then echo "Saved MSAs: $MSA_DIR"; fi
  exit 0
fi

echo "[3/6] Preparing output and cache folders"
mkdir -p "$OUTPUT" "$ROOT/workspace/cache"

QUERY_MOUNT=("-v" "$QUERY:/input/query.json:ro")
MSA_MOUNT=()
if [[ -n "$MSA_DIR" ]]; then
  python3 "$ROOT/prepare_msa_queries.py" "$QUERY" "$MSA_DIR" \
    --output "$OUTPUT/query_with_msa.json"
  QUERY_MOUNT=("-v" "$OUTPUT/query_with_msa.json:/input/query.json:ro")
  MSA_MOUNT=("-v" "$MSA_DIR:/msas:ro")
fi

echo "[4/6] Starting a GPU container from $IMAGE"
echo "[5/6] Running OpenFold3 with the OpenBind-0 checkpoint"
docker run --rm --gpus all --runtime=nvidia --shm-size=16g \
  --user "$(id -u):$(id -g)" \
  -e HOME=/workspace -e OPENFOLD_CACHE=/workspace/cache \
  -v "$ROOT/workspace/cache:/workspace/cache" \
  -v "$ROOT/weights:/weights:ro" \
  "${QUERY_MOUNT[@]}" \
  "${MSA_MOUNT[@]}" \
  -v "$OUTPUT:/output" \
  "$IMAGE" \
  run_openfold predict \
  --query-json /input/query.json \
  --inference-ckpt-path /weights/of3-ob-2025-06-30-174k.pt \
  --use-msa-server false \
  --use-templates false \
  --num-diffusion-samples 1 \
  --num-model-seeds 1 \
  --output-dir /output

echo "[6/6] Prediction finished; Docker removed the temporary container"
echo "Prediction output: $OUTPUT"
if [[ -f "$OUTPUT/summary.txt" ]]; then
  SUCCESSFUL="$(awk '/Successful Queries:/ {print $NF}' "$OUTPUT/summary.txt")"
  FAILED="$(awk '/Failed Queries:/ {print $NF}' "$OUTPUT/summary.txt")"
  if [[ -n "$SUCCESSFUL" && -n "$FAILED" ]]; then
    echo "Queries: $SUCCESSFUL successful, $FAILED failed"
    if [[ "$FAILED" != 0 ]]; then
      exit 1
    fi
  fi
fi
