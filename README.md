# CalAI - Nutrition Tracking & AI Assistant

A full-stack calorie tracking application with a hybrid AI chatbot combining Qdrant-backed food search and Ollama LLM.

## Tech Stack

- **Frontend**: React + TypeScript + Vite
- **Backend**: Node.js + Express + TypeScript
- **Database**: MySQL
- **AI**: CalAI Python agent (Qdrant + Ollama) with Ollama fallback

## Prerequisites

- Node.js 18+ & pnpm
- *(Tùy chọn nâng cao)*: MySQL 8.0+, [Ollama](https://ollama.com/), Python (FastAPI).

> [!TIP]
> **Chế độ Standalone (Zero-Config)**: Bạn **KHÔNG BẮT BUỘC** phải cài MySQL, Ollama hay Python để chạy thử nghiệm! Hệ thống đã tích hợp sẵn **Embedded Local Storage** tự động lưu vào `backend/data/local-db.json` với hơn 180+ món ăn Việt Nam thực tế và trợ lý AI dinh dưỡng tích hợp sẵn.

## Quick Start (Chạy ngay lập tức)

Chỉ cần chạy lệnh sau từ thư mục gốc:

```bash
pnpm install
pnpm dev
```

- Mở trình duyệt tại: **http://localhost:3001**
- Tài khoản mẫu có sẵn:
  - **Admin**: `admin@calai.local` / Mật khẩu: `Admin123!`
  - **User**: `user@calai.local` / Mật khẩu: `User123!`

---

## Cài đặt đầy đủ (Nâng cao với MySQL / Ollama)

### 1. Database

```sql
CREATE DATABASE calai;
```

Run the schema file:

```bash
mysql -u root -p calai < backend/schema.sql
```

### 2. Backend

```bash
cd backend
cp .env.example .env
# Edit .env with your MySQL credentials
pnpm install
pnpm dev
```

### 3. Ollama (required)

Make sure Ollama is running and pull a model:

```bash
ollama pull llama3.2
```

### 4. CalAI Python Backend (optional)

For food nutrition search powered by Qdrant:

```bash
cd Cal_ai
pip install -r requirements.txt
# Edit .env with Qdrant URL if needed
python -m uvicorn api.app:app --reload
```

The chatbot uses this automatically when available. If CalAI is unavailable or returns no data, it falls back to Ollama.

### 5. Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Open http://localhost:3001

### 6. Quick Start with pnpm Workspace (Root)

From the root directory, you can install all dependencies and run both servers simultaneously:

```bash
# Install dependencies for all projects
pnpm install

# Run both backend and frontend concurrently
pnpm dev

# Or run separately from root:
pnpm dev:backend
pnpm dev:frontend
```

## Project Structure

```
backend/src/
├── chat/
│   ├── controllers/chat.controller.ts
│   ├── routes/chat.routes.ts
│   ├── services/
│   │   ├── ai-provider.service.ts   # Hybrid: CalAI agent + Ollama fallback
│   │   └── chat.service.ts         # Chat session/message logic
├── auth/                           # Authentication (JWT)
├── user/                           # User management
├── admin/                          # Admin panel
├── shared/database/db.ts           # MySQL connection pool
└── server.ts                       # Entry point

Cal_ai/                             # Python backend (optional)
├── api/app.py                      # FastAPI app with /query endpoint
├── core/
│   ├── agent/agent.py              # Data agent with search/compute/chart tools
│   ├── services/qdrant_service.py  # Qdrant vector search
│   └── search/hybrid_search.py     # Hybrid search
```

## AI Architecture

The chatbot uses a **hybrid approach**:

1. User sends a message
2. Backend calls the CalAI Python agent (`http://localhost:8000/query`)
   - Agent searches Qdrant for food nutrition data
   - Computes/sorts/aggregates results
   - Generates charts if needed
3. If CalAI returns valid results, they are returned to the user
4. If CalAI is unavailable or returns no data, the system falls back to Ollama
5. Ollama receives user context (profile, goals, today's progress, recent meals) and answers directly

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | 3000 | Backend server port |
| `DB_HOST` | localhost | MySQL host |
| `DB_PORT` | 3306 | MySQL port |
| `DB_USER` | root | MySQL user |
| `DB_PASSWORD` | - | MySQL password |
| `DB_NAME` | calai | Database name |
| `CAL_AI_BASE_URL` | http://localhost:8000 | CalAI Python agent URL |
| `OLLAMA_BASE_URL` | http://localhost:11434 | Ollama server URL |
| `OLLAMA_MODEL` | llama3.2 | Ollama model name |
| `JWT_SECRET` | - | JWT signing secret |
| `JWT_EXPIRES_IN` | 7d | JWT expiry |
