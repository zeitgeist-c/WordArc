@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "WordArc" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0wordarc.py" %*
    exit /b 0
)

where pythonw.exe >nul 2>&1
if %errorlevel% equ 0 (
    start "WordArc" pythonw.exe "%~dp0wordarc.py" %*
    exit /b 0
)

if exist "%~dp0dist\wordarc.exe" (
    echo Python bulunamadi; son derlenen WordArc surumu aciliyor.
    start "WordArc" "%~dp0dist\wordarc.exe" %*
    exit /b 0
)

echo WordArc baslatilamadi: Python veya dist\wordarc.exe bulunamadi.
echo En guncel kaynak kodunu calistirmak icin .venv olusturun veya Python'i PATH'e ekleyin.
pause
exit /b 1
