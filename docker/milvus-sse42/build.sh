#!/usr/bin/env bash
# Run on Linux x86-64 with gcc and Docker installed. Does not restart services.
set -euo pipefail
[[ "$(uname -m)" == "x86_64" ]] || { echo "Requires Linux x86-64" >&2; exit 1; }
command -v gcc >/dev/null
command -v docker >/dev/null
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build_dir="$(mktemp -d -t openzetc-milvus-sse42.XXXXXXXX)"
trap 'rm -f -- "$build_dir/libopenzetc-cpu-compat.so" "$build_dir/Dockerfile" "$build_dir/user.yaml"; rmdir -- "$build_dir"' EXIT
gcc -shared -fPIC -O2 -march=x86-64 -mno-avx -mno-avx2 -mno-avx512f \
    -o "$build_dir/libopenzetc-cpu-compat.so" "$source_dir/compat.c"
cp "$source_dir/Dockerfile" "$source_dir/user.yaml" "$build_dir/"
docker build -t openzetc-milvus:2.5.6-sse42 "$build_dir"
