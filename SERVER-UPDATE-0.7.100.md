# release/0.7.100 服务器更新说明

本压缩包只包含源码与构建配置，不包含 `.env`、`.env.prod`、数据库/对象存储数据卷、Git 目录、虚拟环境、依赖缓存或日志。

## 1. 解压覆盖代码

假设服务器项目位于 `/opt/openzetc/openZetcWeb`：

```bash
cd /opt/openzetc/openZetcWeb
cp -p .env.prod /tmp/openzetc.env.prod.backup
unzip -o /上传目录/openZetcWeb-release-0.7.100-runtime-fix-20260831-server.zip \
  -d /opt/openzetc/openZetcWeb
cmp -s .env.prod /tmp/openzetc.env.prod.backup || {
  echo ".env.prod 发生变化，停止部署"
  exit 1
}
```

压缩包不包含 `.env.prod`，因此正常解压不会覆盖服务器密码。`docker/volumes` 和 `saves` 也不会被覆盖。

## 2. 校验生产配置

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml config --quiet
```

## 3. 只更新 API 与 Worker

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml build api
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  up -d --no-deps --force-recreate api worker
```

API 与 Worker 共用 `openzetc-api:0.7.100` 镜像，因此只需构建一次。上述命令不会重新拉取或重建 PostgreSQL、Redis、MinIO、Milvus、etcd、Neo4j 和 Web，也不会删除数据卷。

由于本次锁定了 PyMilvus 2.5.x，第一次重建 API 镜像可能下载更新后的 Python 依赖；这与重新拉取中间件镜像无关。

## 4. 验证

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=300 api worker
curl -fsS http://127.0.0.1/api/system/health
```

重点确认日志中不再出现：

- `batch size is invalid, it should not be larger than 10`
- `Failed to connect to Neo4j: Unauthorized`
- 长时间重复的 `collection on recovering`

## 5. 可选：应用新的数据库鉴权健康检查

本次 Compose 还更新了 PostgreSQL、Neo4j 健康检查。可在维护窗口只重建这两个容器；会短暂中断连接，但复用现有镜像和数据卷，不会重新拉取或初始化数据：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml stop api worker
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  up -d --no-deps --force-recreate postgres graph
docker compose --env-file .env.prod -f docker-compose.prod.yml ps postgres graph
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  up -d --no-deps --force-recreate api worker
```

不要执行 `docker compose down -v`，该命令会删除数据卷。
