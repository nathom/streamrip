import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest

from streamrip.client import Client
from streamrip.client.downloadable import Downloadable
from streamrip.config import Config
from streamrip.db import Database
from streamrip.media.album import PendingAlbum
from streamrip.media.track import Track
from streamrip.metadata import AlbumMetadata, TrackMetadata


@pytest.fixture
def temp_download_dir() -> str:
    """Fixture providing a temporary download directory."""
    return tempfile.mkdtemp(prefix="streamrip_test_")


@pytest.fixture
def integration_config(temp_download_dir: str) -> Config:
    """Fixture providing a config for integration tests."""
    config = Mock(spec=Config)
    config.session = Mock()
    config.session.downloads = Mock()
    config.session.downloads.folder = temp_download_dir
    config.session.downloads.source_subdirectories = False
    config.session.downloads.downloads = 3
    config.session.filepaths = Mock()
    config.session.filepaths.folder_format = (
        "{artist} - {album} ({year}) [{format}] [{bit_depth}B-{sampling_rate}kHz]"
    )
    config.session.filepaths.track_format = "{tracknumber:02d}. {artist} - {title}"
    config.session.filepaths.restrict_characters = False
    config.session.filepaths.truncate_to = 0
    config.session.filepaths.add_singles_to_folder = True
    config.session.artwork = Mock()
    config.session.conversion = Mock()
    config.session.conversion.enabled = False
    config.session.cli = Mock()
    config.session.cli.progress_bars = False
    return config


@pytest.fixture
def mock_client() -> Client:
    """Fixture providing a mock client for integration tests."""
    client = Mock(spec=Client)
    client.source = "qobuz"
    client.session = Mock()
    client.get_metadata = AsyncMock()
    client.get_downloadable = AsyncMock()
    return client


@pytest.fixture
def mock_database() -> Database:
    """Fixture providing a mock database."""
    db = Mock(spec=Database)
    db.downloaded = Mock(return_value=False)
    db.set_downloaded = Mock()
    db.set_failed = Mock()
    return db


@pytest.fixture
def problematic_album_metadata() -> AlbumMetadata:
    """Fixture providing album metadata that would cause filepath issues."""
    metadata = Mock(spec=AlbumMetadata)
    metadata.album = "Very Long Album Name That Exceeds Normal Filesystem Limits And Contains Special Characters <>/|*?"
    metadata.artist = "Very Long Artist Name That Also Exceeds Normal Limits And Has Unicode Characters ñáéíóú"
    metadata.year = 2023
    metadata.format = "FLAC"
    metadata.bit_depth = 24
    metadata.sampling_rate = 96
    metadata.covers = Mock()
    metadata.disctotal = 1

    long_path = f"{metadata.artist} - {metadata.album} ({metadata.year}) [{metadata.format}] [{metadata.bit_depth}B-{metadata.sampling_rate}kHz]"
    metadata.format_folder_path = Mock(return_value=long_path)
    return metadata


@pytest.fixture
def problematic_track_metadata(
    problematic_album_metadata: AlbumMetadata,
) -> TrackMetadata:
    """Fixture providing track metadata that would cause filepath issues."""
    metadata = Mock(spec=TrackMetadata)
    metadata.title = "Very Long Track Title That Exceeds Normal Limits And Contains Special Characters <>/|*?"
    metadata.artist = problematic_album_metadata.artist
    metadata.album = problematic_album_metadata.album
    metadata.tracknumber = 1
    metadata.discnumber = 1
    metadata.info = Mock()
    metadata.info.id = "test_track_id"

    track_path = f"{metadata.tracknumber:02d}. {metadata.artist} - {metadata.title}"
    metadata.format_track_path = Mock(return_value=track_path)
    return metadata


@pytest.fixture
def mock_downloadable() -> Downloadable:
    """Fixture providing a mock downloadable."""
    downloadable = Mock(spec=Downloadable)
    downloadable.extension = "flac"
    downloadable.size = AsyncMock(return_value=1024000)
    downloadable.download = AsyncMock()
    downloadable.source = "qobuz"
    return downloadable


def test_direct_album_folder_path_handling(
    integration_config: Config,
    mock_client: Client,
    mock_database: Database,
    problematic_album_metadata: AlbumMetadata,
    temp_download_dir: str,
) -> None:
    """Test album folder path handling directly without complex async resolution."""
    pending_album = PendingAlbum(
        id="test_album_id",
        client=mock_client,
        config=integration_config,
        db=mock_database,
    )

    # Test the _album_folder method directly
    album_folder = pending_album._album_folder(
        temp_download_dir, problematic_album_metadata
    )

    # Check that the folder path is reasonable
    folder_name = os.path.basename(album_folder)
    assert len(folder_name) <= 150
    assert album_folder.startswith(temp_download_dir)

    # Test with source subdirectories
    integration_config.session.downloads.source_subdirectories = True
    album_folder_with_source = pending_album._album_folder(
        temp_download_dir, problematic_album_metadata
    )
    assert "Qobuz" in album_folder_with_source
    folder_name_with_source = os.path.basename(album_folder_with_source)
    assert len(folder_name_with_source) <= 150


def test_direct_track_path_handling(
    integration_config: Config,
    problematic_track_metadata: TrackMetadata,
    mock_downloadable: Downloadable,
    mock_database: Database,
    temp_download_dir: str,
) -> None:
    """Test track path handling directly without complex async resolution."""
    # Create a track with a very long folder path (simulating the real-world error)
    long_folder = os.path.join(
        temp_download_dir,
        "Very Long Artist Name That Also Exceeds Normal Limits And Has Unicode Characters ñáéíóú - Very Long Album Name That Exceeds Normal Filesystem Limits And Contains Special Characters (2023) [FLAC] [24B-96kHz]",
    )

    track = Track(
        meta=problematic_track_metadata,
        downloadable=mock_downloadable,
        config=integration_config,
        folder=long_folder,
        cover_path=None,
        db=mock_database,
    )

    # Test the _set_download_path method directly
    track._set_download_path()

    # Check that the resulting path is reasonable
    assert len(track.download_path) <= 250
    assert track.download_path.endswith(".flac")
    assert track.download_path  # Should not be empty

    # Test with different truncate_to values
    for truncate_to in [50, 100, 200]:
        integration_config.session.filepaths.truncate_to = truncate_to
        track._set_download_path()

        if truncate_to > 0:
            filename = os.path.basename(track.download_path)
            filename_without_ext = filename.rsplit(".", 1)[0]
            assert len(filename_without_ext) <= truncate_to

        assert len(track.download_path) <= 250


@pytest.mark.parametrize(
    ("restrict_characters", "source_subdirs"),
    [
        (True, False),
        (False, True),
        (True, True),
        (False, False),
    ],
)
def test_filepath_handling_with_various_configs(
    integration_config: Config,
    mock_client: Client,
    mock_database: Database,
    problematic_album_metadata: AlbumMetadata,
    problematic_track_metadata: TrackMetadata,
    mock_downloadable: Downloadable,
    restrict_characters: bool,
    source_subdirs: bool,
    temp_download_dir: str,
) -> None:
    """Test filepath handling with various configuration combinations."""
    integration_config.session.filepaths.restrict_characters = restrict_characters
    integration_config.session.downloads.source_subdirectories = source_subdirs

    pending_album = PendingAlbum(
        id="test_album_id",
        client=mock_client,
        config=integration_config,
        db=mock_database,
    )

    # Test the _album_folder method directly
    album_folder = pending_album._album_folder(
        temp_download_dir, problematic_album_metadata
    )

    # Check source subdirectory handling
    if source_subdirs:
        assert "Qobuz" in album_folder

    # Check path lengths are reasonable
    folder_name = os.path.basename(album_folder)
    assert len(folder_name) <= 150

    # Test track path handling with the same config
    track = Track(
        meta=problematic_track_metadata,
        downloadable=mock_downloadable,
        config=integration_config,
        folder=album_folder,
        cover_path=None,
        db=mock_database,
    )

    track._set_download_path()
    assert len(track.download_path) <= 250
    assert track.download_path.endswith(".flac")


@pytest.mark.asyncio
async def test_directory_creation_failure_fallback(
    integration_config: Config,
    mock_client: Client,
    mock_database: Database,
    problematic_track_metadata: TrackMetadata,
    mock_downloadable: Downloadable,
) -> None:
    """Test that directory creation failures are handled with fallback."""
    # Create a track with an impossible directory path
    track = Track(
        meta=problematic_track_metadata,
        downloadable=mock_downloadable,
        config=integration_config,
        folder="/definitely/invalid/path/that/cannot/be/created",
        cover_path=None,
        db=mock_database,
    )

    with patch("tempfile.gettempdir", return_value="/tmp"):
        await track.preprocess()

    # Should have fallen back to a temp directory
    assert "streamrip_fallback" in track.folder
    assert track.download_path  # Should have a valid download path


@pytest.mark.parametrize("truncate_to", [50, 100, 200, 0])
def test_track_path_truncation_integration(
    integration_config: Config,
    problematic_track_metadata: TrackMetadata,
    mock_downloadable: Downloadable,
    mock_database: Database,
    truncate_to: int,
) -> None:
    """Test track path truncation with various truncate_to values."""
    integration_config.session.filepaths.truncate_to = truncate_to

    track = Track(
        meta=problematic_track_metadata,
        downloadable=mock_downloadable,
        config=integration_config,
        folder="/tmp/test",
        cover_path=None,
        db=mock_database,
    )

    track._set_download_path()

    if truncate_to > 0:
        # Check that the filename part is truncated
        filename = os.path.basename(track.download_path)
        filename_without_ext = filename.rsplit(".", 1)[0]
        assert len(filename_without_ext) <= truncate_to

    # Path should always be reasonable length overall
    assert len(track.download_path) <= 250


def test_real_world_error_case_simulation(
    integration_config: Config, mock_database: Database, mock_downloadable: Downloadable
) -> None:
    """Test simulation of the real-world error cases from the issue."""
    # Simulate the exact problematic paths from the error messages
    error_cases = [
        {
            "folder": "M:/The London Metropolitan Orchestra, Elliot Goldenthal, Steven Mercurio, Jonathan Sheffer, The Mask Orchestra, The Pickled Heads Band - Titus - Original Motion Picture Soundtrack (2000) [FLAC] [16B-44.1kHz]",
            "filename": "11. Elliot Goldenthal - Pickled Heads (Instrumental)",
        },
        {
            "folder": "M:/Toronto Symphony Orchestra, Gustavo Gimeno, Isabel Leonard, Paul Appleby, Derek Welton - Stravinsky Pulcinella, ballet with song in one act, K034 XIV. Tarantella (2025) [FLAC] [24B-96kHz]",
            "filename": "01. Toronto Symphony Orchestra - Pulcinella, ballet with song in one act, K034 XIV. Tarantella",
        },
    ]

    for case in error_cases:
        # Create mock metadata that would generate these paths
        mock_metadata = Mock(spec=TrackMetadata)
        mock_metadata.format_track_path = Mock(return_value=case["filename"])

        track = Track(
            meta=mock_metadata,
            downloadable=mock_downloadable,
            config=integration_config,
            folder=case["folder"],
            cover_path=None,
            db=mock_database,
        )

        track._set_download_path()

        # The resulting path should be manageable
        assert len(track.download_path) <= 250
        assert track.download_path.endswith(".flac")

        # Should not be empty
        assert track.download_path


@pytest.mark.parametrize(
    "unicode_content",
    [
        "Artista Español - Álbum con Acentos",
        "Русский Исполнитель - Русский Альбом",
        "日本のアーティスト - 日本のアルバム",
        "Künstler - Ümlauts und Spëcial Chärs",
    ],
)
def test_unicode_filepath_handling(
    integration_config: Config,
    mock_database: Database,
    mock_downloadable: Downloadable,
    unicode_content: str,
) -> None:
    """Test filepath handling with various unicode characters."""
    mock_metadata = Mock(spec=TrackMetadata)
    mock_metadata.format_track_path = Mock(return_value=unicode_content)

    track = Track(
        meta=mock_metadata,
        downloadable=mock_downloadable,
        config=integration_config,
        folder="/tmp/test",
        cover_path=None,
        db=mock_database,
    )

    track._set_download_path()

    # Should handle unicode gracefully
    assert track.download_path
    assert track.download_path.endswith(".flac")
    assert len(track.download_path) <= 250

    # Test with character restriction
    integration_config.session.filepaths.restrict_characters = True
    track._set_download_path()

    # Should still work with restriction
    assert track.download_path
    assert track.download_path.endswith(".flac")


def test_real_world_windows_error_case(
    integration_config: Config, mock_database: Database, mock_downloadable: Downloadable
) -> None:
    """Test the exact error case from the user's Windows example."""
    # Simulate the exact problematic path from the error message
    problematic_folder = "M:/Toronto Symphony Orchestra, Gustavo Gimeno, Isabel Leonard, Paul Appleby, Derek Welton - Stravinsky Pulcinella, ballet with song in one act, K034 XIV. Tarantella (2025) [FLAC] [24B-96kHz]"
    problematic_filename = "01. Toronto Symphony Orchestra - Pulcinella, ballet with song in one act, K034 XIV. Tarantella"

    # Create mock metadata that would generate this path
    mock_metadata = Mock(spec=TrackMetadata)
    mock_metadata.format_track_path = Mock(return_value=problematic_filename)

    track = Track(
        meta=mock_metadata,
        downloadable=mock_downloadable,
        config=integration_config,
        folder=problematic_folder,
        cover_path=None,
        db=mock_database,
    )

    # This should not raise an exception and should produce a manageable path
    track._set_download_path()

    # Verify the path is manageable (Windows has a 260 character limit)
    assert len(track.download_path) <= 250
    assert track.download_path.endswith(".flac")
    assert track.download_path  # Should not be empty

    # The filename part should be truncated if necessary
    filename = os.path.basename(track.download_path)
    assert len(filename) <= 200  # Leave room for folder path

    print(
        f"Original problematic path would be: {len(problematic_folder + '/' + problematic_filename + '.flac')} characters"
    )
    print(f"Handled path is: {len(track.download_path)} characters")
    print(f"Final path: {track.download_path}")
