@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\pythonw.exe" (
    if "%~1"=="" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0wordarc.py" restart
    start "WordArc" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0wordarc.py" %*
    exit /b 0
)

where pythonw.exe >nul 2>&1
if %errorlevel% equ 0 (
    if "%~1"=="" pythonw.exe "%~dp0wordarc.py" restart
    start "WordArc" pythonw.exe "%~dp0wordarc.py" %*
    exit /b 0
)

set "WORDARC_EXE="
for /f "delims=" %%F in ('dir /b /a-d /o-d "%~dp0dist\WordArc *.exe" 2^>nul') do if not defined WORDARC_EXE set "WORDARC_EXE=%~dp0dist\%%F"
if defined WORDARC_EXE (
    echo Python bulunamadi; son derlenen WordArc surumu aciliyor.
    start "WordArc" "%WORDARC_EXE%" %*
    exit /b 0
)

echo WordArc baslatilamadi: Python veya surumlu WordArc EXE bulunamadi.
echo En guncel kaynak kodunu calistirmak icin .venv olusturun veya Python'i PATH'e ekleyin.
pause
exit /b 1
