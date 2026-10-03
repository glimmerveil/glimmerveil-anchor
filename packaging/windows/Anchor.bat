@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not exist "%~dp0models" mkdir "%~dp0models"
if not defined VEIL_MODELS_DIR set "VEIL_MODELS_DIR=%~dp0models"
if exist "%~dp0voice\kokoro-v1.0.onnx" (
    if not defined VEIL_VOICE_DIR set "VEIL_VOICE_DIR=%~dp0voice"
    if not defined VEIL_WHISPER_MODEL set "VEIL_WHISPER_MODEL=%~dp0voice\ggml-base.en.bin"
) else (
    if not defined VEIL_VOICE set "VEIL_VOICE=0"
)

"%~dp0python\python.exe" "%~dp0app\src\veil_game.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo   Anchor stopped with an error ^(code %RC%^). Her folder is untouched.
    pause
)
endlocal & exit /b %RC%
