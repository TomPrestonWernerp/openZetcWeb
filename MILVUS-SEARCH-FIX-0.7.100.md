# 知识库检索故障修复与运维操作说明

本文记录 release/0.7.100 在线环境知识库检索无结果、502/503，以及 Milvus
invalid opcode 崩溃的定位结论和修复方法。适用于服务器项目目录
/opt/openzetc/openZetcWeb。文档不包含任何密码、令牌或私钥。

## 1. 故障结论

本次故障不是网页请求地址或知识库数据丢失，而是服务器虚拟机 CPU 指令集暴露不完整：

- 服务器可见 SSE4.2，但没有可用的 AVX、AVX2、AVX512 状态；
- Milvus 2.5.6 的 bitset CPU 分派只检查 CPUID，没有检查操作系统是否允许 AVX 指令；
- 查询触发 AVX512 bitset 指令后，Milvus 进程因 invalid opcode 退出（退出码 132）；
- API 只能得到 Milvus 连接/恢复错误，网页因此显示检索服务暂不可用或没有结果。

Milvus 官方源码见：
https://github.com/milvus-io/milvus/blob/v2.5.6/internal/core/src/bitset/detail/platform/x86/instruction_set.cpp

仅设置 common.simdType: sse4_2 只能限制 FAISS，不能阻止 bitset 的 AVX 分派。因此本次使用兼容镜像：

1. user.yaml 将 FAISS 固定为 SSE4.2；
2. compat.c 让 Milvus 2.5.6 的 bitset AVX2/AVX512 能力函数返回 false；
3. Milvus 回退到基线 bitset 实现，复用原有 PostgreSQL、MinIO、Milvus、Neo4j 数据卷。

该方案牺牲部分 SIMD 性能，只用于确认存在该指令集问题的服务器。不要在未验证符号兼容性前直接升级 Milvus 基础版本。

## 2. 已应用的线上配置

线上服务器已经完成以下配置：

    镜像：openzetc-milvus:2.5.6-sse42
    .env.prod：MILVUS_IMAGE=openzetc-milvus:2.5.6-sse42
    Compose：image: ${MILVUS_IMAGE:-milvusdb/milvus:v2.5.6}

兼容镜像由 docker/milvus-sse42/build.sh 在 Linux x86-64 上构建，随后仅重建 Milvus 容器。没有执行 down -v，没有删除 docker/volumes/，没有重新导入文档。

修复后的验收结果：

- Milvus 容器 healthy，重启次数为 0；
- 域名向量检索接口 HTTP 200，返回 6 条；
- 域名混合检索接口 HTTP 200，返回 10 条；
- 重建后没有新的 invalid opcode、panic 或 segmentation fault；
- 本地部署脚本回归测试 3 项通过。

## 3. 运维首次修复/迁移步骤

以下步骤只需在受影响服务器执行一次。执行前确认目录和备份路径，不要把密码写入命令或日志。

### 3.1 进入项目并备份生产变量

    cd /opt/openzetc/openZetcWeb
    cp -p .env.prod ".env.prod.bak-cpu-fix-$(date +%Y%m%d%H%M%S)"
    chmod 600 .env.prod

### 3.2 获取包含兼容文件的代码

Git 更新方式：

    git fetch origin
    git pull --ff-only origin release/0.7.100

如果使用压缩包覆盖代码，必须保留服务器已有的 .env.prod、docker/volumes/ 和证书目录。覆盖后确认：

    test -f docker/milvus-sse42/build.sh
    test -f docker/milvus-sse42/compat.c
    test -f docker/milvus-sse42/Dockerfile

### 3.3 设置兼容镜像变量

只新增或替换 MILVUS_IMAGE，保留 .env.prod 其它内容：

    if grep -q '^MILVUS_IMAGE=' .env.prod; then
      sed -i 's#^MILVUS_IMAGE=.*#MILVUS_IMAGE=openzetc-milvus:2.5.6-sse42#' .env.prod
    else
      printf '\nMILVUS_IMAGE=openzetc-milvus:2.5.6-sse42\n' >> .env.prod
    fi
    chmod 600 .env.prod

### 3.4 构建兼容镜像

服务器需要 Linux x86-64、gcc、Docker，以及可用的
milvusdb/milvus:v2.5.6 基础镜像。构建脚本不会停止或删除容器：

    chmod +x docker/milvus-sse42/build.sh
    bash docker/milvus-sse42/build.sh

镜像仓库不可访问时，先通过受控渠道导入同版本基础镜像：

    docker load -i /受控路径/milvus-v2.5.6.tar

然后再次执行上面的构建命令。

### 3.5 校验配置并仅重建 Milvus

    docker compose --env-file .env.prod -f docker-compose.prod.yml config --quiet

    docker compose --env-file .env.prod -f docker-compose.prod.yml \
      up -d --no-deps --force-recreate --wait --wait-timeout 120 milvus

此命令复用现有 Milvus、MinIO 和 etcd 数据卷。禁止执行 docker compose down -v，也不要删除或移动
docker/volumes/milvus/、docker/volumes/milvus/minio/ 或 docker/volumes/milvus/etcd/。

## 4. 验证

### 4.1 容器和镜像

    docker inspect -f 'image={{.Config.Image}} restart={{.RestartCount}} status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{end}}' milvus

预期：镜像为 openzetc-milvus:2.5.6-sse42，状态 running，健康状态 healthy，重启次数为 0。

### 4.2 只读真实向量检查

该脚本只读取集合中的一个已有向量并检索，不执行 release、load、reindex 或数据写入：

    bash scripts/check-milvus-search.sh kb_f8smdhu85m

预期最后出现：

    PASS: real vector search returned a hit ...

### 4.3 检查非法指令日志

    docker logs --since 10m milvus 2>&1 | grep -Ei 'invalid opcode|panic|segmentation fault' || true

正常情况下无输出。若再次出现 invalid opcode，先检查：

    docker inspect -f '{{.Config.Image}}' milvus
    grep -n '^MILVUS_IMAGE=' .env.prod

### 4.4 页面和域名接口

登录 https://openzetc.zjshjkj.com，打开目标知识库的“检索测试”，使用向量和混合模式各测试一次。浏览器显示旧页面时先执行 Ctrl + F5。

浏览器 Network 面板应看到：

    POST https://openzetc.zjshjkj.com/api/knowledge/databases/<知识库ID>/query-test
    HTTP 200

HTTP 200 但结果为空时，检查相似度阈值、检索模式和集合是否有可见向量；这与 Milvus 进程崩溃不同。

## 5. 后续系统迭代（不修改数据）

### 5.1 只更新 Web

    docker compose --env-file .env.prod -f docker-compose.prod.yml build web

    docker compose --env-file .env.prod -f docker-compose.prod.yml \
      up -d --no-deps web

### 5.2 更新 API、Worker 和 Web

先确认兼容镜像变量仍在，再执行部署脚本：

    grep -q '^MILVUS_IMAGE=openzetc-milvus:2.5.6-sse42$' .env.prod

    bash scripts/deploy-prod.sh

该脚本只重建应用容器；etcd、MinIO、PostgreSQL、Redis、Neo4j 和 Milvus 默认保留现有容器与数据。只有明确执行第 3.5 节时才重建 Milvus。

### 5.3 完整版本升级

升级前先做 PostgreSQL 逻辑备份和数据卷快照。升级后的 Compose 必须保留 MILVUS_IMAGE；兼容文件发生变化时重新执行第 3.4 节和第 3.5 节。

不要直接把基础镜像改成新 Milvus 版本。新版本需要重新检查导出符号、CPU 分派和真实向量检索。

## 6. 回滚

回滚应用代码时保留兼容镜像变量，避免重新引入非法指令故障。

只有为了故障对比才回滚 Milvus 原镜像：

    sed -i 's#^MILVUS_IMAGE=.*#MILVUS_IMAGE=milvusdb/milvus:v2.5.6#' .env.prod

    docker compose --env-file .env.prod -f docker-compose.prod.yml \
      up -d --no-deps --force-recreate --wait --wait-timeout 120 milvus

原镜像在该服务器上已确认可能再次触发 invalid opcode，不建议作为长期生产方案。恢复兼容镜像时，将变量改回 openzetc-milvus:2.5.6-sse42 后重复第 3.5 节。

## 7. 禁止操作清单

- 不执行 docker compose down -v；
- 不删除、清空或重新初始化 docker/volumes/；
- 不删除 PostgreSQL、MinIO、Milvus、Neo4j 数据目录；
- 不在聊天、工单或日志中粘贴 .env.prod、JWT、数据库密码或 API Key；
- 不把本兼容镜像直接套用到其它 CPU 或其它 Milvus 版本而不做回归验证。
