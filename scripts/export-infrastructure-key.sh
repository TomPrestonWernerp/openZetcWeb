#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ENV="${1:-.env}"
OUTPUT_FILE="${2:-.openzetc/infrastructure-key.env}"
[[ "$SOURCE_ENV" = /* ]] || SOURCE_ENV="$REPO_ROOT/$SOURCE_ENV"
[[ "$OUTPUT_FILE" = /* ]] || OUTPUT_FILE="$REPO_ROOT/$OUTPUT_FILE"

get_env_value() {
  local file="$1" key="$2" value
  [[ -f "$file" ]] || return 0
  value="$(awk -v key="$key" 'index($0, key "=") == 1 {sub(/^[^=]*=/, ""); result=$0} END {print result}' "$file" | tr -d '\r')"
  if [[ "$value" == \"*\" && "$value" == *\" ]] || [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

key="$(get_env_value "$SOURCE_ENV" INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY)"
if [[ -z "$key" ]]; then
  key="$(get_env_value "$SOURCE_ENV" JWT_SECRET_KEY)"
fi
if [[ -z "$key" ]]; then
  echo "在 $SOURCE_ENV 中未找到 INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY 或 JWT_SECRET_KEY，无法导出迁移密钥。" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_FILE")"
umask 077
printf 'INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY=%s\n' "$key" > "$OUTPUT_FILE"
chmod 600 "$OUTPUT_FILE"
echo "已生成基础设施密钥迁移文件：$OUTPUT_FILE"
echo "上传完成后运行 scripts/deploy-prod.sh；脚本导入后会删除迁移文件。"
