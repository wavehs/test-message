@echo off
chcp 65001 > nul
title Message Receiver (Overlay)

echo ===================================================
echo     Запуск получателя сообщений (Overlay)
echo ===================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден в системе!
    echo Пожалуйста, установите Python с https://www.python.org/
    echo При установке ОБЯЗАТЕЛЬНО отметьте галочку:
    echo "Add python.exe to PATH"
    echo.
    pause
    exit /b
)

echo [1/2] Проверка и установка зависимостей...
pip install -r requirements.txt

echo [2/2] Запуск получателя...
echo.
python receive.py
if %errorlevel% neq 0 (
    echo.
    echo [Программа завершилась с ошибкой]
    pause
)
