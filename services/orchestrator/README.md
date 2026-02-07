# OpenCode Orchestrator

FastAPI + Celery orchestrator for OpenCode server, following:

- `docs/plan/initial/overall-design-plan.md`
- `docs/plan/initial/design-plan-detail.md`
- `docs/api/opencode-server.md`

## Run (local)

```bash
cd services/orchestrator
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

Worker:

```bash
cd services/orchestrator
source .venv/bin/activate
celery -A app.worker.celery_app.celery_app worker -Q default --concurrency=12
```

## Env

```bash
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/orchestrator
export REDIS_URL=redis://localhost:6379/0
export OPENCODE_BASE_URL=http://localhost:4096
export OPENCODE_SERVER_USERNAME=opencode
export OPENCODE_SERVER_PASSWORD=your-password
```

