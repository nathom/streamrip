"""Shared test fixtures for Qobuz client tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_transport():
    """Mock HTTP transport that returns configurable responses."""
    transport = AsyncMock()
    transport.app_id = "304027809"
    transport.user_auth_token = "test-token"
    return transport


# --- Sample API responses (from Proxyman captures) ---

SAMPLE_ALBUM = {
    "id": "p0d55tt7gv3lc",
    "title": "Virgin Lake",
    "version": None,
    "maximum_bit_depth": 24,
    "maximum_sampling_rate": 44.1,
    "maximum_channel_count": 2,
    "duration": 3487,
    "tracks_count": 14,
    "parental_warning": True,
    "release_date_original": "2026-04-03",
    "upc": "0067003183055",
    "streamable": True,
    "downloadable": True,
    "hires": True,
    "hires_streamable": True,
    "image": {
        "small": "https://static.qobuz.com/images/covers/lc/v3/p0d55tt7gv3lc_230.jpg",
        "thumbnail": "https://static.qobuz.com/images/covers/lc/v3/p0d55tt7gv3lc_50.jpg",
        "large": "https://static.qobuz.com/images/covers/lc/v3/p0d55tt7gv3lc_600.jpg",
    },
    "artist": {"id": 11162390, "name": "Philine Sonny", "albums_count": 25},
    "artists": [{"id": 11162390, "name": "Philine Sonny", "roles": ["main-artist"]}],
    "label": {"id": 2367808, "name": "Nettwerk Music Group"},
    "genre": {"id": 113, "name": "Alternativ und Indie", "path": [112, 113]},
    "description": "Album description text",
    "awards": [],
}

SAMPLE_TRACK = {
    "id": 33967376,
    "title": "Blitzkrieg Bop",
    "version": "40th Anniversary",
    "isrc": "USWA10100001",
    "duration": 133,
    "parental_warning": False,
    "performer": {"id": 47434, "name": "Ramones"},
    "album": {
        "id": "0603497873012",
        "title": "Ramones - 40th Anniversary",
        "image": {"small": "https://example.com/230.jpg", "thumbnail": "https://example.com/50.jpg", "large": "https://example.com/600.jpg"},
    },
    "audio_info": {"maximum_bit_depth": 24, "maximum_channel_count": 2, "maximum_sampling_rate": 96},
    "physical_support": {"media_number": 1, "track_number": 1},
    "rights": {"streamable": True, "downloadable": True, "hires_streamable": True, "purchasable": True, "previewable": True, "sampleable": True},
}

SAMPLE_PLAYLIST = {
    "id": 61997651,
    "name": "New Private Playlist",
    "description": "This is the name",
    "tracks_count": 0,
    "users_count": 0,
    "duration": 0,
    "public_at": False,
    "created_at": 1775635602,
    "updated_at": 1775635602,
    "is_public": False,
    "is_collaborative": False,
    "owner": {"id": 2113276, "name": "arthursoares"},
}

SAMPLE_GENRE = {"id": 112, "color": "#5eabc1", "name": "Pop/Rock", "path": [112], "slug": "pop-rock"}

SAMPLE_ARTIST_SUMMARY = {"id": 38895, "name": "Talk Talk"}

SAMPLE_FAVORITE_IDS = {
    "albums": ["0724386649553", "xetru34w7hkdv"],
    "tracks": [77158728, 12345678],
    "artists": [38895, 2414834],
    "labels": [7812847],
    "awards": [215],
    "articles": [],
}

SAMPLE_LAST_UPDATE = {
    "last_update": {
        "favorite": 1775473221,
        "favorite_album": 1775473221,
        "favorite_artist": 1657790773,
        "favorite_track": 1773822437,
        "favorite_label": 1756417638,
        "favorite_award": 1775208126,
        "playlist": 1775208266,
        "purchase": 1663572155,
    }
}
