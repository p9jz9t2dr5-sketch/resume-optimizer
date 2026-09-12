# ---- Build stage ----
FROM node:22-alpine AS builder

# 国内 npm 镜像，加速安装（可改为其他源）
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN npm config set registry "$NPM_REGISTRY"

WORKDIR /app

# `npm ci` installs exactly what package-lock.json pins — the same command CI runs.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# 构建时注入 API 基址：使用相对路径 /api，配合 nginx 反代，
# 这样同一镜像在 localhost 或任意域名下都无需重新构建。
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# ---- Runtime stage ----
# `output: "standalone"` traces the modules the server actually requires, so the
# runtime image ships that trace instead of the whole node_modules and no
# dev/build tooling ends up in production.
FROM node:22-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production
# The standalone server binds to $HOSTNAME when it is set, and Docker sets that to
# the container id — pin it so it listens on every interface.
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
