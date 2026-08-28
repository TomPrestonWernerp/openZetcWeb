# openZetc 0.7.100 Linux 离线部署

本压缩包用于服务器无法直接拉取 Git 代码时部署 `release/0.7.100`。包内已经包含：

- 当前 Web、API、Worker 源码与生产 Docker Compose 配置；
- 已配置完成的 `.env.prod` 与本地 `.env`，运维不需要手工填写密钥；
- `docker/nginx/nginx/` 下的 Nginx 配置和 HTTPS 证书；
- `.openzetc/infrastructure-key.env` 一次性密钥迁移文件；
- 对象存储、向量数据库、图数据库配置读取的密钥不一致容错修复。

> 本包包含基础设施配置迁移密钥和 HTTPS 私钥，只能通过受控渠道交给运维，部署成功后应删除服务器上的原始压缩包。

## 一、覆盖现有部署

以下命令同时适用于首次部署和覆盖现有部署，假设压缩包位于 `/tmp`：

```bash
sudo mkdir -p /opt/openzetc
sudo chown -R "$(id -un):$(id -gn)" /opt/openzetc

# 如服务器已有部署，自动备份原生产环境变量。
if [ -f /opt/openzetc/openZetcWeb/.env.prod ]; then
  cp /opt/openzetc/openZetcWeb/.env.prod \
    "/opt/openzetc/openZetcWeb/.env.prod.bak.$(date +%Y%m%d%H%M%S)"
fi

# 覆盖当前代码和环境配置；压缩包不包含 docker/volumes，不会覆盖已有数据卷。
tar -xzf /tmp/openzetc-0.7.100-linux-full.tar.gz -C /opt/openzetc

cd /opt/openzetc/openZetcWeb
chmod +x scripts/*.sh
bash scripts/deploy-prod.sh
```

不需要编辑 `.env.prod`，也不需要手工复制任何密钥。

不要执行 `docker compose down -v`，也不要删除 `docker/volumes/`。

## 二、密钥错误修复机制

`scripts/deploy-prod.sh` 会自动执行以下操作：

1. 备份已有 `.env.prod`；
2. 从 `.openzetc/infrastructure-key.env` 读取本地原加密密钥；
3. 只设置 `INFRASTRUCTURE_CONFIG_ENCRYPTION_KEY`，不会覆盖服务器原来的 `JWT_SECRET_KEY`；
4. 重建并启动生产容器；
5. 确认 API 与 Worker 使用相同密钥；
6. 直接读取 PostgreSQL 中对象存储、向量数据库、图数据库配置，并检查所有历史密文是否可解密；
7. 只有验证全部通过后才删除一次性迁移密钥文件。

如果验证失败，脚本会非零退出，并保留 `.openzetc/infrastructure-key.env` 供排查，不会把失败部署报告为成功。

## 三、部署后检查

```bash
cd /opt/openzetc/openZetcWeb

docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=200 api worker web
```

页面检查：

1. 登录系统；
2. 打开“用户设置 → 基本设置”；
3. 对象存储、向量数据库、图数据库的配置来源应正常加载；
4. 浏览器请求 `/api/system/infrastructure-config` 不应返回 500；
5. 新建知识库，并确认能够读取已激活的对象存储和向量数据库配置。

## 四、失败回滚

如需恢复环境变量：

```bash
cd /opt/openzetc/openZetcWeb
cp .env.prod.bak.YYYYMMDDHHMMSS .env.prod
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build --force-recreate api worker web
```

完整部署和后续 Web 更新说明见 `docs/advanced/linux-deployment-0.7.100.md`。
