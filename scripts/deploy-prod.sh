#!/usr/bin/env bash
# Linux executes this file directly, so keep its line endings as LF.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

COMPOSE=(docker compose --env-file .env.prod -f docker-compose.prod.yml)
TRANSFER_ENV="$REPO_ROOT/.openzetc/infrastructure-key.env"

"$REPO_ROOT/scripts/prepare-prod-env.sh"

required_files=(
  docker/nginx/nginx/nginx.conf
  docker/nginx/nginx/default.conf
  docker/nginx/nginx/cert/scs1776824001002_.zjshjkj.com_server.crt
  docker/nginx/nginx/cert/scs1776824001002_.zjshjkj.com_server.key
)
for required_file in "${required_files[@]}"; do
  if [[ ! -f "$required_file" ]]; then
    echo "缺少生产部署文件：$required_file" >&2
    exit 1
  fi
done

"${COMPOSE[@]}" config --quiet
# Build before interrupting application services. Infrastructure upgrades are
# separate maintenance operations; ordinary code updates preserve containers.
"${COMPOSE[@]}" build api worker web
"${COMPOSE[@]}" up -d --no-recreate --wait --wait-timeout 300 etcd minio postgres redis graph milvus sandbox-provisioner
"${COMPOSE[@]}" up -d --no-deps --force-recreate --wait --wait-timeout 300 api worker web
"${COMPOSE[@]}" ps

api_hash="$("${COMPOSE[@]}" exec -T api python -c 'import hashlib,os; print(hashlib.sha256(os.environ["INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY"].encode()).hexdigest())')"
worker_hash="$("${COMPOSE[@]}" exec -T worker python -c 'import hashlib,os; print(hashlib.sha256(os.environ["INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY"].encode()).hexdigest())')"
if [[ "$api_hash" != "$worker_hash" ]]; then
  echo "API 与 Worker 的基础设施加密密钥不一致，部署终止。" >&2
  exit 1
fi

"${COMPOSE[@]}" exec -T api python - <<'PY'
import asyncio

from openzetc.services.infrastructure_config_service import get_infrastructure_config


async def verify() -> None:
    result = await get_infrastructure_config()
    warnings = result.get("_warnings", [])
    if warnings:
        failed = [
            f"{item.get('section', 'unknown')}.{','.join(item.get('fields', []))}"
            for item in warnings
        ]
        raise SystemExit(
            "基础设施配置密钥校验失败：" + "; ".join(failed)
            + "。请确认迁移包中的加密密钥来自源环境。"
        )

    source_counts = {
        section: len(items)
        for section, items in result.get("_sources", {}).items()
    }
    print(f"基础设施配置解密校验通过：source_counts={source_counts}")


asyncio.run(verify())
PY

if [[ -f "$TRANSFER_ENV" ]]; then
  rm -f "$TRANSFER_ENV"
  echo "基础设施密钥已导入 .env.prod，迁移文件已安全删除。"
fi

echo "应用部署完成。配置密钥指纹：${api_hash:0:12}（仅哈希，不是原密钥）"
echo "容器健康不代表知识库检索正常，请执行：bash scripts/check-milvus-search.sh <知识库ID>"
echo "请检查：${COMPOSE[*]} logs --tail=200 api worker web"
