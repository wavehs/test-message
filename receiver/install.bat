@echo off
chcp 65001 > nul
title Установка зависимостей (Message Receiver)

echo ===================================================
echo   Установка необходимых библиотек для получателя
echo ===================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в системе!
    echo Пожалуйста, установите Python с официального сайта:
    echo https://www.python.org/downloads/
    echo При установке ОБЯЗАТЕЛЬНО отметьте галочку:
    echo "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Сбой при установке зависимостей!
    pause
    exit /b 1
)

echo.
echo ===================================================
echo [УСПЕХ] Все библиотеки успешно установлены!
echo Теперь вы можете запускать:
echo   • run.vbs    (РЕКОМЕНДУЕТСЯ - без открытия консоли)
echo   • receive.pyw
echo   • run.bat
echo ===================================================
echo.
pause
