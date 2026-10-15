@echo off
setlocal
echo Stopping 1TamilVT-TG Bot processes...
taskkill /F /FI "WINDOWTITLE eq 1TamilVT-TG*" /T >nul 2>&1
wmic process where "commandline like '%%python%%-m bot%%'" call terminate >nul 2>&1
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*python*-m bot*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
echo [OK] Bot stopped.
pause
