#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_ENV="${TARGET_ENV:-$REPO_ROOT/.env.prod}"
TRANSFER_ENV="${TRANSFER_ENV:-$REPO_ROOT/.openzetc/infrastructure-key.env}"
LOCAL_ENV="${LOCAL_ENV:-$REPO_ROOT/.env}"
TEMPLATE_ENV="$REPO_ROOT/.env.template"

get_env_value() {
  local file="$1" key="$2" value
  [[ -f "$file" ]] || return 0
  value="$(awk -v key="$key" 'index($0, key "=") == 1 {sub(/^[^=]*=/, ""); result=$0} END {print result}' "$file" | tr -d '\r')"
  if [[ "$value" == \"*\" && "$value" == *\" ]] || [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

set_env_value() {
  local file="$1" key="$2" value="$3" temp
  temp="$(mktemp "${file}.tmp.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN {updated=0}
    index($0, key "=") == 1 {
      if (!updated) print key "=" value
      updated=1
      next
    }
    {print}
    END {if (!updated) print key "=" value}
  ' "$file" > "$temp"
  chmod 600 "$temp"
  mv -f "$temp" "$file"
}

new_hex() {
  openssl rand -hex "${1:-32}"
}

new_uuid() {
  if command -v uuidgen >/dev/null 2>&1; then
    uuidgen
  elif [[ -r /proc/sys/kernel/random/uuid ]]; then
    cat /proc/sys/kernel/random/uuid
  else
    local raw
    raw="$(openssl rand -hex 16)"
    printf '%s-%s-%s-%s-%s\n' "${raw:0:8}" "${raw:8:4}" "${raw:12:4}" "${raw:16:4}" "${raw:20:12}"
  fi
}

if [[ ! -f "$TARGET_ENV" ]]; then
  if [[ ! -f "$TEMPLATE_ENV" ]]; then
    echo "缺少生产环境模板：$TEMPLATE_ENV" >&2
    exit 1
  fi
  cp "$TEMPLATE_ENV" "$TARGET_ENV"
  chmod 600 "$TARGET_ENV"
  echo "已从模板创建 $TARGET_ENV"
else
  backup="${TARGET_ENV}.bak.$(date +%Y%m%d%H%M%S)"
  cp -p "$TARGET_ENV" "$backup"
  chmod 600 "$backup"
  echo "已备份现有生产配置：$backup"
fi

set_if_missing() {
  local key="$1" value="$2"
  if [[ -z "$(get_env_value "$TARGET_ENV" "$key")" ]]; then
    set_env_value "$TARGET_ENV" "$key" "$value"
  fi
}

set_env_value "$TARGET_ENV" OPENZETC_VERSION "0.7.100"
set_env_value "$TARGET_ENV" OPENZETC_ENV "production"
set_if_missing JWT_SECRET_KEY "$(new_hex 32)"
set_if_missing OPENZETC_INSTANCE_ID "$(new_uuid)"
set_if_missing POSTGRES_PASSWORD "$(new_hex 24)"
set_if_missing MINIO_ACCESS_KEY "openzetc$(new_hex 6)"
set_if_missing MINIO_SECRET_KEY "$(new_hex 24)"
set_if_missing NEO4J_PASSWORD "$(new_hex 24)"
set_if_missing SANDBOX_PROVISIONER_TOKEN "$(new_hex 32)"

migration_key=""
if [[ -f "$TRANSFER_ENV" ]]; then
  migration_key="$(get_env_value "$TRANSFER_ENV" INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY)"
  [[ -n "$migration_key" ]] || {
    echo "迁移文件存在但不包含有效密钥：$TRANSFER_ENV" >&2
    exit 1
  }
  echo "检测到独立的基础设施密钥迁移文件。"
elif [[ -f "$LOCAL_ENV" ]]; then
  migration_key="$(get_env_value "$LOCAL_ENV" INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY)"
  [[ -n "$migration_key" ]] || migration_key="$(get_env_value "$LOCAL_ENV" JWT_SECRET_KEY)"
  [[ -z "$migration_key" ]] || echo "检测到随代码上传的本地环境密钥。"
fi

current_key="$(get_env_value "$TARGET_ENV" INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY)"
if [[ -n "$migration_key" ]]; then
  set_env_value "$TARGET_ENV" INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY "$migration_key"
elif [[ -z "$current_key" ]]; then
  # 全新部署没有历史密文时可以生成新密钥；迁移数据库时应提供迁移文件。
  set_env_value "$TARGET_ENV" INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY "$(new_hex 32)"
  echo "警告：未发现源环境密钥，已为全新部署生成基础设施加密密钥。" >&2
  echo "如果 PostgreSQL 来自其他环境，请停止部署并先运行 export-infrastructure-key 脚本。" >&2
fi

chmod 600 "$TARGET_ENV"
echo "生产环境配置已准备完成：$TARGET_ENV"
