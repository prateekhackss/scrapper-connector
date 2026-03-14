# ConnectorOS Scout

**ConnectorOS Scout** is an end-to-end recruitment intelligence pipeline built for tech recruiting agencies. It automatically discovers, enriches, verifies, and scores potential candidate leads in real-time.

## Features

- **Multi-Source Discovery**: Aggregates job postings and companies from RemoteOK and SerpAPI (Google Jobs).
- **AI-Powered Enrichment**: Uses OpenAI (GPT-4o / GPT-4o-mini) to find contacts, generate hyper-personalized emails, and determine hiring intensity.
- **Robust Verification**: Performs deep validation on emails (MX records, syntax) and social profiles.
- **Real-Time Streaming**: Streams live backend execution logs to the frontend via Server-Sent Events (SSE).
- **PostgreSQL / Supabase**: Fully compatible with Supabase for cloud persistence.
- **Modern Frontend Environment**: Built with React and Vite, featuring a premium dark-themed "Live Console".

## Tech Stack

- **Backend**: FastAPI, Python 3.10+, SQLAlchemy (ORMs), `asyncio`, Uvicorn.
- **Frontend**: React, Vite, TailwindCSS (optional integration), Javascript.
- **Database**: PostgreSQL (Supabase).
- **Integrations**: OpenAI API, SerpAPI.

## Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1. Database & Environment Setup
Copy the example environment variables and add your keys:
```bash
cp .env.example .env
```
Inside `.env`, configure your API Keys:
- `OPENAI_API_KEY`
- `SERPAPI_KEY` *(Optional)*
- `DATABASE_URL` *(Required: Supabase Postgres URI, ideally pooler `...pooler.supabase.com:6543`)*  
  - You can alternatively set `SUPABASE_DB_URL`.
  - `SUPABASE_URL` (`https://<project>.supabase.co`) is API URL only, not DB URL.

### 2. Backend Setup
```bash
pip install -r requirements.txt
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```
*The database and 11 schemas will automatically initialize on the first run.*

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

Navigate to `http://localhost:5173/pipeline`, open the **Pipeline** tab, and click **Start Pipeline** to watch the real-time execution in the Live Console!

## Deployment Architecture

Use this split deployment:

- **Frontend** on Vercel
- **Backend + pipeline** on Railway or Render
- **Database** on Supabase

Vercel is great for the React frontend, but long-running background pipeline jobs are not reliable inside Vercel serverless functions.

### Recommended Production Layout

```text
Vercel (React frontend)
        |
        v
Railway/Render (FastAPI backend + pipeline execution)
        |
        v
Supabase Postgres
```

## Deploy Backend on Railway

This repo includes both [Procfile](C:\Users\techb\OneDrive\Desktop\real_scrapper\Procfile) and [railway.json](C:\Users\techb\OneDrive\Desktop\real_scrapper\railway.json), so Railway does not need to guess the FastAPI start command.

### 1. Create a Railway Project

- Push this repo to GitHub
- In Railway, click **New Project**
- Choose **Deploy from GitHub repo**
- Select this repository

Railway should now start the backend with:

```bash
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

### 2. Set Railway Environment Variables

Add these in Railway:

- `DATABASE_URL=postgresql://...`
- `OPENAI_API_KEY=...`
- `SERPAPI_KEY=...` *(optional)*
- `CORS_ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:5173`

Optional:

- `LOG_LEVEL=INFO`

### 3. Verify Railway Backend

Open:

- `https://your-backend.up.railway.app/api/health`

It should return JSON like:

```json
{"status":"healthy","version":"2.0.0"}
```

## Deploy Backend on Render

This repo includes [render.yaml](C:\Users\techb\OneDrive\Desktop\real_scrapper\render.yaml) for a simple FastAPI web service deploy.

### 1. Create a Render Web Service

- Push this repo to GitHub
- In Render, click **New +** -> **Web Service**
- Connect the GitHub repo
- Render should detect the included `render.yaml`

If you configure manually, use:

- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`

### 2. Set Render Environment Variables

Add these in Render:

- `DATABASE_URL=postgresql://...`
- `OPENAI_API_KEY=...`
- `SERPAPI_KEY=...` *(optional)*
- `CORS_ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://localhost:5173`

Optional:

- `LOG_LEVEL=INFO`

### 3. Verify Render Backend

Open:

- `https://your-backend.onrender.com/api/health`

It should return JSON like:

```json
{"status":"healthy","version":"2.0.0"}
```

## Deploy Frontend on Vercel

Keep the frontend on Vercel, but point it to the Railway or Render backend.

### 1. Vercel Environment Variable

In Vercel, add:

```env
VITE_API_BASE_URL=https://your-backend.up.railway.app/api
```

### 2. Redeploy Vercel

After saving the variable, redeploy the frontend.

The frontend API client in [frontend/src/api.js](C:\Users\techb\OneDrive\Desktop\real_scrapper\frontend\src\api.js) will then call Render instead of same-origin `/api`.

## Local Development

For local development, you can still run:

- backend on `http://localhost:8000`
- frontend on `http://localhost:5173`

The Vite proxy in [frontend/vite.config.js](C:\Users\techb\OneDrive\Desktop\real_scrapper\frontend\vite.config.js) will continue forwarding `/api` to the local backend.

## License
Proprietary - ConnectorOS
