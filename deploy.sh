#!/usr/bin/env bash
# 部署脚本：备份 → 构建 → 迁移 → 启动 → 重启 nginx → 验证。
#
# 为什么不是简单一句 `docker compose up -d --build`：
#   1. compose 里的后端启动命令会先跑 `alembic upgrade head`，一旦迁移失败，
#      容器会崩溃重启、你看到的只是「服务起不来」，看不到真正的失败原因；
#      这里把迁移单独拎出来先跑，失败就立刻停，服务不受影响。
#   2. 迁移会改 schema，必须先备份数据库。
#   3. 老库（由早期 create_all 建出、没有 alembic_version 表）直接 upgrade 会报
#      「table already exists」。这种情况要先打基线：STAMP_BASELINE=1 bash deploy.sh
#
# 用法（在服务器上的仓库根目录执行）：
#   bash deploy.sh                    # 常规部署
#   STAMP_BASELINE=1 bash deploy.sh   # 老库首次迁移（只在确认它等于基线时才用）
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
COMPOSE="docker compose"
BASE_URL="${BASE_URL:-http://127.0.0.1}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m!! %s\033[0m\n' "$*" >&2; exit 1; }

cd "$APP_DIR"

log "1/6 检查前提"
command -v docker >/dev/null 2>&1 || fail "服务器上没有 docker"
[ -f backend/.env ] || fail "缺少 backend/.env（里面要有 SECRET_KEY 与模型 Key）"
if [ -f backend/.env.local ]; then
  echo "    提示：backend/.env.local 是本地开发配置（SQLite），容器不会读它"
fi

log "2/6 备份数据库（迁移前必须）"
mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
$COMPOSE up -d db redis
$COMPOSE exec -T db pg_dump -U resume_user -d resume_optimizer > "$BACKUP_DIR/resume_optimizer-$STAMP.sql"
[ -s "$BACKUP_DIR/resume_optimizer-$STAMP.sql" ] || fail "备份文件为空，已停止部署"
echo "    备份：$BACKUP_DIR/resume_optimizer-$STAMP.sql"

log "3/6 构建镜像（必须早于迁移：迁移代码在新镜像里）"
$COMPOSE build backend frontend

log "4/6 迁移 schema"
$COMPOSE run --rm --no-deps backend alembic current || true
if [ "${STAMP_BASELINE:-0}" = "1" ]; then
  echo "    打基线：把老库标记为 452bb3dc1c69（仅在确认它确实等于基线 schema 时使用）"
  $COMPOSE run --rm --no-deps backend alembic stamp 452bb3dc1c69
fi
$COMPOSE run --rm --no-deps backend alembic upgrade head
$COMPOSE run --rm --no-deps backend alembic current

log "5/6 启动容器并重启 nginx"
$COMPOSE up -d
# 前端容器重建后 IP 会变，nginx 仍指向旧上游，必须重启一次
$COMPOSE restart nginx

log "6/6 验证"
ready=0
for _ in $(seq 1 30); do
  # 必须走 /api/health：nginx 把 / 转给前端，根路径 /health 会命中原子的 404 页面
  # （后端健康检查挂在后端根路径，不在 /api 前缀下，只能经 /api/ 剥前缀转发过去）。
  if curl -fsS "$BASE_URL/api/health" >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
[ "$ready" = "1" ] || fail "60 秒内 /api/health 仍未就绪：docker compose logs --tail=100 backend"

curl -fsS "$BASE_URL/api/openapi.json" | grep -q '"/agent/optimize"' \
  || fail "服务起来了但 openapi 里没有 /agent/optimize：代码没更新或镜像没重建"
echo "    /api/health 正常，/agent 路由已注册"

$COMPOSE ps
cat <<EOF

部署完成。
回滚：docker compose run --rm --no-deps backend alembic downgrade -1
      （或从 $BACKUP_DIR/resume_optimizer-$STAMP.sql 恢复整库）
      再 git checkout <上一个提交> && docker compose up -d --build && docker compose restart nginx
EOF
