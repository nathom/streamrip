import os
from unittest.mock import AsyncMock, Mock, patch

import pytest

from streamrip.client import Client
from streamrip.config import Config
from streamrip.db import Database
from streamrip.media.album import PendingAlbum
from streamrip.metadata import AlbumMetadata


@pytest.fixture
def mock_client() -> Client:
    """Fixture providing a mock client."""
    client = Mock(spec=Client)
    client.source = "qobuz"
    client.session = Mock()
    client.get_metadata = AsyncMock()
    return client


@pytest.fixture
def mock_config() -> Config:
    """Fixture providing a mock config with filepath settings."""
    config = Mock(spec=Config)
    config.session = Mock()
    config.session.downloads = Mock()
    config.session.downloads.folder = "/tmp/music"
    config.session.downloads.source_subdirectories = False
    config.session.filepaths = Mock()
    config.session.filepaths.folder_format = (
        "{artist} - {album} ({year}) [{format}] [{bit_depth}B-{sampling_rate}kHz]"
    )
    config.session.filepaths.restrict_characters = False
    config.session.artwork = Mock()
    return config


@pytest.fixture
def mock_database() -> Database:
    """Fixture providing a mock database."""
    return Mock(spec=Database)


@pytest.fixture
def mock_album_metadata() -> AlbumMetadata:
    """Fixture providing mock album metadata."""
    metadata = Mock(spec=AlbumMetadata)
    metadata.album = "Test Album"
    metadata.artist = "Test Artist"
    metadata.year = 2023
    metadata.format = "FLAC"
    metadata.bit_depth = 24
    metadata.sampling_rate = 96
    metadata.covers = Mock()
    metadata.format_folder_path = Mock(
        return_value="Test Artist - Test Album (2023) [FLAC] [24B-96kHz]"
    )
    return metadata


@pytest.fixture
def mock_long_album_metadata() -> AlbumMetadata:
    """Fixture providing mock album metadata with very long names."""
    metadata = Mock(spec=AlbumMetadata)
    metadata.album = "Very Long Album Name That Exceeds Normal Filesystem Limits" * 3
    metadata.artist = "Very Long Artist Name That Also Exceeds Normal Limits" * 2
    metadata.year = 2023
    metadata.format = "FLAC"
    metadata.bit_depth = 24
    metadata.sampling_rate = 96
    metadata.covers = Mock()

    long_path = (
        "Very Long Artist Name That Also Exceeds Normal Limits" * 2
        + " - "
        + "Very Long Album Name That Exceeds Normal Filesystem Limits" * 3
        + " (2023) [FLAC] [24B-96kHz]"
    )
    metadata.format_folder_path = Mock(return_value=long_path)
    return metadata


@pytest.fixture
def pending_album(
    mock_client: Client, mock_config: Config, mock_database: Database
) -> PendingAlbum:
    """Fixture providing a PendingAlbum instance."""
    return PendingAlbum(
        id="test_album_id", client=mock_client, config=mock_config, db=mock_database
    )


def test_album_folder_normal_length(
    pending_album: PendingAlbum, mock_album_metadata: AlbumMetadata
) -> None:
    """Test _album_folder with normal-length album metadata."""
    parent = "/tmp/music"
    result = pending_album._album_folder(parent, mock_album_metadata)

    expected_folder = "Test Artist - Test Album (2023) [FLAC] [24B-96kHz]"
    assert expected_folder in result
    assert result.startswith(parent)


def test_album_folder_respects_max_length(
    pending_album: PendingAlbum, mock_long_album_metadata: AlbumMetadata
) -> None:
    """Test _album_folder respects maximum length limit."""
    parent = "/tmp/music"
    result = pending_album._album_folder(parent, mock_long_album_metadata)

    # The folder name part should be truncated to 150 characters
    folder_name = os.path.basename(result)
    assert len(folder_name) <= 150
    assert result.startswith(parent)


def test_album_folder_with_source_subdirectories(
    pending_album: PendingAlbum, mock_album_metadata: AlbumMetadata
) -> None:
    """Test _album_folder with source subdirectories enabled."""
    pending_album.config.session.downloads.source_subdirectories = True
    parent = "/tmp/music"

    result = pending_album._album_folder(parent, mock_album_metadata)

    # Should include source subdirectory
    assert "Qobuz" in result  # Capitalized source name
    assert "Test Artist - Test Album" in result


def test_album_folder_restrict_characters(
    pending_album: PendingAlbum, mock_album_metadata: AlbumMetadata
) -> None:
    """Test _album_folder with character restriction enabled."""
    pending_album.config.session.filepaths.restrict_characters = True

    # Set up metadata with problematic characters
    problematic_path = "Test<>Artist - Test|Album*Name (2023) [FLAC]"
    mock_album_metadata.format_folder_path.return_value = problematic_path

    parent = "/tmp/music"
    result = pending_album._album_folder(parent, mock_album_metadata)

    # Should not contain restricted characters in the folder name
    folder_name = os.path.basename(result)
    restricted_chars = ["<", ">", "|", "*"]
    for char in restricted_chars:
        # clean_filepath should handle these through pathvalidate
        assert char not in folder_name, (
            f"Restricted character '{char}' found in folder name: {folder_name}"
        )

    # Verify the result is a valid path
    assert folder_name  # Should not be empty
    assert len(folder_name.encode()) <= 150  # Should respect max_length parameter


@pytest.mark.parametrize(
    ("parent_length", "album_name_length"),
    [
        (50, 100),  # Moderate parent, long album
        (100, 200),  # Long parent, very long album
        (200, 50),  # Very long parent, moderate album
        (10, 300),  # Short parent, extremely long album
    ],
)
def test_album_folder_various_lengths(
    pending_album: PendingAlbum, parent_length: int, album_name_length: int
) -> None:
    """Test _album_folder with various parent and album name lengths."""
    parent = "/tmp/" + "a" * parent_length

    # Create mock metadata with specified length
    mock_metadata = Mock(spec=AlbumMetadata)
    long_album_path = "b" * album_name_length
    mock_metadata.format_folder_path = Mock(return_value=long_album_path)

    result = pending_album._album_folder(parent, mock_metadata)

    # The album folder part should be limited to 150 characters
    folder_name = os.path.basename(result)
    assert len(folder_name) <= 150
    assert result.startswith(parent)


def test_album_folder_handles_empty_format(pending_album: PendingAlbum) -> None:
    """Test _album_folder handles empty format results."""
    mock_metadata = Mock(spec=AlbumMetadata)
    mock_metadata.format_folder_path = Mock(return_value="")

    parent = "/tmp/music"
    result = pending_album._album_folder(parent, mock_metadata)

    # Should still return a valid path
    assert result.startswith(parent)


def test_album_folder_strips_trailing_whitespace(pending_album: PendingAlbum) -> None:
    """Test _album_folder strips trailing whitespace after truncation."""
    mock_metadata = Mock(spec=AlbumMetadata)
    # Create a path that when truncated will have trailing spaces
    path_with_spaces = "Album Name With Trailing Spaces" + " " * 200
    mock_metadata.format_folder_path = Mock(return_value=path_with_spaces)

    parent = "/tmp/music"
    result = pending_album._album_folder(parent, mock_metadata)

    # Should not end with spaces
    folder_name = os.path.basename(result)
    assert not folder_name.endswith(" ")


@pytest.mark.parametrize(
    ("source", "expected_subdir"),
    [
        ("qobuz", "Qobuz"),
        ("deezer", "Deezer"),
        ("tidal", "Tidal"),
        ("soundcloud", "Soundcloud"),
    ],
)
def test_album_folder_source_subdirectory_names(
    mock_config: Config,
    mock_database: Database,
    mock_album_metadata: AlbumMetadata,
    source: str,
    expected_subdir: str,
) -> None:
    """Test _album_folder creates correct source subdirectory names."""
    mock_client = Mock(spec=Client)
    mock_client.source = source

    pending_album = PendingAlbum(
        id="test_id", client=mock_client, config=mock_config, db=mock_database
    )

    pending_album.config.session.downloads.source_subdirectories = True
    parent = "/tmp/music"

    result = pending_album._album_folder(parent, mock_album_metadata)

    assert expected_subdir in result


@pytest.mark.asyncio
async def test_resolve_creates_album_folder(
    pending_album: PendingAlbum, mock_album_metadata: AlbumMetadata
) -> None:
    """Test that resolve creates the album folder."""
    # Mock the client response with proper Qobuz tracks structure
    mock_resp = {
        "title": "Test Album",
        "artist": {"name": "Test Artist"},
        "tracks": {"items": [{"id": "track1"}, {"id": "track2"}]},
    }
    pending_album.client.get_metadata.return_value = mock_resp

    with (
        patch(
            "streamrip.media.album.AlbumMetadata.from_album_resp",
            return_value=mock_album_metadata,
        ),
        patch("streamrip.media.album.download_artwork", return_value=(None, None)),
        patch("os.makedirs") as mock_makedirs,
    ):
        await pending_album.resolve()

        # Should have called makedirs for the album folder
        mock_makedirs.assert_called()
        args, kwargs = mock_makedirs.call_args
        assert kwargs.get("exist_ok", False) is True


@pytest.mark.asyncio
async def test_resolve_handles_long_paths(
    pending_album: PendingAlbum, mock_long_album_metadata: AlbumMetadata
) -> None:
    """Test that resolve handles very long album paths correctly."""
    # Mock the client response with proper Qobuz tracks structure
    mock_resp = {
        "title": "Very Long Album Name",
        "artist": {"name": "Very Long Artist Name"},
        "tracks": {"items": [{"id": "track1"}]},
    }
    pending_album.client.get_metadata.return_value = mock_resp

    with (
        patch(
            "streamrip.media.album.AlbumMetadata.from_album_resp",
            return_value=mock_long_album_metadata,
        ),
        patch("streamrip.media.album.download_artwork", return_value=(None, None)),
        patch("os.makedirs") as _,
    ):
        album = await pending_album.resolve()

        assert album is not None
        # The folder path should be truncated appropriately
        folder_name = os.path.basename(album.folder)
        assert len(folder_name) <= 150


def test_album_folder_unicode_handling(pending_album: PendingAlbum) -> None:
    """Test _album_folder handles unicode characters properly."""
    mock_metadata = Mock(spec=AlbumMetadata)
    unicode_path = "Artista - Álbum Español (2023) [FLAC]"
    mock_metadata.format_folder_path = Mock(return_value=unicode_path)

    parent = "/tmp/music"
    result = pending_album._album_folder(parent, mock_metadata)

    # Should handle unicode characters
    assert "Artista" in result
    assert result.startswith(parent)


@pytest.mark.parametrize(
    ("restrict_chars", "input_path", "should_restrict"),
    [
        (True, "Artist - Album (2023)", False),  # No problematic chars
        (True, "Artist<>Album|Name*", True),  # Has problematic chars
        (False, "Artist<>Album|Name*", False),  # Restriction disabled
    ],
)
def test_album_folder_character_restriction_scenarios(
    pending_album: PendingAlbum,
    restrict_chars: bool,
    input_path: str,
    should_restrict: bool,
) -> None:
    """Test _album_folder character restriction in various scenarios."""
    pending_album.config.session.filepaths.restrict_characters = restrict_chars

    mock_metadata = Mock(spec=AlbumMetadata)
    mock_metadata.format_folder_path = Mock(return_value=input_path)

    parent = "/tmp/music"
    result = pending_album._album_folder(parent, mock_metadata)

    # Should always return a valid path
    assert result.startswith(parent)
    folder_name = os.path.basename(result)
    assert len(folder_name) <= 150


def test_album_folder_real_world_examples(pending_album: PendingAlbum) -> None:
    """Test _album_folder with real-world problematic album names."""
    real_world_examples = [
        "The London Metropolitan Orchestra, Elliot Goldenthal, Steven Mercurio, Jonathan Sheffer, The Mask Orchestra, The Pickled Heads Band - Titus - Original Motion Picture Soundtrack (2000) [FLAC] [16B-44.1kHz]",
        "Toronto Symphony Orchestra, Gustavo Gimeno, Isabel Leonard, Paul Appleby, Derek Welton - Stravinsky Pulcinella, ballet with song in one act, K034 XIV. Tarantella (2025) [FLAC] [24B-96kHz]",
        "Various Artists - The Complete Collection of Classical Music: Symphonies, Concertos, and Chamber Music (2023) [FLAC] [24B-192kHz]",
    ]

    parent = "/tmp/music"

    for example in real_world_examples:
        mock_metadata = Mock(spec=AlbumMetadata)
        mock_metadata.format_folder_path = Mock(return_value=example)

        result = pending_album._album_folder(parent, mock_metadata)

        # Should be truncated to reasonable length
        folder_name = os.path.basename(result)
        assert len(folder_name) <= 150
        assert result.startswith(parent)
        assert not folder_name.endswith(" ")  # No trailing spaces
