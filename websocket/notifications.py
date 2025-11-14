from fastapi import WebSocket, WebSocketDisconnect
from typing import List

connected_clients: List[WebSocket] = []

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            for client in connected_clients:
                await client.send_text(f"🔔 {data}")
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
