# release/0.7.100 服务器更新说明（保留数据）

本文用于运维在已有 Linux 部署上更新系统。当前线上知识库检索故障已通过 Milvus SSE4.2 兼容镜像修复；后续按本文更新不会删除或重新导入知识库数据。

服务器示例目录：/opt/openzetc/openZetcWeb

## 一、更新前必须确认

    cd /opt/openzetc/openZetcWeb
    git status --short

工作区如有人工修改，先备份并停止更新。生产环境变量文件 .env.prod、证书目录和 docker/volumes/ 必须保留。

本项目的持久化数据目录包括：

- docker/volumes/postgresql/：业务数据库和系统配置；
- docker/volumes/openzetc/：对象存储文件；
- docker/volumes/milvus/：向量库、MinIO 和 etcd 数据；
- docker/volumes/neo4j/：知识图谱数据；
- docker/volumes/redis/：任务和缓存数据。

禁止执行 docker compose down -v，禁止删除上述目录。

## 二、压缩包覆盖方式

压缩包不应包含 .env.prod、.env、docker/volumes/、.git/、日志和虚拟环境。假设压缩包已上传到 /tmp：

    cd /opt/openzetc/openZetcWeb
    cp -p .env.prod ".env.prod.bak-$(date +%Y%m%d%H%M%S)"

    unzip -o /tmp/openZetcWeb-release-0.7.100.zip \
      -d /opt/openzetc/openZetcWeb

覆盖后检查生产变量未被替换：

    test -f .env.prod
    chmod 600 .env.prod
    test -d docker/volumes

如果使用 tar 包，使用 tar -xzf 包名 -C /opt/openzetc/openZetcWeb，并同样保留以上三个路径。

## 三、首次应用检索兼容修复

受影响的虚拟机通常只有 SSE4.2，没有可用 AVX/AVX2/AVX512。Milvus 2.5.6 在这种环境会错误选择 AVX 位图实现，日志出现 invalid opcode，查询进程退出。修复文件位于：

    docker/milvus-sse42/build.sh
    docker/milvus-sse42/compat.c
    docker/milvus-sse42/Dockerfile
    docker/milvus-sse42/user.yaml

仅需在服务器首次执行一次。

### 3.1 设置镜像变量

    if grep -q '^MILVUS_IMAGE=' .env.prod; then
      sed -i 's#^MILVUS_IMAGE=.*#MILVUS_IMAGE=openzetc-milvus:2.5.6-sse42#' .env.prod
    else
      printf '\nMILVUS_IMAGE=openzetc-milvus:2.5.6-sse42\n' >> .env.prod
    fi
    chmod 600 .env.prod

### 3.2 构建兼容镜像

构建机需要 Linux x86-64、gcc、Docker 和 milvusdb/milvus:v2.5.6 基础镜像：

    chmod +x docker/milvus-sse42/build.sh
    bash docker/milvus-sse42/build.sh

构建过程只生成镜像，不会停止容器，也不会访问或修改数据卷。

### 3.3 仅替换 Milvus 容器

    docker compose --env-file .env.prod -f docker-compose.prod.yml config --quiet

    docker compose --env-file .env.prod -f docker-compose.prod.yml \
      up -d --no-deps --force-recreate --wait --wait-timeout 120 milvus

该命令复用现有 Milvus、MinIO 和 etcd 数据。不要使用 down -v 或删除 docker/volumes/milvus/。

### 3.4 首次修复验收

    docker inspect -f 'image={{.Config.Image}} restart={{.RestartCount}} status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{end}}' milvus

预期镜像为 openzetc-milvus:2.5.6-sse42，状态 running，健康状态 healthy，重启次数为 0。

    bash scripts/check-milvus-search.sh kb_f8smdhu85m

预期出现 PASS: real vector search returned a hit。

## 四、更新 API、Worker、Web

### 4.1 Git 更新代码

    cd /opt/openzetc/openZetcWeb
    git fetch origin
    git pull --ff-only origin release/0.7.100

### 4.2 校验兼容变量没有丢失

    grep -q '^MILVUS_IMAGE=openzetc-milvus:2.5.6-sse42$' .env.prod

如果该命令返回非零，先按第三节重新设置，不要继续部署。

### 4.3 执行应用部署脚本

    chmod +x scripts/*.sh
    bash scripts/deploy-prod.sh

脚本会先构建 API、Worker、Web，再只重建这三个应用容器；PostgreSQL、Redis、MinIO、etcd、Neo4j 和 Milvus 默认保留现有容器和数据。

## 五、只更新 Web 前端

适合只修改 web/、Nginx 或 Web Dockerfile 的版本：

    docker compose --env-file .env.prod -f docker-compose.prod.yml build web

    docker compose --env-file .env.prod -f docker-compose.prod.yml \
      up -d --no-deps web

该流程不重启 API、Worker、Milvus 和数据库。

## 六、部署后完整检查

    docker compose --env-file .env.prod -f docker-compose.prod.yml ps

    docker compose --env-file .env.prod -f docker-compose.prod.yml \
      logs --tail=200 api worker web milvus

    curl -fsS http://127.0.0.1/api/system/health

然后登录 https://openzetc.zjshjkj.com，打开目标知识库的“检索测试”，分别测试向量和混合检索。

Milvus 日志不应出现：

- invalid opcode；
- panic 或 segmentation fault；
- 长时间重复 collection on recovering。

如果接口返回 HTTP 200 但结果为空，检查相似度阈值、检索模式和目标集合是否有向量；这不等同于 Milvus 崩溃。

## 七、备份与回滚

版本升级前至少备份 PostgreSQL：

    mkdir -p backups
    BACKUP_STAMP=$(date +%Y%m%d-%H%M%S)
    docker compose --env-file .env.prod -f docker-compose.prod.yml \
      exec -T postgres sh -c \
      'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
      > "backups/openzetc-${BACKUP_STAMP}.dump"

同时备份 docker/volumes/ 和 .env.prod 到服务器之外的受控位置。

应用代码回滚时，保留 MILVUS_IMAGE=openzetc-milvus:2.5.6-sse42。只有为了故障对比才切回原 Milvus 镜像：

    sed -i 's#^MILVUS_IMAGE=.*#MILVUS_IMAGE=milvusdb/milvus:v2.5.6#' .env.prod

    docker compose --env-file .env.prod -f docker-compose.prod.yml \
      up -d --no-deps --force-recreate --wait --wait-timeout 120 milvus

原镜像在该虚拟机上可能再次触发 invalid opcode，不建议长期使用。恢复时将变量改回兼容镜像并重复第三节。

## 八、后续升级约束

- 兼容镜像固定基于 Milvus 2.5.6；升级 Milvus 前必须重新验证 CPU 分派和真实向量检索；
- 不要在生产机直接运行 docker compose down -v；
- 不要清空、移动或重新初始化任何 docker/volumes/ 子目录；
- 不要把 .env.prod、JWT、数据库密码或 API Key 提交到 Git；
- 部署完成后保留本文件、版本号、提交号和验收结果，便于下一次迭代。
