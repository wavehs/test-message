"""
CLI-отправитель сообщений (macOS).
Запускай, пиши текст, жми Enter — сообщение улетит на Windows.
"""

import asyncio
import websockets
import sys
import os

# URL сервера — замени YOUR-APP на реальное имя после деплоя на Render
SERVER_URL = os.environ.get(
    "RELAY_SERVER_URL",
    "wss://test-message-xc4m.onrender.com/ws/send"
)


async def main():
    print("=" * 50)
    print("📨  ОТПРАВИТЕЛЬ СООБЩЕНИЙ")
    print("=" * 50)
    print(f"Сервер: {SERVER_URL}")
    print()

    while True:
        try:
            print("⏳ Подключение к серверу...")
            async with websockets.connect(SERVER_URL, ping_interval=20) as ws:
                print("✅ Подключено! Пиши сообщение и жми Enter.")
                print("   (Ctrl+C для выхода)")
                print("-" * 50)

                while True:
                    # Чтение ввода в отдельном потоке, чтобы не блокировать event loop
                    try:
                        message = await asyncio.get_event_loop().run_in_executor(
                            None, input, "💬 > "
                        )
                    except EOFError:
                        print("\n👋 Выход.")
                        return

                    message = message.strip()
                    if not message:
                        continue

                    await ws.send(message)

                    # Ждём подтверждение от сервера
                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        if response.startswith("OK:"):
                            count = response.split(":")[1]
                            print(f"   ✅ Доставлено ({count} получатель(ей) онлайн)")
                        else:
                            print(f"   ✅ Отправлено")
                    except asyncio.TimeoutError:
                        print(f"   ⚠️  Отправлено (нет подтверждения)")

        except websockets.exceptions.ConnectionClosedError:
            print("\n⚠️  Соединение разорвано. Переподключение через 3 сек...")
            await asyncio.sleep(3)
        except ConnectionRefusedError:
            print("\n❌ Сервер недоступен. Повтор через 5 сек...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"\n❌ Ошибка: {e}. Повтор через 5 сек...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Выход.")
