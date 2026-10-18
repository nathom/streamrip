from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from streamrip.exceptions import NonStreamableError
from streamrip.media.track import PendingSingle, Track
from streamrip.rip.main import Main


def make_pending(tmp_path, track_id, get_downloadable):
    config = MagicMock()
    config.session.deezer.quality = 2
    config.session.downloads.folder = str(tmp_path)
    config.session.filepaths.add_singles_to_folder = False

    client = MagicMock()
    client.source = "deezer"
    client.get_metadata = AsyncMock(return_value={"id": track_id})
    client.get_downloadable = AsyncMock(side_effect=get_downloadable)

    db = MagicMock()
    db.downloaded.return_value = False

    pending = PendingSingle(track_id, client, config, db)
    pending._download_cover = AsyncMock(return_value=None)
    return pending


@pytest.fixture(autouse=True)
def patch_metadata():
    with (
        patch("streamrip.media.track.AlbumMetadata.from_track_resp") as album,
        patch("streamrip.media.track.TrackMetadata.from_resp") as meta,
    ):
        album.return_value = MagicMock()
        meta.return_value = MagicMock()
        yield


async def test_available_track_resolves(tmp_path):
    pending = make_pending(tmp_path, "1", [MagicMock()])
    track = await pending.resolve()
    assert isinstance(track, Track)


async def test_non_streamable_track_returns_none(tmp_path, caplog):
    err = NonStreamableError("The requested track is not available.")
    pending = make_pending(tmp_path, "2", err)
    assert await pending.resolve() is None
    assert "[2]" in caplog.text


async def test_unexpected_error_is_not_swallowed(tmp_path):
    pending = make_pending(tmp_path, "3", RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        await pending.resolve()


async def test_main_resolve_skips_unavailable_track(tmp_path):
    ok_a = make_pending(tmp_path, "10", [MagicMock()])
    bad = make_pending(tmp_path, "11", NonStreamableError("geo"))
    ok_b = make_pending(tmp_path, "12", [MagicMock()])

    main = Main.__new__(Main)
    main.pending = [ok_a, bad, ok_b]
    main.media = []
    await main.resolve()

    assert len(main.media) == 2
    assert all(isinstance(m, Track) for m in main.media)
    assert main.pending == []
