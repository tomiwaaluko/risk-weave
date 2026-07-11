from fastapi import APIRouter, WebSocket

router = APIRouter(prefix="/scenarios", tags=["slider"])


@router.websocket("/{scenario_id}/slider")
async def slider_socket(websocket: WebSocket, scenario_id: str) -> None:
    await websocket.accept()
    await websocket.send_json({"scenario_id": scenario_id, "status": "connected"})
    await websocket.close()
