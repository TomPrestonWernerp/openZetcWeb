#!/usr/bin/env bash
# Read-only probe: no release, load, reindex, or data mutation.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ $# -ne 1 || ! "$1" =~ ^kb_[a-zA-Z0-9_]+$ ]]; then
    echo "用法：bash scripts/check-milvus-search.sh kb_xxx" >&2
    exit 2
fi
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T api uv run --no-sync python - "$1" <<'PY'
import os
import sys
import time

from pymilvus import Collection, connections, utility

name = sys.argv[1]
connections.connect(
    alias="diagnostic",
    uri=os.environ.get("MILVUS_URI", "http://milvus:19530"),
    token=os.environ.get("MILVUS_TOKEN", ""),
    db_name=os.environ.get("MILVUS_DB_NAME", "default"),
    timeout=15,
)
print("server:", utility.get_server_version(using="diagnostic", timeout=15), flush=True)
print("collection:", name, flush=True)
print("state:", utility.load_state(name, using="diagnostic", timeout=15), flush=True)
collection = Collection(name, using="diagnostic")
print("scalar query starting", flush=True)
rows = collection.query(expr="", output_fields=["embedding"], limit=1, timeout=30)
if not rows:
    raise SystemExit("FAIL: collection has no visible vectors; cannot validate search")
metric = next(index.params["metric_type"] for index in collection.indexes if index.field_name == "embedding")
print("vector search starting:", metric, flush=True)
started = time.monotonic()
hits = collection.search(
    data=[rows[0]["embedding"]],
    anns_field="embedding",
    param={"metric_type": metric, "params": {"nprobe": 10}},
    limit=1,
    timeout=30,
)
if not hits or not hits[0]:
    raise SystemExit("FAIL: search returned no hit for an existing vector")
print(f"PASS: real vector search returned a hit in {time.monotonic() - started:.2f}s", flush=True)
print("This verifies Milvus only; verify query-test separately with the original question.", flush=True)
PY
