# 部署手册

演示环境：阿里云 ECS（2 vCPU / 2 GiB），单机 Docker Compose，nginx 单一入口。

## 常规部署（推荐）

在服务器上的仓库根目录执行：

```bash
cd /path/to/resume-optimizer
bash deploy.sh
```

脚本按固定顺序做六件事，顺序本身是有原因的：

| 步骤 | 做什么 | 为什么不能省 |
|------|--------|--------------|
| 1 | 检查 docker 与 `backend/.env` | `.env.local` 是本地 SQLite 配置，容器不读；缺 `.env` 会连到错误的库 |
| 2 | `pg_dump` 备份 | 迁移改 schema，出问题要能整库恢复 |
| 3 | `docker compose build` | **必须早于迁移**：迁移脚本在新镜像里，用旧镜像跑 `upgrade head` 等于没跑 |
| 4 | `alembic current` → `upgrade head` | 单独跑，失败立刻停；若让它跟在容器启动命令里，失败只会表现为「服务起不来」 |
| 5 | `up -d` + `restart nginx` | 前端容器重建后 IP 变化，nginx 仍指向旧上游 |
| 6 | 探 `/health` 与 `/api/openapi.json` | 只探端口不等于功能可用；这里会校验 `/agent/optimize` 是否真的注册上 |

## 老库首次迁移

如果这个库是早期 `Base.metadata.create_all` 建出来的（没有 `alembic_version` 表），
直接 `upgrade head` 会报 `table already exists`。先确认它确实等于基线 schema，再打基线：

```bash
STAMP_BASELINE=1 bash deploy.sh
```

判断方法：`docker compose exec db psql -U resume_user -d resume_optimizer -c '\dt'`
应该能看到 `users / resumes / job_descriptions / chat_sessions / messages / companies`
六张表，且**没有** `alembic_version`。

## 回滚

```bash
# 只回滚最近一次迁移（例如 b3f6a1d4e807 那三张 Agent 表）
docker compose run --rm --no-deps backend alembic downgrade -1

# 整库恢复
docker compose exec -T db psql -U resume_user -d resume_optimizer < backups/resume_optimizer-<时间戳>.sql

# 回滚代码
git checkout <上一个提交> && docker compose up -d --build && docker compose restart nginx
```

## 两个已知踩坑

1. **不要在小内存机器上跑 `docker system df`**：统计镜像时会吃掉 1 GB 以上内存，
   实测触发过内核级 OOM，把 dockerd 和五个容器一起干掉。回收空间用
   `docker builder prune -f`。
2. **`backend` 服务的启动命令带 `--reload`**：这是开发模式，生产环境建议去掉
   （文件监视常驻内存、异常时行为不同）。改一行 compose 即可，但会改变现有部署行为，
   所以这里只提示、不擅自改。
