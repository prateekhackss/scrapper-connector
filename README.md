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
- **Database**: SQLite (default) / PostgreSQL (Supabase ready).
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
- `DATABASE_URL` *(Optional: Uncomment to use Supabase/PostgreSQL. Defaults to local SQLite)*

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

## License
Proprietary - ConnectorOS
