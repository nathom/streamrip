import shutil

import pytest

from streamrip.config import *

SAMPLE_CONFIG = "tests/test_config.toml"


# Define a fixture to create a sample ConfigData instance for testing
@pytest.fixture()
def sample_config_data() -> ConfigData:
    # Create a sample ConfigData instance here
    # You can customize this to your specific needs for testing
    with open(SAMPLE_CONFIG) as f:
        config_data = ConfigData.from_toml(f.read())
    return config_data


# Define a fixture to create a sample Config instance for testing
@pytest.fixture()
def sample_config() -> Config:
    # Create a sample Config instance here
    # You can customize this to your specific needs for testing
    config = Config(SAMPLE_CONFIG)
    return config


def test_sample_config_data_properties(sample_config_data):
    # Test the properties of ConfigData
    assert sample_config_data.modified is False  # Ensure initial state is not modified


def test_sample_config_data_modification(sample_config_data):
    # Test modifying ConfigData and checking modified property
    sample_config_data.set_modified()
    assert sample_config_data._modified is True


def test_sample_config_data_fields(sample_config_data):
    test_config = ConfigData(
        toml=None,  # type: ignore
        downloads=DownloadsConfig(
            folder="test_folder",
            source_subdirectories=False,
            concurrency=True,
            max_connections=6,
            requests_per_minute=60,
        ),
        qobuz=QobuzConfig(
            use_auth_token=False,
            email_or_userid="test@gmail.com",
            password_or_token="test_pwd",
            app_id="12345",
            quality=3,
            download_booklets=True,
            secrets=["secret1", "secret2"],
        ),
        tidal=TidalConfig(
            user_id="userid",
            country_code="countrycode",
            access_token="accesstoken",
            refresh_token="refreshtoken",
            token_expiry="tokenexpiry",
            quality=3,
            download_videos=True,
        ),
        deezer=DeezerConfig(
            arl="testarl",
            quality=2,
            use_deezloader=True,
            deezloader_warnings=True,
        ),
        soundcloud=SoundcloudConfig(
            client_id="clientid",
            app_version="appversion",
            quality=0,
        ),
        youtube=YoutubeConfig(
            video_downloads_folder="videodownloadsfolder",
            quality=0,
            download_videos=False,
        ),
        lastfm=LastFmConfig(source="qobuz", fallback_source=""),
        filepaths=FilepathsConfig(
            add_singles_to_folder=False,
            folder_format="{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]",
            track_format="{tracknumber}. {artist} - {title}{explicit}",
            restrict_characters=False,
            truncate_to=120,
        ),
        artwork=ArtworkConfig(
            embed=True,
            embed_size="large",
            embed_max_width=-1,
            save_artwork=True,
            saved_max_width=-1,
        ),
        metadata=MetadataConfig(
            set_playlist_to_album=True,
            renumber_playlist_tracks=True,
            exclude=[],
        ),
        qobuz_filters=QobuzDiscographyFilterConfig(
            extras=False,
            repeats=False,
            non_albums=False,
            features=False,
            non_studio_albums=False,
            non_remaster=False,
        ),
        cli=CliConfig(
            text_output=False,
            progress_bars=False,
            max_search_results=100,
        ),
        database=DatabaseConfig(
            downloads_enabled=True,
            downloads_path="downloadspath",
            failed_downloads_enabled=True,
            failed_downloads_path="faileddownloadspath",
        ),
        conversion=ConversionConfig(
            enabled=False,
            codec="ALAC",
            sampling_rate=48000,
            bit_depth=24,
            lossy_bitrate=320,
        ),
        misc=MiscConfig(version="2.0", check_for_updates=True),
        _modified=False,
    )
    assert sample_config_data.downloads == test_config.downloads
    assert sample_config_data.qobuz == test_config.qobuz
    assert sample_config_data.tidal == test_config.tidal
    assert sample_config_data.deezer == test_config.deezer
    assert sample_config_data.soundcloud == test_config.soundcloud
    assert sample_config_data.youtube == test_config.youtube
    assert sample_config_data.lastfm == test_config.lastfm
    assert sample_config_data.artwork == test_config.artwork
    assert sample_config_data.filepaths == test_config.filepaths
    assert sample_config_data.metadata == test_config.metadata
    assert sample_config_data.qobuz_filters == test_config.qobuz_filters
    assert sample_config_data.database == test_config.database
    assert sample_config_data.conversion == test_config.conversion


# def test_config_save_file_called_on_del(sample_config, mocker):
#     sample_config.file.set_modified()
#     mockf = mocker.Mock()
#
#     sample_config.save_file = mockf
#     sample_config.__del__()
#     mockf.assert_called_once()


def test_config_update_on_save():
    tmp_config_path = "tests/config2.toml"
    shutil.copy(SAMPLE_CONFIG, tmp_config_path)
    conf = Config(tmp_config_path)
    conf.file.downloads.folder = "new_folder"
    conf.file.set_modified()
    conf.save_file()
    conf2 = Config(tmp_config_path)
    os.remove(tmp_config_path)

    assert conf2.session.downloads.folder == "new_folder"


# def test_config_update_on_del():
#     tmp_config_path = "tests/config2.toml"
#     shutil.copy(SAMPLE_CONFIG, tmp_config_path)
#     conf = Config(tmp_config_path)
#     conf.file.downloads.folder = "new_folder"
#     conf.file.set_modified()
#     del conf
#     conf2 = Config(tmp_config_path)
#     os.remove(tmp_config_path)
#
#     assert conf2.session.downloads.folder == "new_folder"


def test_config_dont_update_without_set_modified():
    tmp_config_path = "tests/config2.toml"
    shutil.copy(SAMPLE_CONFIG, tmp_config_path)
    conf = Config(tmp_config_path)
    conf.file.downloads.folder = "new_folder"
    del conf
    conf2 = Config(tmp_config_path)
    os.remove(tmp_config_path)

    assert conf2.session.downloads.folder == "test_folder"


# Other tests for the Config class can be added as needed

if __name__ == "__main__":
    pytest.main()
