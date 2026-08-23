# AI Resume Optimizer — AI 简历优化平台

AI-powered resume optimization platform. Upload your resume, paste a job description, and get AI-driven match analysis and conversational optimization using STAR methodology.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind CSS 4, Zustand, TanStack Query |
| Backend | FastAPI (Python 3.12), SQLAlchemy 2.0 (async), PostgreSQL 15 (本地可用 SQLite) |
| Cache | Redis 7 |
| AI | DeepSeek (OpenAI 兼容协议), extensible adapter |
| Auth | JWT (access + refresh tokens), bcrypt |
| File Storage | Local (extensible to OSS/S3) |

## Project Structure

```
resume-optimizer/
├── frontend/           # Next.js 16 SPA
│   ├── app/            # App Router pages
│   ├── components/     # UI components (glass-morphism design)
│   ├── lib/            # API client, auth helpers, utils
│   └── stores/         # Zustand state stores
├── backend/            # FastAPI service
│   ├── app/
│   │   ├── api/        # Route handlers (auth, resumes, companies, jd, chat)
│   │   ├── models/     # SQLAlchemy ORM models
│   │   ├── schemas/    # Pydantic request/response schemas
│   │   ├── services/   # Business logic (AI, anonymize, file parsing)
│   │   └── middleware/ # JWT auth middleware
│   ├── alembic/        # Database migrations
│   └── scripts/        # Seed data (50+ companies)
└── docker-compose.yml  # PostgreSQL + Redis + Backend
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 18+
- Python 3.12+

### 1. Start Backend Services

```bash
cd resume-optimizer

# Start PostgreSQL, Redis, and Backend (auto-creates tables + seeds 50+ companies)
docker-compose up -d --build
```

### 2. Start Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Visit **http://localhost:3000**

### 3. Configure AI API Key

Edit `backend/.env` (or copy `backend/.env.example`) and fill in your DeepSeek key:
```env
OPENAI_API_KEY=sk-your-deepseek-api-key-here
OPENAI_BASE_URL=https://api.deepseek.com/v1
```

### Local Development (no Docker)

Run the same backend against SQLite with the DeepSeek key in `.env.local`:

```bash
cd backend
APP_ENV=local python -m uvicorn app.main:app --reload
```

> Windows PowerShell: `$env:APP_ENV="local"; python -m uvicorn app.main:app --reload`

## Core Features

1. **User System** — Email registration/login, JWT auth, free/premium tiers
2. **Resume Management** — Upload PDF/Word, auto-parse, PII anonymization
3. **Company Database** — 50+ top tech companies with common positions
4. **JD Parsing & Match Analysis** — AI extracts structured requirements, scores match
5. **AI Chat Optimization** — SSE streaming, multi-turn conversation, STAR rewrites
6. **Dashboard** — Stats, quota tracking, session history

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /auth/register | Create account |
| POST | /auth/login | Login, get JWT |
| GET | /auth/me | Current user info |
| POST | /resumes/upload | Upload & parse resume |
| GET | /resumes | List user resumes |
| GET | /companies/search | Search companies |
| POST | /jd/parse | Parse JD + match analysis |
| POST | /chat/start | Create optimization session |
| POST | /chat/{id}/message | Send message (SSE stream) |
| GET | /chat/sessions | List chat sessions |

## Design System

- **Dark theme**: `#0F172A` background with glass-morphism cards
- **Gradient accent**: Purple (`#7C3AED`) → Blue (`#3B82F6`) → Cyan (`#22D3EE`)
- **Font**: Geist (Sans + Mono)
- **Icons**: Lucide React

## Privacy

- Resume PII (names, phones, emails, addresses, IDs) automatically replaced with `[已隐藏]`
- Only anonymized text is sent to AI models
- Users can delete all data at any time

## MVP Scope

The MVP implements the core closed loop: **Register → Upload Resume → Paste JD → AI Match Analysis → Multi-turn Chat Optimization**.
