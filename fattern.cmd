@echo off
setlocal
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

where python >nul 2>nul
if not errorlevel 1 (
    python -m fattern %*
    exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 11))" >nul 2>nul
    if not errorlevel 1 (
        py -3 -m fattern %*
        exit /b %ERRORLEVEL%
    )
)

for /f "delims=" %%P in ('dir /b /s "%LOCALAPPDATA%\Programs\Python\Python3*\python.exe" 2^>nul') do (
    "%%P" -c "import sys; raise SystemExit(sys.version_info < (3, 11))" >nul 2>nul
    if not errorlevel 1 (
        "%%P" -m fattern %*
        exit /b %ERRORLEVEL%
    )
)

echo Python 3.11+ was not found. Install Python and add it to PATH.
exit /b 1
