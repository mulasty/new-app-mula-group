# Control Center - SaaS Bootstrap

Control Center is a multi-tenant SaaS starter repository with FastAPI, PostgreSQL, Redis, and Celery.

## Stack

- Python 3.11
- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Redis
- Celery
- Docker + Docker Compose

## Repository Structure

```text
backend/
  app/
    core/
    domain/
    application/
    infrastructure/
    interfaces/
  workers/
  main.py
frontend/
```

## Quick Start

1. Create environment file:

```bash
cp .env.example .env
```

2. Start the system:

```bash
docker compose up --build
```

3. Verify health endpoint:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok","services":{"api":"up","database":"up","redis":"up"}}
```

## Local Backend Development (optional)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```
