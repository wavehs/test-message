"""
Relay-сервер для пересылки сообщений между отправителем (Mac) и получателем (Windows).
Используется FastAPI + WebSocket.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import asyncio
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Message Relay Server")

# Хранилище подключённых получателей
receivers: list[WebSocket] = []


@app.get("/")
async def health():
    """Health-check эндпоинт (полезен для ping'а и мониторинга)."""
    return JSONResponse({
        "status": "ok",
        "receivers_online": len(receivers),
        "timestamp": datetime.utcnow().isoformat()
    })


@app.websocket("/ws/send")
async def sender_endpoint(websocket: WebSocket):
    """
    Эндпоинт для отправителя.
    Принимает текстовые сообщения и рассылает их всем подключённым получателям.
    """
    await websocket.accept()
    logger.info("📤 Отправитель подключён")

    try:
        while True:
            message = await websocket.receive_text()
            message = message.strip()

            if not message:
                continue

            logger.info(f"📨 Сообщение: '{message}' → {len(receivers)} получатель(ей)")

            # Рассылка всем подключённым получателям
            disconnected = []
            for receiver in receivers:
                try:
                    await receiver.send_text(message)
                except Exception:
                    disconnected.append(receiver)

            # Удаляем отключившихся получателей
            for r in disconnected:
                if r in receivers:
                    receivers.remove(r)
                    logger.info("🔌 Удалён отключившийся получатель")

            # Подтверждение отправителю
            delivered = len(receivers)
            await websocket.send_text(f"OK:{delivered}")

    except WebSocketDisconnect:
        logger.info("📤 Отправитель отключился")


@app.websocket("/ws/receive")
async def receiver_endpoint(websocket: WebSocket):
    """
    Эндпоинт для получателя.
    Держит постоянное WebSocket-соединение и пересылает сообщения от отправителей.
    """
    await websocket.accept()
    receivers.append(websocket)
    logger.info(f"📥 Получатель подключён (всего: {len(receivers)})")

    try:
        while True:
            # Ожидаем ping/keepalive от клиента
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in receivers:
            receivers.remove(websocket)
        logger.info(f"📥 Получатель отключился (всего: {len(receivers)})")
