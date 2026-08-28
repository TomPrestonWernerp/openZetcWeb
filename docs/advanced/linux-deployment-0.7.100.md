# Linux 部署与 Web 版本更新（release/0.7.100）

本文用于在 Linux 服务器首次部署 `release/0.7.100`，以及后续只更新 Web 前端。生产环境统一使用 `docker-compose.prod.yml`；PostgreSQL、MinIO、Milvus、Neo4j 和 Redis 数据均通过 `docker/volumes/` 下的宿主机目录持久化。

> 切换分支、删除目录或升级服务前必须先备份。不要执行 `docker compose down -v`，也不要删除 `docker/volumes/`。

## 1. 部署前准备

### 1.1 服务器建议

- Linux x86_64/amd64，建议 8 核 CPU、16 GB 内存、100 GB 以上可用磁盘；实际容量应按知识库文件、向量和图谱规模预留。
- Docker Engine 24+、Docker Compose 2.20+、Git、OpenSSL。
- 默认只需放行 SSH 和 Web 的 `80` 端口；MinIO、Milvus、Neo4j、PostgreSQL、Redis 不应直接暴露到公网。
- MinerU、PaddleOCR GPU 服务属于可选 `all` profile，只有服务器已安装 NVIDIA 驱动及 NVIDIA Container Toolkit 时才启用。

Docker Engine 和 Compose 请通过 Docker 官方软件源安装，不建议在生产机使用仅适合测试环境的便捷安装脚本：

- [Docker Engine 官方安装说明](https://docs.docker.com/engine/install/)
- [Docker Compose Plugin 官方安装说明](https://docs.docker.com/compose/install/linux/)

安装后检查：

```bash
docker version
docker compose version
git --version
```

### 1.2 获取代码

下面以 `/opt/openzetc/openZetcWeb` 为部署目录。私有仓库需要先给服务器配置 GitHub Deploy Key 或其他只读凭据。

```bash
sudo mkdir -p /opt/openzetc
sudo chown -R "$(id -un):$(id -gn)" /opt/openzetc
cd /opt/openzetc
git clone --branch release/0.7.100 --single-branch \
  git@github.com:TomPrestonWernerp/openZetcWeb.git
cd openZetcWeb
git status --short --branch
```

若服务器使用 HTTPS 凭据，将 clone 地址换成：

```text
https://github.com/TomPrestonWernerp/openZetcWeb.git
```

### 1.3 服务器无法访问 GitHub 时离线更新

离线包必须同时包含当前分支代码、生产 Nginx 配置和证书。若 PostgreSQL 是从本地迁移到
服务器，还必须安全携带本地用于加密基础设施配置的密钥；只迁移数据库无法解密对象存储
`Secret Key`、向量数据库 `Token` 和图数据库 `Password`。

在本地 Windows 项目目录执行（脚本不会显示密钥原文）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/export-infrastructure-key.ps1
tar -czf openzetc-0.7.100-offline.tar.gz `
  --exclude=.git --exclude=.env --exclude=.env.prod `
  --exclude=node_modules --exclude=docker/volumes .
```

生成的 `.openzetc/infrastructure-key.env` 仅用于一次迁移，已经被 Git 忽略。将离线包上传
到服务器后覆盖代码文件，但保留服务器原有的 `.env.prod` 和 `docker/volumes/`：

```bash
cd /opt/openzetc/openZetcWeb
cp .env.prod ".env.prod.bak.$(date +%Y%m%d%H%M%S)"
tar -xzf /上传目录/openzetc-0.7.100-offline.tar.gz
bash scripts/deploy-prod.sh
```

部署脚本会在容器启动后直接读取对象存储、向量数据库和图数据库配置表，验证历史密文能否用当前 `INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY` 解密。任意密钥无法解密时部署会直接失败，且不会删除一次性迁移文件；只有三类配置全部校验通过后才会完成部署。

部署脚本只把迁移密钥写入服务器现有 `.env.prod` 的
`INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY`，不会覆盖服务器的 `JWT_SECRET_KEY`、数据库密码或
其他已有配置；API、Worker 和 Web 验证成功后会删除一次性迁移文件。

## 2. 配置生产环境

复制模板并限制权限：

```bash
cp .env.template .env.prod
chmod 600 .env.prod
```

使用 `openssl rand -hex 32` 分别生成不同的随机值，使用 `uuidgen` 生成实例 ID。编辑 `.env.prod`，至少确认以下项目：

```dotenv
OPENZETC_VERSION=0.7.100
OPENZETC_ENV=production

JWT_SECRET_KEY=<独立随机值：openssl rand -hex 32>
OPENZETC_INSTANCE_ID=<固定 UUID：uuidgen>
INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY=<独立随机值：openssl rand -hex 32>

POSTGRES_PASSWORD=<强密码>
MINIO_ACCESS_KEY=<MinIO 账号>
MINIO_SECRET_KEY=<MinIO 密码/Secret Key>
NEO4J_PASSWORD=<强密码>
SANDBOX_PROVISIONER_TOKEN=<独立随机值，至少 32 个字符>

# 同域部署可留空；前后端跨域时填写实际来源，多个来源用逗号分隔。
OPENZETC_CORS_ORIGINS=
```

注意：

- `.env.prod` 不得提交到 Git，也不要在工单、聊天或截图中暴露。
- `JWT_SECRET_KEY`、`OPENZETC_INSTANCE_ID` 和 `INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY` 部署后应固定保存。
- 已保存对象存储、向量数据库或图数据库配置后，不能直接更换 `INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY`，否则数据库内的密文将无法解密。
- 模型 API Key 可在首次登录后的“用户设置”中配置，不需要写入镜像。
- 第三方对象存储、向量数据库和图数据库配置保存在 PostgreSQL；Docker 重启不会丢失，但 PostgreSQL 与相关数据卷仍必须纳入备份。

### 从其他环境迁移 PostgreSQL 时的加密密钥

对象存储的 `Secret Key`、托管向量库的 `Token` 和图数据库的 `Password` 在 PostgreSQL
中以密文保存。迁移数据库时必须同时把源环境 `.env.prod` 中的
`INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY` 安全复制到目标环境；不能在目标服务器重新生成。
如果源环境没有显式配置该变量，旧数据实际使用源环境的 `JWT_SECRET_KEY` 加密；此时应把
源环境的 `JWT_SECRET_KEY` 值写入目标环境的 `INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY`，
不要因此替换目标环境正在使用的 JWT 密钥。

如果数据库已经迁移但原密钥无法取得，新版本仍会加载三张配置表中的来源及非敏感字段，
并在“基础设置 → 存储与数据库”中把对应来源标记为“需要重新填写密钥”。重新填写该来源的
敏感字段并保存后，系统会用目标服务器当前的加密密钥重新加密；测试连接成功后再激活。
在修复完成前，系统不会把无法解密的来源应用为运行时连接。

可用以下命令确认 API 和 worker 实际拿到了同一个配置值（只输出哈希，不暴露原文）：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec api \
  python -c 'import hashlib,os; print(hashlib.sha256(os.environ["INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY"].encode()).hexdigest())'
docker compose --env-file .env.prod -f docker-compose.prod.yml exec worker \
  python -c 'import hashlib,os; print(hashlib.sha256(os.environ["INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY"].encode()).hexdigest())'
```

两行哈希必须一致，并且容器重建后不能变化。

生产 Compose 会把 `INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY` 作为启动必填项，缺失时会在
创建容器前直接报错。这样可以避免服务表面启动成功、访问配置页面时才返回 500。

验证 Compose 配置。后续所有生产命令都应显式携带 `--env-file .env.prod`，确保镜像标签和变量插值使用生产配置：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml config >/dev/null
```

## 3. 首次启动

推荐使用部署脚本完成环境检查、Nginx/证书路径检查、构建、启动和 API/Worker 密钥一致性
校验：

```bash
bash scripts/deploy-prod.sh
```

也可以手工构建并启动核心服务：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  up -d --build
```

API 和 Worker 会等待 PostgreSQL、Redis、MinIO、Milvus、Neo4j 及沙箱服务健康后再启动，
避免 Milvus Proxy 尚未就绪时出现 `service unavailable`。

首次构建和拉取镜像耗时较长。查看状态和日志：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f --tail=200 api
```

另开一个终端验证：

```bash
curl -fsS http://127.0.0.1/api/system/health
curl -I http://127.0.0.1/
```

浏览器访问 `http://服务器IP/`。全新数据库会进入初始管理员创建流程；后端启动时会幂等创建并补齐当前版本所需表结构。

如果要启用可选 GPU 解析服务：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  --profile all up -d --build
```

没有 GPU 环境时不要添加 `--profile all`。

## 4. 数据目录与备份

生产数据主要位于：

| 数据 | 宿主机目录 |
| --- | --- |
| PostgreSQL 业务与配置数据 | `docker/volumes/postgresql/` |
| MinIO 对象文件 | `docker/volumes/openzetc/` |
| Milvus 与其依赖数据 | `docker/volumes/milvus/` |
| Neo4j 图数据与日志 | `docker/volumes/neo4j/` |
| Redis 数据 | `docker/volumes/redis/` |
| 模型缓存 | `docker/volumes/models/` |

### 4.1 PostgreSQL 在线逻辑备份

```bash
mkdir -p backups
DEPLOY_STAMP=$(date +%Y%m%d-%H%M%S)
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "backups/openzetc-${DEPLOY_STAMP}.dump"
```

确认文件不是空文件：

```bash
ls -lh backups/
```

### 4.2 全量数据卷快照（有短暂停机）

此方式能同时保留对象、向量、图谱和关系数据，适合大版本升级前执行：

```bash
mkdir -p backups
DEPLOY_STAMP=$(date +%Y%m%d-%H%M%S)
docker compose --env-file .env.prod -f docker-compose.prod.yml down
tar -czf "backups/openzetc-volumes-${DEPLOY_STAMP}.tar.gz" docker/volumes
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

请将 `.env.prod`、数据库逻辑备份和数据卷快照复制到服务器之外的备份位置。恢复演练应在独立服务器或独立目录完成。

## 5. 后续只更新 Web 前端

以下流程只重建并替换 `web` 容器，不重启 API、Worker 和数据库，适合改动仅位于 `frontend/`、`docker/nginx/` 或 `docker/web.Dockerfile` 的情况。

### 5.1 更新前检查

```bash
cd /opt/openzetc/openZetcWeb
git switch release/0.7.100
git status --short
DEPLOY_COMMIT_BEFORE=$(git rev-parse HEAD)
echo "$DEPLOY_COMMIT_BEFORE"
```

`git status --short` 必须为空。如果服务器目录存在人工修改，先备份并处理，不要直接覆盖。

### 5.2 拉取并仅发布 Web

```bash
git fetch origin
git pull --ff-only origin release/0.7.100

docker compose --env-file .env.prod -f docker-compose.prod.yml build web
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  up -d --no-deps web
```

验证：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps web
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=100 web
curl -I http://127.0.0.1/
curl -fsS http://127.0.0.1/api/system/health
```

浏览器若仍显示旧页面，先强制刷新或清除站点缓存；不要因此重启数据库服务。

### 5.3 Web 回滚

若新 Web 有问题，使用更新前记录的提交重新构建：

```bash
git switch --detach "$DEPLOY_COMMIT_BEFORE"
docker compose --env-file .env.prod -f docker-compose.prod.yml build web
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  up -d --no-deps web
git switch release/0.7.100
```

此时运行中的 Web 是旧提交构建的镜像，工作目录已回到发布分支。修复代码推送后，再执行 5.2 的更新流程。

## 6. 完整版本升级

如果更新包含后端、Worker、Compose、环境变量、数据库结构或基础设施配置，不能只更新 Web。先做第 4 节备份，再执行：

```bash
cd /opt/openzetc/openZetcWeb
git switch release/0.7.100
git status --short
git fetch origin
git pull --ff-only origin release/0.7.100

docker compose --env-file .env.prod -f docker-compose.prod.yml config >/dev/null
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

升级后同时检查 API、Worker、Web、PostgreSQL、MinIO、Milvus 和 Neo4j 日志：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  logs --tail=200 api worker web postgres minio milvus graph
```

切换到后续新发布分支时，还要同步修改 `.env.prod` 中的 `OPENZETC_VERSION`。不要跨版本复用未经核对的 Compose 文件或环境变量模板。

## 7. 常见问题

### 页面显示 502 Bad Gateway

先检查 API 是否健康以及是否仍在初始化：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps api postgres redis
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=300 api
curl -v http://127.0.0.1/api/system/health
```

常见原因包括 `.env.prod` 必填项缺失、PostgreSQL 尚未就绪、旧数据库密码与新 `.env.prod` 不一致，或 API 启动时连接 MinIO/Milvus/Neo4j 失败。

### 端口 80 已被占用

检查占用者：

```bash
sudo ss -lntp | grep ':80 '
```

项目生产 Compose 默认将宿主机 `80` 映射到 Web 容器。若服务器已有 Nginx/Caddy，应先规划反向代理端口并调整 `web.ports`，不要让两个服务同时监听 80。

### 查看服务状态与重启单个服务

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml restart api
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f --tail=200 api
```

### 磁盘空间检查

```bash
df -h
docker system df
du -sh docker/volumes/*
```

清理镜像前先确认不再需要回滚。不要使用会删除数据卷的清理选项。
