# ---- Build stage ----
FROM node:22-alpine AS builder

# 国内 npm 镜像，加速安装（可改为其他源）
ARG NPM_REGISTRY=https://registry.npmmirror.com
RUN npm config set registry "$NPM_REGISTRY"

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# 构建时注入 API 基址：使用相对路径 /api，配合 nginx 反代，
# 这样同一镜像在 localhost 或任意域名下都无需重新构建。
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# ---- Runtime stage ----
FROM node:22-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts

EXPOSE 3000
CMD ["npm", "run", "start"]
