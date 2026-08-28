# 开发阶段
FROM node:24-alpine AS development
WORKDIR /app
ENV TZ=Asia/Shanghai

# 使用 package.json 锁定的 pnpm 版本，并使用国内镜像与重试策略。
RUN npm config set registry https://registry.npmmirror.com \
    && npm config set fetch-retries 5 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && npm install -g pnpm@10.11.0

# 复制 package.json 和 pnpm-lock.yaml
COPY ./web/package*.json ./
COPY ./web/pnpm-lock.yaml* ./

# 安装依赖
RUN pnpm install --registry=https://registry.npmmirror.com

# 复制源代码
COPY ./web .

# 暴露端口
EXPOSE 5173

# 启动开发服务器的命令在 docker-compose 文件中定义

# 生产阶段
FROM node:24-alpine AS build-stage
WORKDIR /app

# 使用 package.json 锁定的 pnpm 版本，避免构建时随 latest 漂移。
RUN npm config set registry https://registry.npmmirror.com \
    && npm config set fetch-retries 5 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && npm install -g pnpm@10.11.0

# 复制依赖文件
COPY ./web/package*.json ./
COPY ./web/pnpm-lock.yaml* ./

# 安装依赖
RUN pnpm install --frozen-lockfile --registry=https://registry.npmmirror.com

# 复制源代码并构建
COPY ./web .
RUN pnpm run build

# 生产环境运行阶段
FROM nginx:alpine AS production
COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY ./docker/nginx/nginx/nginx.conf /etc/nginx/nginx.conf
COPY ./docker/nginx/nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
