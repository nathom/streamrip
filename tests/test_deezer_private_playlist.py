from types import SimpleNamespace

import deezer.errors
import pytest

from streamrip.client.deezer import DeezerClient
from streamrip.metadata.playlist import PlaylistMetadata


@pytest.mark.asyncio
async def test_get_playlist_falls_back_to_gw_on_permission_exception():
    def raise_perm(_item_id):
        raise deezer.errors.PermissionException("OAuthException code 200")

    fake_api = SimpleNamespace(
        get_playlist=raise_perm,
        get_playlist_tracks=raise_perm,
    )
    fake_gw = SimpleNamespace(
        get_playlist_page=lambda _id: {"DATA": {"TITLE": "Private Mix"}},
        get_playlist_tracks=lambda _id: [{"SNG_ID": "111"}, {"SNG_ID": "222"}],
    )

    client = DeezerClient.__new__(DeezerClient)
    client.client = SimpleNamespace(api=fake_api, gw=fake_gw)

    resp = await client.get_playlist("999")
    meta = PlaylistMetadata.from_deezer(resp)
    assert meta.name == "Private Mix"
    assert meta.tracks == ["111", "222"]
    assert resp["track_total"] == 2
