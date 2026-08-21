@echo off
echo Iniciando entorno de desarrollo de MAIS_IA...

:: Cargar variables de entorno de forma limpia y sin espacios desde backend/.env
if exist "%~dp0backend\.env" (
    echo Cargando variables de entorno desde backend/.env...
    for /f "usebackq tokens=1,* delims==" %%i in (`powershell -Command "Get-Content '%~dp0backend\.env' | Where-Object { $_ -match '=' -and -not $_.Trim().StartsWith('#') } | ForEach-Object { $k,$v = $_ -split '=', 2; Write-Output ($k.Trim() + '=' + $v.Trim()) }"`) do (
        set "%%i=%%j"
    )
)

echo Levantando contenedores Docker...
docker compose up -d

echo Iniciando worker de Celery...
start "MAIS_IA Celery" cmd /k "cd backend && .venv\Scripts\python.exe -m celery -A app.workers.celery_app worker --loglevel=info --pool=solo"

echo Iniciando servidor Backend (FastAPI)...
start "MAIS_IA Backend" cmd /k "cd backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

echo Iniciando Frontend (Next.js)...
start "MAIS_IA Frontend" cmd /k "cd frontend && npm run dev"

echo Iniciando Tunel Seguro (Ngrok)...
start "MAIS_IA Tunnel" cmd /k ""%~dp0ngrok.exe" http 8000 --domain=footing-jellied-glamorous.ngrok-free.dev"

echo Todos los servicios han sido iniciados.
