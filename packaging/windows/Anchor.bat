@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not exist "%~dp0models" mkdir "%~dp0models"

if defined VEIL_MODEL if exist "%VEIL_MODEL%" goto run
set "VEIL_MODEL="
for %%F in ("%~dp0models\*.gguf") do (
    set "VEIL_MODEL=%%~fF"
    goto run
)
if exist "%~dp0models\MODEL_PATH.txt" set /p VEIL_MODEL=<"%~dp0models\MODEL_PATH.txt"
if defined VEIL_MODEL if exist "%VEIL_MODEL%" goto run

echo.
echo   Glimmerveil Anchor needs a brain: a ChatML (Qwen-family) instruct model, as a .gguf file.
echo.
echo   Either put the .gguf in the "models" folder next to this file and run Anchor again,
echo   or drag the .gguf onto this window now and press Enter.
echo.
set "VEIL_MODEL="
set /p "VEIL_MODEL=  model file: "
if not defined VEIL_MODEL goto nomodel
set "VEIL_MODEL=%VEIL_MODEL:"=%"
if not exist "%VEIL_MODEL%" goto nomodel
>"%~dp0models\MODEL_PATH.txt" echo %VEIL_MODEL%
goto run

:nomodel
echo.
echo   No model file found there. Nothing was changed.
pause
exit /b 1

:run
"%~dp0python\python.exe" "%~dp0app\src\veil_game.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo   Anchor stopped with an error ^(code %RC%^). Her folder is untouched.
    pause
)
endlocal & exit /b %RC%
