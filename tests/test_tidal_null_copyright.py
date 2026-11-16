from streamrip.metadata.album import AlbumMetadata


def test_tidal_from_track_and_album_handles_null_copyright():
    album_resp = {
        "allowStreaming": True,
        "title": "Test Album",
        "id": 123,
        "numberOfTracks": 1,
        "numberOfVolumes": 1,
        "copyright": None,
        "releaseDate": "2024-01-01",
        "artists": [{"name": "Artist"}],
        "explicit": False,
        "audioQuality": "LOSSLESS",
        "cover": "abc-def",
        "mediaMetadata": {"tags": ["LOSSLESS"]},
    }
    track_resp = {
        "allowStreaming": True,
        "title": "Test Track",
        "id": 456,
        "copyright": None,
        "artists": [{"name": "Artist"}],
        "explicit": False,
        "audioQuality": "LOSSLESS",
        "album": {"title": "Test Album", "id": 123, "cover": "abc-def"},
        "mediaMetadata": {"tags": ["LOSSLESS"]},
    }

    from_album = AlbumMetadata.from_tidal(album_resp)
    from_track = AlbumMetadata.from_tidal_playlist_track_resp(track_resp)
    assert from_album is not None and from_album.copyright == ""
    assert from_track is not None and from_track.copyright == ""
