@echo off
echo Stopping Athena Trader Services...
echo.

REM Kill all Python processes related to Athena Trader
taskkill /f /im python.exe /fi "WINDOWTITLE eq Data Manager*" 2>nul
taskkill /f /im python.exe /fi "WINDOWTITLE eq Risk Manager*" 2>nul
taskkill /f /im python.exe /fi "WINDOWTITLE eq Executor*" 2>nul
taskkill /f /im python.exe /fi "WINDOWTITLE eq Strategy Engine*" 2>nul

REM Alternative: Kill by port
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000"') do taskkill /f /pid %%a 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001"') do taskkill /f /pid %%a 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8002"') do taskkill /f /pid %%a 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8003"') do taskkill /f /pid %%a 2>nul

echo.
echo All services stopped!
pause
