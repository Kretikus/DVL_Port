@echo off
for /f "delims=" %%p in ('where python') do SET PYTHON_PATH=%%p
if defined PYTHON_PATH (
    echo Python is installed at: %PYTHON_PATH%
) else (
    echo Python is not found in PATH.
    echo The game need python to run.
    pause
    exit 1
)

python -m laas_port.game

pause