# AI Resume Optimizer · AI 简历优化平台

上传简历、粘贴目标岗位 JD，得到可解释的匹配度评分与逐段改写建议；再开一场 AI 模拟面试，把简历里的经历真正讲清楚。

**在线体验：** <http://47.119.113.82> — 演示账号 `demo@resume-optimizer.dev` / `demo1234`（已预置一份示例简历和一场模拟面试记录）

> 演示账号是公开的、仅用于试用，请不要上传真实个人信息。

---

## 核心功能

| 功能 | 说明 |
|------|------|
| 账号体系 | 邮箱注册登录，JWT（access + refresh 双 token），bcrypt 存储密码；`is_premium` 区分免费/会员两档（配额与所选模型不同，暂无自助升级入口，由数据库字段控制） |
| 简历管理 | 支持 PDF / DOCX / TXT / 图片上传，服务端解析正文并保留原始文件 |
| 隐私脱敏 | 姓名、手机号、邮箱、身份证等 PII 自动替换为 `[已隐藏]`，送给模型的是脱敏文本 |
| 图片简历 OCR | 用 Qwen-VL 视觉模型识别图片简历，并自动裁出证件照作为简历头像 |
| JD 匹配分析 | 把岗位描述解析成结构化要求，逐条比对经历，输出匹配度评分、缺失关键词与改进建议 |
| AI 优化建议 | 按 STAR 原则逐段改写、量化成果，SSE 流式输出，支持一键复制全文 |
| AI 模拟面试 | 面试官围绕简历里的项目和经历逐轮追问，一次只问一个问题（prompt 明确禁止一次抛多条），SSE 流式；随时可以让它点评回答或总结整场表现 |
| 公司库 | 内置 50+ 互联网公司及其常见岗位，点击岗位可直接生成 JD 草稿 |
| 个人资料 | 头像上传（服务端居中裁剪并压缩）与昵称编辑 |
| 账号注销 | 一键删除账号：简历、JD、面试会话与消息全部清除，磁盘上的原始文件与头像也一并删除（先提交事务再删文件，避免数据库指向已删除的文件） |
| 用量配额 | 免费用户每日面试消息条数上限（默认 20 条，`FREE_DAILY_MESSAGE_LIMIT` 可配）；额度在调用模型前预占、模型失败则回滚，超限返回 429，控制面板实时显示「今日消息 / 每日额度」 |

## 系统架构

```text
                        ┌───────────────────────────────┐
   浏览器 ─────────────▶│  nginx :80（唯一入口）         │
                        │  /      → 前端容器 :3000       │
                        │  /api/  → 后端容器 :8000       │
                        │  SSE 关闭 proxy_buffering      │
                        └───────┬───────────────┬───────┘
                                │               │
                    ┌───────────▼────────┐  ┌───▼──────────────────────┐
                    │ Next.js 16         │  │ FastAPI (Python 3.12)    │
                    │ App Router + TS    │  │ SQLAlchemy 2.0 async     │
                    │ Zustand / Query    │  │ JWT 中间件 / Pydantic v2 │
                    └────────────────────┘  └───┬──────────┬───────────┘
                                                │          │
                                     ┌──────────▼───┐  ┌───▼──────────┐
                                     │ PostgreSQL 15│  │ Redis（配额）│
                                     └──────────────┘  └──────────────┘
                                                │
                                     ┌──────────▼──────────────────────┐
                                     │ DeepSeek（面试追问 / 改写）      │
                                     │ Qwen-VL via DashScope（图片 OCR）│
                                     └─────────────────────────────────┘
```

### 一次「简历优化」的完整链路

1. 前端把文件 POST 到 `/api/resumes/upload`，后端落盘并解析出正文；
2. 正文经 `anonymizer` 脱敏后写入 `anonymized_text`，真实文本单独留在 `content` 供预览与导出，**只有脱敏文本会发给模型**；
3. `/api/jd/parse` 把 JD 结构化并返回匹配度报告（评分、命中/缺失关键词、改进建议）；
4. `/api/resumes/{id}/polish` 用 SSE 流式返回逐段改写结果，nginx 侧关闭响应缓冲，首字延迟 1 秒内；
5. 模拟面试由 `/api/chat/start` 建立会话，后端先让模型生成一段面试官开场白（best-effort，失败不影响会话），之后 `/api/chat/{id}/message` 带着历史上下文逐轮追问，同样是 SSE；
6. 面试消息在调用模型前先原子预占一个免费额度（并发请求无法一起挤过上限），模型异常时把额度退回；计数存 Redis 以跨 worker 共享，未配置 Redis 时退化为进程内计数。

## 技术栈

| 层 | 选型 |
|----|------|
| 前端 | Next.js 16（App Router）、TypeScript、Tailwind CSS 4、Zustand、TanStack Query |
| 后端 | FastAPI、SQLAlchemy 2.0（async）、Pydantic v2、python-jose、passlib + bcrypt |
| 数据 | PostgreSQL 15、Redis 7（本地开发可退化为 SQLite，无需 Redis） |
| AI | DeepSeek（OpenAI 兼容协议，可替换）、Qwen-VL（DashScope，图片简历 OCR） |
| 部署 | Docker Compose（db / redis / backend / frontend / nginx）、阿里云 ECS |

## 工程实践

- **测试**：后端 44 个 pytest 用例（`backend/tests`）+ 前端 30 个 Vitest 用例（`frontend/tests`）。后端测试自备独立 SQLite 与临时上传目录，不依赖 Postgres、Redis 或任何 API Key，覆盖脱敏边界、迁移与模型一致性、账号资料链路、密码策略与登录限流、免费额度真的会拦下第 21 条消息、注销账号后不残留孤儿行与磁盘文件、孤儿文件清理脚本只删未被引用的文件，以及模拟面试会话的生命周期与所有权隔离（别人的会话一律 404）；前端用 Testing Library 覆盖头像回退、昵称校验边界、先传图再保存、非图片文件被拒、注册页校验、注销需二次确认、404 与错误边界，以及 API 错误透传。
- **数据生命周期**：删除简历会带走原始文件与裁剪头像，替换头像会删掉旧文件，注销账号会清空该用户的全部数据与文件；文件一律在事务提交之后才删除，避免数据库指向已不存在的文件。历史上用 psql 直接删行留下的孤儿文件，可以用 `backend/scripts/prune_orphan_uploads.py` 先 dry-run 列出、再加 `--delete` 清理。
- **认证与滥用防护**：注册密码限定 8–72 位（上限正好是 bcrypt 72 字节的截断边界，超长直接拒绝而不是静默截断）；登录按「客户端 IP + 邮箱」维度做失败限流，同一组合连续失败 5 次后返回 429，15 分钟窗口，登录成功即清零——按 IP+邮箱而不是仅按邮箱计数，避免攻击者用失败尝试把受害者锁在门外。
- **用量配额**：`quota_service` 用「先预占、失败回滚」的方式执行免费额度，避免并发请求绕过上限；Redis 不可用时不静默放行，而是退化为进程内计数（有测试覆盖第 21 条消息被拒的场景）。
- **数据库迁移**：schema 由 Alembic 版本化管理（`backend/alembic/versions`），应用启动不再建表。测试库本身就是用 `alembic upgrade head` 建的，另有一条测试跑 `alembic check`，一旦有人改了模型却没加迁移就会失败。
- **CI**：`.github/workflows/ci.yml` 分两个 job，后端跑 `pytest`，前端跑 `eslint` + `vitest` + `next build`。
- **配置分层**：`APP_ENV=local` 时读 `backend/.env.local`（SQLite、关闭 Redis），否则读 `backend/.env`（Postgres + Redis），由 `app/config.py` 统一决定；密钥只存在于环境变量，仓库里只有 `.env.example`。
- **上传与 URL 约定**：文件保存在 `UPLOAD_DIR`，对外一律通过 `app/services/storage.py` 转成 `/uploads/<name>` 形式的 URL，避免把服务器文件路径返回给浏览器。
- **反向代理**：前端构建时把 `NEXT_PUBLIC_API_URL` 注入为相对路径 `/api`，同一个镜像在 localhost 和任意域名下都不用重新构建。
- **容器**：前端用 Next 的 `output: "standalone"`，只把服务端真正依赖的模块装进运行镜像（`node server.js` 启动），镜像从 930 MB 降到 230 MB、运行时内存约 60 MB；后端镜像带 `.dockerignore`，构建上下文排除虚拟环境与上传文件，体积从 417 MB 降到 286 MB。
- **健壮性**：后端健康检查探 `/health`、前端探首页，nginx 会等两个上游都 healthy 再启动，因此 `docker compose ps` 的状态就是真实可用性；前端有路由级错误边界（可重试）和自定义 404 页，不会掉到 Next 默认的英文报错页。

## 性能实测

演示环境是阿里云 ECS（2 vCPU / 2 GiB，Alibaba Cloud Linux 3），单 uvicorn worker，PostgreSQL 与 Redis 同机。用 `backend/scripts/bench_api.py` 每项采样 15 次（脚本只打非模型接口，可安全对生产重复运行）：

| 接口 | 容器内直连后端（中位 / P95） | 经 nginx 反代（中位） | 公网往返（中位） |
|------|------|------|------|
| `GET /health` | 2.2 / 2.8 ms | 3.4 ms | 27.3 ms |
| `GET /resumes` | 8.5 / 9.2 ms | 11.9 ms | 37.6 ms |
| `GET /resumes/{id}` | 8.6 / 9.4 ms | 15.6 ms | 38.3 ms |
| `GET /companies/search` | 7.3 / 12.0 ms | 9.9 ms | 34.7 ms |
| `GET /chat/sessions` | 8.7 / 9.1 ms | 9.9 ms | 39.6 ms |
| `GET /auth/me/stats` | 11.0 / 16.1 ms | 10.2 ms | 35.9 ms |
| `POST /auth/login` | 291.7 / 314.6 ms | 292.1 ms | 317.4 ms |

读接口的服务端处理在 7–16 ms 区间，nginx 反代只增加 1–5 ms，公网往返约 25 ms（华南机房）。唯一明显的慢点是登录：290 ms 几乎全部花在 bcrypt 哈希上（成本因子 12，刻意让哈希慢一些以抵抗离线爆破），也正因如此，登录接口的失败限流同时承担了防爆破与保护 CPU 两个作用。复现方式：`docker compose exec backend python scripts/bench_api.py http://127.0.0.1:8000`。

## 目录结构

```text
resume-optimizer/
├── backend/
│   ├── app/
│   │   ├── api/          # auth / resumes / companies / jd / chat 路由
│   │   ├── models/       # SQLAlchemy ORM 模型
│   │   ├── schemas/      # Pydantic 请求/响应模型（含对模型输出的容错）
│   │   ├── services/     # 业务逻辑：AI、脱敏、解析、配额、存储
│   │   ├── middleware/   # JWT 鉴权
│   │   ├── config.py     # 环境分层（.env / .env.local）
│   │   └── main.py       # 应用装配、静态挂载、启动期建表与种子数据
│   ├── tests/            # pytest 用例与隔离 fixture
│   ├── scripts/          # 种子数据、一次性数据迁移脚本
│   ├── alembic/          # 版本化迁移（基线 + 后续 revision）
│   └── requirements*.txt
├── frontend/
│   ├── app/              # App Router 页面（landing / auth / dashboard / chat / companies）
│   ├── components/       # 按功能分目录的组件
│   ├── lib/              # API 客户端、鉴权与工具函数
│   ├── stores/           # Zustand 状态
│   └── tests/            # Vitest + Testing Library 组件/工具测试
├── nginx/nginx.conf      # 唯一入口，/api 反向代理 + SSE 关闭缓冲
├── docker-compose.yml    # db / redis / backend / frontend / nginx
└── .github/workflows/    # CI
```

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
cp backend/.env.example backend/.env   # 填入 OPENAI_API_KEY（DeepSeek）
docker compose up -d --build           # 启动前自动执行 alembic upgrade head
```

访问 <http://localhost>（nginx 在 80 端口统一入口）。

### 方式二：不用 Docker（SQLite）

```bash
cd backend
cp .env.example .env.local   # DATABASE_URL 改成 sqlite+aiosqlite:///./local_dev.db，REDIS_URL 留空
alembic upgrade head         # 建表（schema 由 Alembic 管理）
APP_ENV=local python -m uvicorn app.main:app --reload
```

> 如果本地已经有旧版本建出来的 `local_dev.db`，先执行一次 `alembic stamp head` 标记为最新，不用重新升级。

```bash
cd frontend
npm install && npm run dev
```

> Windows PowerShell：`$env:APP_ENV="local"; python -m uvicorn app.main:app --reload`

> 想在本机用生产模式预览前端：`npm run build` 后执行 `npm start`（standalone 服务端）。若页面样式缺失，把 `.next/static` 与 `public` 拷进 `.next/standalone/` 即可——容器镜像里这一步由 Dockerfile 完成。

## 环境变量

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | `postgresql+asyncpg://…`（Docker）或 `sqlite+aiosqlite:///./local_dev.db`（本地） |
| `REDIS_URL` | 配额计数用；留空则本地开发时跳过 |
| `SECRET_KEY` | JWT 签名密钥，**上线必须换成随机值** |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | DeepSeek 或任何 OpenAI 兼容服务 |
| `DASHSCOPE_API_KEY` / `QWEN_VL_MODEL` | 图片简历 OCR；不配置时该功能会明确报错，其余功能不受影响 |
| `CORS_ORIGINS` | 允许的前端来源，逗号分隔 |
| `UPLOAD_DIR` | 上传文件目录，容器内为 `./uploads` |
| `FREE_DAILY_MESSAGE_LIMIT` | 免费用户每日消息上限 |

## 测试与检查

```bash
# 后端：44 个用例，使用独立 SQLite，不依赖外部服务
cd backend && pip install -r requirements.txt -r requirements-dev.txt && python -m pytest
```

```bash
# 前端：30 个用例（jsdom + Testing Library）
cd frontend && npm run test
```

```bash
# 前端：测试 + 生产构建（含类型检查）+ lint
cd frontend && npm run test && npm run build && npm run lint
```

## API

所有业务接口都在 `/api` 前缀之后（nginx 剥离前缀转发给后端）。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` · `/auth/login` · `/auth/refresh` | 注册 / 登录 / 刷新 access token |
| GET · PATCH · DELETE | `/auth/me` | 当前用户 / 修改昵称（1–8 字）/ 注销账号（连同数据与上传文件一并清除） |
| POST · DELETE | `/auth/me/avatar` | 上传（服务端裁剪为 256×256 PNG）/ 删除头像 |
| GET | `/auth/me/stats` | 简历数、会话数、今日用量与上限 |
| POST | `/resumes/upload` | 上传并解析简历（PDF / DOCX / TXT / 图片） |
| GET · DELETE | `/resumes` | 简历列表 / 全部清空 |
| GET · DELETE | `/resumes/{id}` | 单份简历详情 / 删除 |
| POST | `/resumes/{id}/parse` | 重新做结构化解析 |
| POST | `/resumes/{id}/polish` | AI 逐段改写（SSE 流式） |
| GET | `/resumes/{id}/export` | 导出优化后文本（.txt） |
| POST | `/jd/parse` | JD 结构化 + 匹配度分析 |
| GET | `/companies` · `/companies/search` | 公司库分页 / 搜索 |
| POST | `/chat/start` | 新建模拟面试会话（生成面试官开场白） |
| GET · DELETE | `/chat/sessions` | 面试记录列表 / 清空 |
| GET | `/chat/{id}/messages` | 会话消息 |
| POST | `/chat/{id}/message` | 面试问答（SSE 流式） |
| GET | `/health` | 健康检查 |

完整的交互式文档在 `http://<host>/api/docs`（FastAPI Swagger UI）。

## 部署

当前演示环境是阿里云 ECS（2 核 2 GiB，Alibaba Cloud Linux 3）上的 Docker Compose 单机部署：

```bash
git clone <repo> && cd resume-optimizer
cp backend/.env.example backend/.env   # 填 SECRET_KEY、AI Key，CORS_ORIGINS 换成实际域名/IP
docker compose up -d --build
docker compose ps                       # 5 个容器：db / redis / backend / frontend / nginx
```

- `docker-compose.override.yml` 给所有服务加了 `restart: unless-stopped`，机器重启后自动拉起；
- 更新版本：把新代码同步到服务器后执行 `docker compose up -d --build`，重建镜像会保留数据库卷；
- 前端容器重建后 nginx 会缓存旧的上游 IP，需要 `docker compose restart nginx`。

## 已知限制与后续计划

- **水平扩展**：会话状态在 Redis、文件在本地磁盘，多实例部署前需要把上传切到对象存储。
- **lint 债务**：`npm run lint` 已做到 0 error，但仍有 24 条 warning，主要是 API 适配层的 `any` 与数据获取写法的 `react-hooks/set-state-in-effect`。
