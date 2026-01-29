@echo off
echo ==========================================
echo 🚀 INICIANDO PROJECT ALKAHEST (DEV MODE)
echo ==========================================

:: 1. Inicia o Redis (se não for serviço)
echo [1/3] Verificando Redis...
start "REDIS SERVER" cmd /k "redis-server"

:: 2. Inicia o Celery Worker
echo [2/3] Ligando o Cozinheiro (Celery)...
start "CELERY WORKER" cmd /k "call venv\Scripts\activate && python -m celery -A core worker -l info -P solo"

:: 3. Inicia o Django Server
echo [3/3] Ligando o Garcom (Django)...
start "DJANGO SERVER" cmd /k "call venv\Scripts\activate && python manage.py runserver"

echo.
echo ✅ Tudo pronto! Janelas abertas.
echo Acesse: http://127.0.0.1:8000
pause
