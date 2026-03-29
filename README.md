# AI Code Reviewer

A FastAPI webhook service that uses **Ollama** (local LLM) to automatically review GitHub pull requests. When a PR is opened, the service fetches the diff, sends it to a local code review model, and posts the AI-generated review as a comment on the PR.

## Architecture

```
GitHub PR → Webhook → FastAPI (verify HMAC) → Redis Queue → Worker
                                                                ↓
                                              Fetch diff ← GitHub API
                                                                ↓
                                              AI Review ← Ollama (codellama)
                                                                ↓
                                              Store result → PostgreSQL
                                                                ↓
                                              Post comment → GitHub API
                                                                ↓
                                              Dashboard ← Next.js Frontend
```

## Prerequisites

- **Docker Desktop** installed and running
- **Ollama** installed ([https://ollama.com](https://ollama.com)) and running: `ollama serve`
- **ngrok** installed for local webhook testing
- A **GitHub account** with a test repository
- **Python 3.11+** and **Node 18+** (for local dev only)

## Step 1 — Clone and Configure

```bash
git clone <repo>
cd ai-code-reviewer
cp backend/.env.example .env
```

Edit `.env` and fill in:
- `GITHUB_TOKEN` — needs `repo` + `pull_request` scopes ([create one here](https://github.com/settings/tokens))
- `GITHUB_WEBHOOK_SECRET` — make up any random string, e.g.:
  ```bash
  openssl rand -hex 32
  ```

## Step 2 — Pull the Ollama Model

```bash
ollama pull codellama
```

This is ~4GB, do it before anything else. Verify it works:

```bash
ollama run codellama "say hello"
```

## Step 3 — Start Infrastructure

```bash
make db-up
```

Wait ~5 seconds for Postgres to be ready, then:

```bash
make migrate
```

## Step 4 — Start the Backend + Worker

In **terminal 1**:
```bash
make dev-backend
```

In **terminal 2**:
```bash
make dev-worker
```

Verify:
```bash
curl http://localhost:8000/health
```

## Step 5 — Expose Local Server to GitHub via ngrok

```bash
make tunnel
```

Copy the HTTPS forwarding URL, e.g. `https://abc123.ngrok.io`. You need this for the next step.

## Step 6 — Register the Webhook on GitHub

Go to: **GitHub repo → Settings → Webhooks → Add webhook**

| Field          | Value                                       |
|----------------|---------------------------------------------|
| Payload URL    | `https://abc123.ngrok.io/webhook`           |
| Content type   | `application/json`                          |
| Secret         | Same value as `GITHUB_WEBHOOK_SECRET` in `.env` |
| Events         | Select **"Pull requests"** only             |
| Active         | ✅ Checked                                   |

Click **Save** — GitHub will send a ping event to verify the URL.

## Step 7 — Start the Frontend

```bash
make dev-frontend
```

Opens at [http://localhost:3000](http://localhost:3000)

## Step 8 — Test It End to End

1. Open a pull request on the GitHub repo you registered the webhook for
2. Watch **terminal 1** (backend) log: `webhook received → verified → queued`
3. Watch **terminal 2** (worker) log: `fetching diff → calling ollama → posting comment`
4. Check the PR on GitHub — a review comment should appear within ~60 seconds
5. Check the dashboard at [http://localhost:3000](http://localhost:3000) — the review should appear there too

## Running the Full Stack with Docker (Alternative to Steps 3–7)

```bash
make docker-up
```

Everything starts except Ollama (which runs on your host):

| Service   | URL                        |
|-----------|----------------------------|
| Frontend  | http://localhost:3000       |
| Backend   | http://localhost:8000       |

You still need to run ngrok separately:

```bash
make tunnel
```

## Makefile Targets

| Target           | Description                                         |
|------------------|-----------------------------------------------------|
| `make install`   | pip install + npm install                           |
| `make db-up`     | docker compose up postgres redis -d                 |
| `make migrate`   | run alembic upgrade head                            |
| `make ollama-pull` | run: ollama pull codellama                        |
| `make dev-backend` | uvicorn main:app --reload --port 8000             |
| `make dev-worker`  | python worker.py                                  |
| `make dev-frontend` | cd frontend && npm run dev                       |
| `make dev`       | run db-up, then all three dev targets in parallel   |
| `make tunnel`    | run: ngrok http 8000                                |
| `make test`      | pytest tests/ -v                                    |
| `make docker-up` | docker compose up --build (full stack in containers)|
| `make docker-down` | docker compose down -v                            |

## Environment Variables

| Variable                | Description                                |
|-------------------------|--------------------------------------------|
| `GITHUB_WEBHOOK_SECRET` | Shared secret for HMAC verification        |
| `GITHUB_TOKEN`          | GitHub PAT with repo + PR scopes           |
| `OLLAMA_BASE_URL`       | Ollama API URL (default: http://localhost:11434) |
| `OLLAMA_MODEL`          | Model to use (default: codellama)          |
| `DATABASE_URL`          | PostgreSQL connection string               |
| `REDIS_URL`             | Redis connection string                    |

## Troubleshooting

| Problem                    | Solution                                                        |
|----------------------------|-----------------------------------------------------------------|
| Webhook returns 401        | `GITHUB_WEBHOOK_SECRET` in `.env` doesn't match GitHub setting  |
| Ollama timeout             | Run `ollama run codellama "hi"` to warm up the model first      |
| Worker not processing      | Check Redis is running: `docker compose ps`                     |
| No comment on PR           | Check `GITHUB_TOKEN` has `pull_request` write scope             |
| ngrok URL changed          | Update the webhook URL in GitHub settings and restart ngrok     |

## API Endpoints

| Method | Path              | Description                         |
|--------|-------------------|-------------------------------------|
| POST   | `/webhook`        | GitHub webhook receiver             |
| GET    | `/health`         | Health check (DB, Redis, Ollama)    |
| GET    | `/reviews`        | List reviews (paginated)            |
| GET    | `/reviews/{id}`   | Single review detail                |
