"""Downloads API routes."""
from fastapi import APIRouter, Request
from ..models.schemas import DownloadRequest

router = APIRouter(prefix="/api/downloads", tags=["downloads"])

@router.get("/queue")
async def get_queue(request: Request):
    service = request.app.state.download_service
    queue = service.get_queue()
    active = [q for q in queue if q["status"] == "downloading"]
    return {"items": queue, "active_count": len(active), "total_speed": sum(q.get("speed", 0) for q in active)}

@router.post("/queue")
async def enqueue(request: Request, body: DownloadRequest):
    service = request.app.state.download_service
    return await service.enqueue(body.source, body.album_ids)

@router.delete("/queue/{item_id}")
async def remove_from_queue(request: Request, item_id: str):
    service = request.app.state.download_service
    await service.cancel([item_id])
    return {"status": "cancelled"}

@router.post("/cancel")
async def cancel_all(request: Request):
    service = request.app.state.download_service
    await service.cancel_all()
    return {"status": "cancelled"}
