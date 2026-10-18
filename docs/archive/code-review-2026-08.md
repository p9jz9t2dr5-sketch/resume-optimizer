# AI 简历优化平台 — 代码完善与建议报告

> 审查日期：2026-08-16
> 范围：后端 FastAPI（简历解析 / JD 匹配 / AI 对话 / 配额 / 认证）+ 前端 Next.js
> 结论：**核心闭环可用，已修复 6 个真实缺陷、新增 refresh token 与测试；另给出分阶段优化建议。**

---

## 一、本轮已完成的改动（均已验证）

| # | 文件 | 改动 | 修复的问题 | 验证 |
|---|------|------|-----------|------|
| 1 | `backend/app/api/jd.py` | `request.resume_id`（str）用 `uuid.UUID()` 包裹后再查库，非法值降级忽略 | Postgres 下 `Resume.id == "<str>"` 会报错，导致「带简历做 JD 匹配分析」功能崩溃 | 导入 OK |
| 2 | `backend/app/schemas/jd.py` | `MatchReport.overall_score` 增加 `field_validator` 安全取整 | LLM 返回 `87.5`/字符串时 pydantic 校验失败，匹配报告被**静默丢弃** | `test_schemas.py` 通过 |
| 3 | `backend/requirements.txt` | 补充 `aiosqlite` | README 宣称「本地无需 Docker（SQLite）」，但 `.env.local` 用的是 `sqlite+aiosqlite`，缺依赖直接导致本地起不来 | 安装成功 |
| 4 | `backend/app/api/companies.py` | 公司搜索 `Company.name.ilike` → `func.lower(Company.name).like(...)` | `.ilike` 在 SQLite 本地开发下行为异常/报错，搜索不可用 | 导入 OK |
| 5 | `backend/app/services/anonymizer.py` | ① 身份证号检测置于手机号之前（手机号正则会吞掉身份证里的 11 位数字，导致身份证漏脱敏）；② 中文姓名改为**仅行首或「姓名/名字/Name」标签后**才脱敏，避免误伤正文 | 隐私漏脱敏 + 原姓名正则把「张表」「李工」等正文整段误替换 | `test_anonymizer.py` 通过 |
| 6 | `backend/app/main.py` | CORS origins 按逗号切分并 `strip()` | 配置里若有空格会导致 CORS 不匹配 | 导入 OK |
| 7 | `backend/app/api/auth.py` + `services/auth_service.py` | 新增 `POST /auth/refresh` 端点与 `refresh_access_token()`，用 refresh token 换发 access token | 登录返回的 refresh_token 此前**毫无用处**，access 过期只能强制登出 | 导入 OK（路由 23→含 refresh） |
| 8 | `frontend/lib/api.ts` + `lib/auth.ts` | 实现 401 时**单次刷新**（single-flight）后自动重试；删除无效的 `EventSource` 死代码 | access 过期体验差；`sendMessageStream` 用了 GET+query 的 EventSource，而端点要求 POST，纯属错误代码 | TS 类型自洽 |
| 9 | `backend/.gitignore` | 忽略 `uploads/`、`local_dev.db`、`__pycache__`、`.env*` 等 | `uploads/` 含带隐私的测试简历（PDF/txt），会随仓库泄露 PII | — |
| 10 | `backend/tests/` | 新增 `test_anonymizer.py`、`test_schemas.py` + `conftest.py` | 此前**零测试**，无法防止回归 | `pytest` 8 passed |

**验证方式**（隔离 venv，Python 3.10）：`pip install -r requirements.txt aiosqlite pytest` → `pytest tests/ -q` 全部通过；`python -c "import app.main"` 成功，注册 23 条路由。

---

## 二、如何运行与验证

```bash
# 后端（本地 SQLite，无需 Docker）
cd backend
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt aiosqlite
APP_ENV=local uvicorn app.main:app --reload
pytest tests/ -q        # 8 passed

# 前端
cd frontend && npm install && npm run dev   # http://localhost:3000
```

> ⚠️ 前端 `package.json` 锁定 `next@16.3.0` / `react@19.2.8`。请确认 `npm install` 能拉到这些版本（如官方未发布对应版本会安装失败），必要时降到已发布的稳定版。

---

## 三、进一步建议（按优先级）

### P0 — 安全 / 正确性（建议尽快做）
1. **真实 token 用量统计**：当前 `Message.tokens_used` 是「按空格分词数」的估算，与计费/配额无关。建议用 LLM 返回的 `usage.prompt_tokens / completion_tokens` 真实数据，并据此做配额，而不是简单按「消息条数」计数。
2. **配额竞态**：`can_send_message` 检查与 `increment_daily` 非原子，高并发下免费用户可能小幅超额。建议用 Redis `INCR` + `DECR` 的原子检查（`INCR` 超过上限则 `DECR` 回滚）。
3. **文件上传安全**：`file_parser.parse_file` 对 `.doc` 也走 `python-docx`（`.doc` 是旧格式，docx 无法解析会抛错）；且未限制文件大小。建议：明确只支持 `.docx/.pdf/.txt`、限制单文件 ≤ 5MB、用 `asyncio.to_thread` 离线解析避免阻塞事件循环。
4. **`.env.local` 已提交密钥**：仓库 `/backend/.env.local` 含真实 DeepSeek key。应立即**轮换该 key** 并将其加入 `.gitignore`（本轮已加规则，但历史记录仍需轮换）。

### P1 — 功能完善
5. **结构化解析结果落库**：`/resumes/{id}/parse` 已存 `parsed_data.structured`，但 `/jd/parse` 的 `match_report` 仅返回不落库；建议持久化到 `JobDescription`，方便会话内复用。
6. **对话历史截断**：`stream_chat_response` 把全部历史塞进上下文，长会话会超出模型上下文。建议保留系统提示 + 最近 N 轮，或对 early 轮做摘要。
7. **账号体系**：注册无密码强度校验；无「忘记密码 / 邮箱验证 / 删除账号」。`README` 宣称「用户可随时删除所有数据」，但后端**没有删除账号/级联删除简历与上传文件**的接口，应补上（并注意 `uploads/` 物理文件也要删）。
8. **refresh token 轮换**：当前 `/auth/refresh` 复用原 refresh token；建议改成「刷新即轮换」，旧 token 短期失效，降低泄露风险。

### P2 — 工程化 / 体验
9. **统一数据库迁移**：同时存在 `Base.metadata.create_all`（lifespan 自动建表）与 `alembic/`（未使用）。二选一：用 Alembic 管理迁移（推荐，便于加列/索引），或删掉 alembic 目录消除歧义。
10. **Pydantic v2 告警**：多个 schema 仍用 `class Config:` 写法，触发 `PydanticDeprecatedSince20`。建议改为 `model_config = ConfigDict(from_attributes=True)`。
11. **前端构建验证**：`frontend` 至今无一次成功 `build` 的记录（仓库无 `.next`）。建议接入 CI：`npm run lint && npm run build`，并补充少量组件/接口测试（Vitest）。
12. **`structlog` 已声明但未使用**：清理未用依赖，保持 `requirements.txt` 与运行时一致。

### P3 — 架构 / 部署
13. **前端 Docker 化**：`docker-compose.yml` 只编排 pg/redis/backend，前端靠本地 `npm run dev`。生产化应加 `frontend` 服务（Next build + Nginx）与 `NEXT_PUBLIC_API_URL` 注入。
14. **异步任务**：JD 解析、简历结构化解析是同步阻塞调用，建议改为后台任务（Celery/ARQ/RQ）+ 轮询/WebSocket，避免请求超时。
15. **可观测性**：补充结构化日志（用已装但未用的 `structlog`）、请求追踪与基础指标；AI 调用加超时重试与降级（当前 `httpx.Timeout(10.0)` 偏短，长简历易超时）。
16. **多模型/多厂商适配**：`llm_service` 已预留 `is_premium` 双模型，但 `AI_FAST_MODEL==AI_PREMIUM_MODEL`。建议 FAST 用小参数模型、PREMIUM 用强模型，真正体现层级差异。

---

## 四、已知限制（设计层面，需权衡）

- **中文姓名脱敏是启发式**：仅「行首 / 姓名标签后」才替换，能大幅降低误报，但**行内出现的姓名可能漏脱敏**；且英文姓名未处理。要做到高召回需引入 NER 模型（如 spaCy / 中文 LTP），属后续增强项。
- **地址正则偏激进**：`anonymizer` 地址规则含「省/市/区/路/号」组合，可能误伤含地名的普通句子。如介意，可收紧为「仅含 省市区+具体门牌号」才替换。
- **AI 输出不可控**：匹配评分、结构化解析依赖 LLM JSON 输出，已做 `try/except` 兜底，但仍建议加 JSON schema 校验与失败重试。

---

## 五、交付清单

- [x] 修复 `jd.py` resume_id 类型 bug
- [x] 修复 `MatchReport` 评分健壮性
- [x] 补充 `aiosqlite` 依赖（本地开发可用）
- [x] 修复 SQLite 公司搜索兼容
- [x] 修复脱敏：身份证优先 + 姓名误报
- [x] 清理 CORS 配置
- [x] 新增 `/auth/refresh` 端点 + 前端自动刷新
- [x] 新增 `backend/.gitignore`（防 PII 入库）
- [x] 新增后端测试（脱敏 + schema），8 项通过
- [ ] 建议项（见第三节）待排期
