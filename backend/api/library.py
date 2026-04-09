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
async def search(
    request: Request,
    source: str,
    q: str,
    page: int = 1,
    page_size: int = 60,
):
    """Search the streaming service's catalog (paginated).

    Mirrors the shape of ``GET /api/library/{source}/albums`` so the
    frontend can reuse its Load More / table-view machinery.  Returns
    ``{albums, total, limit, offset}``.
    """
    service = request.app.state.library_service
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    offset = (page - 1) * page_size
    return await service.search(source, q, limit=page_size, offset=offset)


@router.get("/{source}/playlists")
async def list_playlists(request: Request, source: str):
    """List the user's playlists from the streaming service.

    Currently only Qobuz is implemented.  Tidal returns an empty list
    until the SDK gains playlist read methods.
    """
    service = request.app.state.library_service
    return await service.list_playlists(source)


@router.get("/{source}/playlists/{playlist_id}")
async def get_playlist(request: Request, source: str, playlist_id: int):
    """Fetch a playlist with its track list."""
    service = request.app.state.library_service
    result = await service.get_playlist(source, playlist_id)
    if result is None:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Playlist not found"}, status_code=404)
    return result
