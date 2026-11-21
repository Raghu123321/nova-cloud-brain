# NOVA Cloud Brain (Memory-as-a-Service)

A dedicated, production-grade cloud memory microservice powered by **Mem0**, **Supabase (pgvector)**, and **FastAPI**.

Designed as a central 24/7 intelligence layer for the NOVA ecosystem (PC Assistant, Flutter Mobile App, Telegram Bot).

---

## 🌟 Key Features

- **Multi-Signal Semantic Recall (`POST /v1/recall`)**: Semantic vector search fused with entity boosting and keyword matching.
- **Fire-and-Forget Async Learning (`POST /v1/learn`)**: Returns `202 Accepted` instantly; extracts facts and links entities in the background without UI lag.
- **Persistent & Scalable**: Vector embeddings stored in your **Supabase PostgreSQL** (`pgvector`), surviving all server restarts.
- **High-Entropy Security**: Constant-time `X-API-Key` verification protecting your memories from unauthorized access.
- **Zero-Downtime Keep-Alive**: Public `/health` endpoint compatible with UptimeRobot / cron-job.org to prevent Render free-tier sleep.

---

## 🚀 Local Quickstart

### 1. Install Dependencies
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

| Key | Description |
| :--- | :--- |
| `BRAIN_API_KEY` | High-entropy secret key for API authentication (e.g. `nb_live_...`) |
| `SUPABASE_DB_URL` | Supabase connection string (`postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require`) |
| `OPENAI_API_KEY` | OpenAI API Key for fact extraction and embeddings |
| `COLLECTION_NAME` | Default: `nova_memories` |

### 3. Run Locally
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open **http://localhost:8000/docs** to test the interactive Swagger UI.

---

## ☁️ Deploying to Render (Free Tier)

1. Create a new **Private GitHub Repository** and push this folder.
2. In [Render Dashboard](https://dashboard.render.com):
   - Click **New +** -> **Web Service**.
   - Select your GitHub repo.
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
3. Add Environment Variables in Render:
   - `BRAIN_API_KEY`
   - `SUPABASE_DB_URL`
   - `OPENAI_API_KEY`
   - `COLLECTION_NAME` = `nova_memories`
4. Deploy! Your API will be live at `https://nova-cloud-brain.onrender.com`.

---

## 🔌 Client Integration Example (Python)

```python
import requests

BRAIN_URL = "https://nova-cloud-brain.onrender.com"
API_KEY = "your_secret_key"
HEADERS = {"X-API-Key": API_KEY}

# 1. Recall
res = requests.post(
    f"{BRAIN_URL}/v1/recall",
    headers=HEADERS,
    json={"query": "kahan photo bheju?", "user_id": "master_user", "top_k": 3}
)
print("Memories:", res.json().get("memories"))

# 2. Learn (Async)
requests.post(
    f"{BRAIN_URL}/v1/learn",
    headers=HEADERS,
    json={"message": "Mera personal app photos path G:/photos hai.", "user_id": "master_user"}
)
```

