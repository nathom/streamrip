import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest

from streamrip.client.downloadable import Downloadable
from streamrip.config import Config
from streamrip.db import Database
from streamrip.media.track import Track
from streamrip.metadata import AlbumMetadata, TrackMetadata


@pytest.fixture
def mock_config() -> Config:
    """Fixture providing a mock config with filepath settings."""
    config = Mock(spec=Config)
    config.session = Mock()
    config.session.filepaths = Mock()
    config.session.filepaths.track_format = "{tracknumber}. {artist} - {title}"
    config.session.filepaths.restrict_characters = False
    config.session.filepaths.truncate_to = 0
    config.session.downloads = Mock()
    config.session.downloads.downloads = 3
    return config


@pytest.fixture
def mock_track_metadata() -> TrackMetadata:
    """Fixture providing mock track metadata."""
    metadata = Mock(spec=TrackMetadata)
    metadata.title = "Test Track Title"
    metadata.artist = "Test Artist"
    metadata.tracknumber = 1
    metadata.format_track_path = Mock(return_value="01. Test Artist - Test Track Title")
    return metadata


@pytest.fixture
def mock_album_metadata() -> AlbumMetadata:
    """Fixture providing mock album metadata."""
    metadata = Mock(spec=AlbumMetadata)
    metadata.album = "Test Album"
    metadata.artist = "Test Artist"
    metadata.year = 2023
    return metadata


@pytest.fixture
def mock_downloadable() -> Downloadable:
    """Fixture providing mock downloadable."""
    downloadable = Mock(spec=Downloadable)
    downloadable.extension = "flac"
    downloadable.size = AsyncMock(return_value=1024000)
    downloadable.download = AsyncMock()
    return downloadable


@pytest.fixture
def mock_database() -> Database:
    """Fixture providing mock database."""
    return Mock(spec=Database)


@pytest.fixture
def temp_folder() -> str:
    """Fixture providing a temporary folder path."""
    return tempfile.mkdtemp()


@pytest.fixture
def track_with_normal_path(
    mock_track_metadata: TrackMetadata,
    mock_downloadable: Downloadable,
    mock_config: Config,
    temp_folder: str,
    mock_database: Database,
) -> Track:
    """Fixture providing a track with normal-length paths."""
    return Track(
        meta=mock_track_metadata,
        downloadable=mock_downloadable,
        config=mock_config,
        folder=temp_folder,
        cover_path=None,
        db=mock_database,
    )


@pytest.fixture
def track_with_long_path(
    mock_downloadable: Downloadable,
    mock_config: Config,
    temp_folder: str,
    mock_database: Database,
) -> Track:
    """Fixture providing a track with very long paths."""
    long_metadata = Mock(spec=TrackMetadata)
    long_metadata.title = "Very Long Track Title That Exceeds Normal Limits" * 5
    long_metadata.artist = "Very Long Artist Name That Also Exceeds Limits" * 3
    long_metadata.tracknumber = 1
    long_metadata.format_track_path = Mock(
        return_value="01. "
        + "Very Long Artist Name That Also Exceeds Limits" * 3
        + " - "
        + "Very Long Track Title That Exceeds Normal Limits" * 5
    )

    return Track(
        meta=long_metadata,
        downloadable=mock_downloadable,
        config=mock_config,
        folder=temp_folder,
        cover_path=None,
        db=mock_database,
    )


def test_set_download_path_normal_length(track_with_normal_path: Track) -> None:
    """Test _set_download_path with normal-length paths."""
    track_with_normal_path._set_download_path()

    assert track_with_normal_path.download_path
    assert track_with_normal_path.download_path.endswith(".flac")
    assert "Test Artist" in track_with_normal_path.download_path
    assert "Test Track Title" in track_with_normal_path.download_path


def test_set_download_path_respects_max_length(track_with_long_path: Track) -> None:
    """Test _set_download_path respects maximum path length."""
    track_with_long_path._set_download_path()

    # Path should be truncated to reasonable length
    assert len(track_with_long_path.download_path) <= 250
    assert track_with_long_path.download_path.endswith(".flac")


@pytest.mark.parametrize(
    "truncate_to,expected_truncated",
    [
        (50, True),
        (0, False),  # No truncation
        (200, False),  # Longer than typical track name
    ],
)
def test_set_download_path_config_truncation(
    track_with_normal_path: Track, truncate_to: int, expected_truncated: bool
) -> None:
    """Test _set_download_path respects config truncation settings."""
    track_with_normal_path.config.session.filepaths.truncate_to = truncate_to
    original_format_result = "01. Test Artist - Test Track Title"
    track_with_normal_path.meta.format_track_path.return_value = original_format_result

    track_with_normal_path._set_download_path()

    if expected_truncated and truncate_to > 0:
        # Should be truncated
        filename = os.path.basename(track_with_normal_path.download_path)
        filename_without_ext = filename.rsplit(".", 1)[0]
        assert len(filename_without_ext) <= truncate_to
    else:
        # Should contain full original content
        assert "Test Artist" in track_with_normal_path.download_path
        assert "Test Track Title" in track_with_normal_path.download_path


def test_set_download_path_restrict_characters(track_with_normal_path: Track) -> None:
    """Test _set_download_path with character restriction enabled."""
    track_with_normal_path.config.session.filepaths.restrict_characters = True
    track_with_normal_path.meta.format_track_path.return_value = (
        "01. Test<>Artist - Test|Track*Title"
    )

    track_with_normal_path._set_download_path()

    # Should not contain restricted characters
    path = track_with_normal_path.download_path
    restricted_chars = ["<", ">", "|", "*"]
    for char in restricted_chars:
        assert char not in path


@pytest.mark.parametrize(
    "folder_length,filename_length",
    [
        (50, 100),  # Moderate folder, long filename
        (100, 100),  # Both moderate
        (150, 50),  # Long folder, short filename
        (100, 200),  # Moderate folder, very long filename
    ],
)
def test_set_download_path_various_lengths(
    mock_track_metadata: TrackMetadata,
    mock_downloadable: Downloadable,
    mock_config: Config,
    mock_database: Database,
    folder_length: int,
    filename_length: int,
) -> None:
    """Test _set_download_path with various folder and filename lengths."""
    long_folder = "/tmp/" + "a" * folder_length
    long_filename = "b" * filename_length

    mock_track_metadata.format_track_path.return_value = long_filename

    track = Track(
        meta=mock_track_metadata,
        downloadable=mock_downloadable,
        config=mock_config,
        folder=long_folder,
        cover_path=None,
        db=mock_database,
    )

    track._set_download_path()

    # Total path should be within reasonable limits
    assert len(track.download_path) <= 250
    assert track.download_path.endswith(".flac")


@pytest.mark.asyncio
async def test_preprocess_creates_directory(
    track_with_normal_path: Track, temp_folder: str
) -> None:
    """Test that preprocess creates the target directory."""
    # Remove the temp folder to test creation
    if os.path.exists(temp_folder):
        os.rmdir(temp_folder)

    await track_with_normal_path.preprocess()

    assert os.path.exists(temp_folder)
    assert os.path.isdir(temp_folder)


@pytest.mark.asyncio
async def test_preprocess_handles_directory_creation_failure(
    track_with_normal_path: Track,
) -> None:
    """Test that preprocess handles directory creation failures gracefully."""
    # Set an invalid folder path that will cause OSError
    track_with_normal_path.folder = "/invalid/path/that/cannot/be/created"

    with patch("tempfile.gettempdir", return_value="/tmp"):
        await track_with_normal_path.preprocess()

    # Should fall back to temp directory
    assert "streamrip_fallback" in track_with_normal_path.folder
    assert track_with_normal_path.download_path  # Should be recalculated


@pytest.mark.asyncio
async def test_preprocess_fallback_directory_creation() -> None:
    """Test that preprocess creates fallback directory when main directory fails."""
    mock_metadata = Mock(spec=TrackMetadata)
    mock_metadata.title = "Test Track"
    mock_metadata.format_track_path = Mock(return_value="Test Track")

    mock_downloadable = Mock(spec=Downloadable)
    mock_downloadable.extension = "flac"

    mock_config = Mock(spec=Config)
    mock_config.session = Mock()
    mock_config.session.filepaths = Mock()
    mock_config.session.filepaths.track_format = "{title}"
    mock_config.session.filepaths.restrict_characters = False
    mock_config.session.filepaths.truncate_to = 0
    mock_config.session.downloads = Mock()
    mock_config.session.downloads.downloads = 3

    track = Track(
        meta=mock_metadata,
        downloadable=mock_downloadable,
        config=mock_config,
        folder="/definitely/invalid/path",
        cover_path=None,
        db=Mock(spec=Database),
    )

    with (
        patch("tempfile.gettempdir", return_value="/tmp"),
        patch("os.makedirs") as mock_makedirs,
    ):
        # First call fails, second succeeds
        mock_makedirs.side_effect = [OSError("Permission denied"), None]

        await track.preprocess()

    # Should have switched to fallback folder
    assert "streamrip_fallback" in track.folder


def test_set_download_path_handles_empty_format() -> None:
    """Test _set_download_path handles empty format results."""
    mock_metadata = Mock(spec=TrackMetadata)
    mock_metadata.format_track_path = Mock(return_value="")

    mock_downloadable = Mock(spec=Downloadable)
    mock_downloadable.extension = "flac"

    mock_config = Mock(spec=Config)
    mock_config.session = Mock()
    mock_config.session.filepaths = Mock()
    mock_config.session.filepaths.restrict_characters = False
    mock_config.session.filepaths.truncate_to = 0

    track = Track(
        meta=mock_metadata,
        downloadable=mock_downloadable,
        config=mock_config,
        folder="/tmp",
        cover_path=None,
        db=Mock(spec=Database),
    )

    track._set_download_path()

    # Should still have a valid path with extension
    assert track.download_path.endswith(".flac")
    assert "/tmp" in track.download_path


@pytest.mark.parametrize("extension", ["flac", "mp3", "wav", "m4a"])
def test_set_download_path_preserves_extension(
    track_with_normal_path: Track, extension: str
) -> None:
    """Test that _set_download_path preserves the file extension."""
    track_with_normal_path.downloadable.extension = extension

    track_with_normal_path._set_download_path()

    assert track_with_normal_path.download_path.endswith(f".{extension}")


def test_set_download_path_strips_trailing_whitespace() -> None:
    """Test that _set_download_path strips trailing whitespace after truncation."""
    mock_metadata = Mock(spec=TrackMetadata)
    # Create a path that when truncated will have trailing spaces
    mock_metadata.format_track_path = Mock(return_value="Track Name With Spaces    ")

    mock_downloadable = Mock(spec=Downloadable)
    mock_downloadable.extension = "flac"

    mock_config = Mock(spec=Config)
    mock_config.session = Mock()
    mock_config.session.filepaths = Mock()
    mock_config.session.filepaths.restrict_characters = False
    mock_config.session.filepaths.truncate_to = 15  # Will truncate and leave spaces

    track = Track(
        meta=mock_metadata,
        downloadable=mock_downloadable,
        config=mock_config,
        folder="/tmp",
        cover_path=None,
        db=Mock(spec=Database),
    )

    track._set_download_path()

    # Should not end with spaces before the extension
    filename = os.path.basename(track.download_path)
    filename_without_ext = filename.rsplit(".", 1)[0]
    assert not filename_without_ext.endswith(" ")
