"""Sync API routes."""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/sync", tags=["sync"])

@router.get("/status/{source}")
async def sync_status(request: Request, source: str):
    service = request.app.state.sync_service
    return await service.get_diff(source)

@router.post("/run/{source}")
async def run_sync(request: Request, source: str, download_new: bool = False):
    service = request.app.state.sync_service
    return await service.run_sync(source, download_new=download_new)

@router.get("/history")
async def sync_history(request: Request, source: str = "qobuz", limit: int = 10):
    service = request.app.state.sync_service
    return await service.get_history(source, limit=limit)
