@echo off
echo Parando processos Django e Celery...
taskkill /F /IM python.exe 2>nul
timeout /t 2 >nul

echo Deletando banco de testes antigo...
del /F /Q test_db.sqlite3 2>nul
del /F /Q db.sqlite3-journal 2>nul

echo Banco limpo! Pode rodar os testes agora.
pause
