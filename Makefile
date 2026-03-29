.PHONY: install db-up migrate ollama-pull dev-backend dev-worker dev-frontend dev tunnel test docker-up docker-down

# Install all dependencies for backend and frontend
install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

# Start Postgres and Redis containers in the background
db-up:
	docker compose up postgres redis -d

# Run Alembic database migrations
migrate:
	cd backend && alembic upgrade head

# Download the codellama model for Ollama (~4GB)
ollama-pull:
	ollama pull codellama

# Start the FastAPI backend with hot reload
dev-backend:
	cd backend && uvicorn main:app --reload --port 8000

# Start the background worker that processes review jobs
dev-worker:
	cd backend && python worker.py

# Start the Next.js frontend dev server
dev-frontend:
	cd frontend && npm run dev

# Start everything: infrastructure + all three dev processes in parallel
dev: db-up
	$(MAKE) dev-backend & $(MAKE) dev-worker & $(MAKE) dev-frontend & wait

# Expose local backend to the internet for GitHub webhook testing
tunnel:
	ngrok http 8000

# Run the test suite
test:
	cd backend && pytest tests/ -v

# Build and start the full stack in Docker containers
docker-up:
	docker compose up --build

# Stop all containers and remove volumes
docker-down:
	docker compose down -v
