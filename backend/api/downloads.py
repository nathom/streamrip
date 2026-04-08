"""Downloads API routes."""
from fastapi import APIRouter, Request
from ..models.schemas import DownloadRequest

router = APIRouter(prefix="/api/downloads", tags=["downloads"])

@router.get("/queue")
async def get_queue(request: Request):
    service = request.app.state.download_service
    db = request.app.state.db

    # In-memory active/pending items
    queue = service.get_queue()
    active = [q for q in queue if q["status"] == "downloading"]

    # Merge DB history for completed/failed items not in the in-memory queue
    in_memory_ids = {q.get("source_album_id") for q in queue}
    db_history = db.get_recent_downloads(limit=50)
    for album in db_history:
        if album["source_album_id"] not in in_memory_ids:
            queue.append({
                "id": f"history-{album['id']}",
                "source": album["source"],
                "source_album_id": album["source_album_id"],
                "title": album["title"],
                "artist": album["artist"],
                "cover_url": album.get("cover_url"),
                "track_count": album.get("track_count", 0),
                "tracks_done": album.get("track_count", 0) if album["download_status"] == "complete" else 0,
                "status": album["download_status"],
                "speed": 0,
                "bytes_done": 0,
                "bytes_total": 0,
            })

    return {"items": queue, "active_count": len(active), "total_speed": sum(q.get("speed", 0) for q in active)}

@router.post("/queue")
async def enqueue(request: Request, body: DownloadRequest):
    service = request.app.state.download_service
    return await service.enqueue(body.source, body.album_ids, force=body.force)

@router.delete("/queue/{item_id}")
async def remove_from_queue(request: Request, item_id: str):
    service = request.app.state.download_service
    await service.cancel([item_id])
    return {"status": "cancelled"}

@router.post("/scan")
async def scan_downloads(request: Request):
    """Scan the download directory for .streamrip.json files and reconcile with DB."""
    from qobuz.downloader import AlbumDownloader
    from datetime import datetime

    db = request.app.state.db
    download_path = db.get_config("downloads_path") or "/music"

    albums = AlbumDownloader.scan_downloaded_albums(download_path)
    reconciled = 0

    for meta in albums:
        source = meta.get("source", "qobuz")
        album_id = meta.get("album_id")
        if not album_id:
            continue

        existing = db.get_album_by_source_id(source, album_id)
        if existing is None:
            db.upsert_album(
                source=source,
                source_album_id=album_id,
                title=meta.get("title", "Unknown"),
                artist=meta.get("artist", "Unknown"),
                track_count=meta.get("tracks_count"),
                added_to_library_at=meta.get("downloaded_at", datetime.now().isoformat()),
            )

        db.update_album_status(
            db.get_album_by_source_id(source, album_id)["id"],
            "complete",
            downloaded_at=meta.get("downloaded_at"),
        )
        reconciled += 1

    return {"scanned": len(albums), "reconciled": reconciled}

@router.post("/cancel")
async def cancel_all(request: Request):
    service = request.app.state.download_service
    await service.cancel_all()
    return {"status": "cancelled"}
