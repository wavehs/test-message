@echo off
chcp 65001 > nul
cd /d "%~dp0"

:: Проверка наличия pythonw в системе
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw receive.py
    exit
)

:: Проверка наличия обычного python
where python >nul 2>&1
if %errorlevel% equ 0 (
    start "" python receive.py
    exit
)

:: Если Python не найден
echo ===================================================
echo [ОШИБКА] Python не найден в системе!
echo Пожалуйста, установите Python с официального сайта:
echo https://www.python.org/downloads/
echo.
echo При установке ОБЯЗАТЕЛЬНО отметьте галочку:
echo "Add python.exe to PATH"
echo ===================================================
echo.
pause
