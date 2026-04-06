"""Library API routes."""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/library", tags=["library"])

@router.get("/{source}/albums")
async def get_albums(request: Request, source: str, page: int = 1, page_size: int = 50,
                     sort_by: str = "added_to_library_at", sort_dir: str = "DESC",
                     status: str | None = None, search: str | None = None):
    service = request.app.state.library_service
    return await service.get_albums(source, page=page, page_size=page_size,
                                     sort_by=sort_by, sort_dir=sort_dir, status=status, search=search)

@router.get("/{source}/albums/{album_id}")
async def get_album_detail(request: Request, source: str, album_id: int):
    service = request.app.state.library_service
    result = await service.get_album_detail(album_id)
    if result is None:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Album not found"}, status_code=404)
    return result

@router.post("/refresh/{source}")
async def refresh_library(request: Request, source: str):
    service = request.app.state.library_service
    return await service.refresh_library(source)

@router.get("/search/{source}")
async def search(request: Request, source: str, q: str, limit: int = 20):
    service = request.app.state.library_service
    return await service.search(source, q, limit=limit)
