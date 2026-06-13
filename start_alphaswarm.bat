@echo off
echo Starting AlphaSwarm Infrastructure...

echo 1. Starting Docker Containers...
docker compose up -d

echo 2. Running DB Migrations...
python -m alembic upgrade head

echo 3. Starting Backend API...
start "AlphaSwarm API" cmd /k "python -m uvicorn app.main:app --reload"

echo 4. Starting Celery Worker...
start "AlphaSwarm Celery Worker" cmd /k "python -m celery -A app.core.celery_app.celery_app worker -Q trading_tasks -P threads -c 2 --loglevel=info"

echo 5. Starting Celery Beat...
start "AlphaSwarm Celery Beat" cmd /k "python -m celery -A app.core.celery_app.celery_app beat --loglevel=info"

echo 6. Starting Frontend...
cd frontend
start "AlphaSwarm Frontend" cmd /k "npm.cmd run dev"

echo ===================================================
echo All services launched in separate windows!
echo - API is running on http://localhost:8000
echo - Frontend is running on http://localhost:3000
echo ===================================================
