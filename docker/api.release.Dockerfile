# 发布加速镜像：复用已验证的 API 运行时依赖，仅覆盖当前版本代码。
# 完整从零构建仍使用 api.Dockerfile。
ARG OPENZETC_API_BASE_IMAGE=openzetc-api:0.7.1
FROM ${OPENZETC_API_BASE_IMAGE}

WORKDIR /app

COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/.python-version /app/.python-version
COPY backend/uv.lock /app/uv.lock
COPY backend/package /app/package
COPY backend/server /app/server
