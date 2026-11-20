#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements-dev.txt

if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install --no-audit --no-fund)
fi
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm run build)
fi

echo "FraudLens: http://127.0.0.1:8000"
echo "(can PostgreSQL dang chay o 127.0.0.1:5432; tren Windows dung .\\scripts\\windows-db.ps1 start)"

# Mac dinh Postgres cai tren may (cong 5432). Doi bang bien moi truong DATABASE_URL neu can.
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://fraudlens:fraudlens_dev_password@127.0.0.1:5432/fraudlens}"
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
