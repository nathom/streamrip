"""Classes and functions that manage config state."""

import copy
import functools
import logging
import os
import shutil
from dataclasses import dataclass, fields
from pathlib import Path

import click
from tomlkit.api import dumps, parse
from tomlkit.toml_document import TOMLDocument

logger = logging.getLogger("streamrip")

APP_DIR = click.get_app_dir("streamrip")
os.makedirs(APP_DIR, exist_ok=True)
DEFAULT_CONFIG_PATH = os.path.join(APP_DIR, "config.toml")
CURRENT_CONFIG_VERSION = "2.0.6"


class OutdatedConfigError(Exception):
    pass


@dataclass(slots=True)
class QobuzConfig:
    use_auth_token: bool
    email_or_userid: str
    # This is an md5 hash of the plaintext password
    password_or_token: str
    # Do not change
    app_id: str
    quality: int
    # This will download booklet pdfs that are included with some albums
    download_booklets: bool
    # Do not change
    secrets: list[str]


@dataclass(slots=True)
class TidalConfig:
    # Do not change any of the fields below
    user_id: str
    country_code: str
    access_token: str
    refresh_token: str
    # Tokens last 1 week after refresh. This is the Unix timestamp of the expiration
    # time. If you haven't used streamrip in more than a week, you may have to log
    # in again using `rip config --tidal`
    token_expiry: str
    # 0: 256kbps AAC, 1: 320kbps AAC, 2: 16/44.1 "HiFi" FLAC, 3: 24/44.1 "MQA" FLAC
    quality: int
    # This will download videos included in Video Albums.
    download_videos: bool


@dataclass(slots=True)
class DeezerConfig:
    # An authentication cookie that allows streamrip to use your Deezer account
    # See https://github.com/nathom/streamrip/wiki/Finding-Your-Deezer-ARL-Cookie
    # for instructions on how to find this
    arl: str
    # 0, 1, or 2
    # This only applies to paid Deezer subscriptions. Those using deezloader
    # are automatically limited to quality = 1
    quality: int
    # This allows for free 320kbps MP3 downloads from Deezer
    # If an arl is provided, deezloader is never used
    use_deezloader: bool
    # This warns you when the paid deezer account is not logged in and rip falls
    # back to deezloader, which is unreliable
    deezloader_warnings: bool


@dataclass(slots=True)
class SoundcloudConfig:
    # This changes periodically, so it needs to be updated
    client_id: str
    app_version: str
    # Only 0 is available for now
    quality: int


@dataclass(slots=True)
class YoutubeConfig:
    # The path to download the videos to
    video_downloads_folder: str
    # Only 0 is available for now
    quality: int
    # Download the video along with the audio
    download_videos: bool


@dataclass(slots=True)
class DatabaseConfig:
    downloads_enabled: bool
    downloads_path: str
    failed_downloads_enabled: bool
    failed_downloads_path: str


@dataclass(slots=True)
class ConversionConfig:
    enabled: bool
    # FLAC, ALAC, OPUS, MP3, VORBIS, or AAC
    codec: str
    # In Hz. Tracks are downsampled if their sampling rate is greater than this.
    # Value of 48000 is recommended to maximize quality and minimize space
    sampling_rate: int
    # Only 16 and 24 are available. It is only applied when the bit depth is higher
    # than this value.
    bit_depth: int
    # Only applicable for lossy codecs
    lossy_bitrate: int


@dataclass(slots=True)
class QobuzDiscographyFilterConfig:
    # Remove Collectors Editions, live recordings, etc.
    extras: bool
    # Picks the highest quality out of albums with identical titles.
    repeats: bool
    # Remove EPs and Singles
    non_albums: bool
    # Remove albums whose artist is not the one requested
    features: bool
    # Skip non studio albums
    non_studio_albums: bool
    # Only download remastered albums
    non_remaster: bool


@dataclass(slots=True)
class ArtworkConfig:
    # Write the image to the audio file
    embed: bool
    # The size of the artwork to embed. Options: thumbnail, small, large, original.
    # "original" images can be up to 30MB, and may fail embedding.
    # Using "large" is recommended.
    embed_size: str
    # Both of these options limit the size of the embedded artwork. If their values
    # are larger than the actual dimensions of the image, they will be ignored.
    # If either value is -1, the image is left untouched.
    embed_max_width: int
    # Save the cover image at the highest quality as a seperate jpg file
    save_artwork: bool
    # If artwork is saved, downscale it to these dimensions, or ignore if -1
    saved_max_width: int


@dataclass(slots=True)
class MetadataConfig:
    # Sets the value of the 'ALBUM' field in the metadata to the playlist's name.
    # This is useful if your music library software organizes tracks based on album name.
    set_playlist_to_album: bool
    # If part of a playlist, sets the `tracknumber` field in the metadata to the track's
    # position in the playlist instead of its position in its album
    renumber_playlist_tracks: bool
    # The following metadata tags won't be applied
    # See https://github.com/nathom/streamrip/wiki/Metadata-Tag-Names for more info
    exclude: list[str]


@dataclass(slots=True)
class FilepathsConfig:
    # Create folders for single tracks within the downloads directory using the folder_format
    # template
    add_singles_to_folder: bool
    # Available keys: "albumartist", "title", "year", "bit_depth", "sampling_rate",
    # "container", "id", and "albumcomposer"
    folder_format: str
    # Available keys: "tracknumber", "artist", "albumartist", "composer", "title",
    # and "albumcomposer"
    track_format: str
    # Only allow printable ASCII characters in filenames.
    restrict_characters: bool
    # Truncate the filename if it is greater than 120 characters
    # Setting this to false may cause downloads to fail on some systems
    truncate_to: int


@dataclass(slots=True)
class DownloadsConfig:
    # Folder where tracks are downloaded to
    folder: str
    # Put Qobuz albums in a 'Qobuz' folder, Tidal albums in 'Tidal' etc.
    source_subdirectories: bool
    # Put tracks in an album with 2 or more discs into a subfolder named `Disc N`
    disc_subdirectories: bool
    # Download (and convert) tracks all at once, instead of sequentially.
    # If you are converting the tracks, or have fast internet, this will
    # substantially improve processing speed.
    concurrency: bool
    # The maximum number of tracks to download at once
    # If you have very fast internet, you will benefit from a higher value,
    # A value that is too high for your bandwidth may cause slowdowns
    max_connections: int
    requests_per_minute: int


@dataclass(slots=True)
class LastFmConfig:
    # The source on which to search for the tracks.
    source: str
    # If no results were found with the primary source, the item is searched for
    # on this one.
    fallback_source: str


@dataclass(slots=True)
class CliConfig:
    # Print "Downloading {Album name}" etc. to screen
    text_output: bool
    # Show resolve, download progress bars
    progress_bars: bool
    # The maximum number of search results to show in the interactive menu
    max_search_results: int


@dataclass(slots=True)
class MiscConfig:
    version: str
    check_for_updates: bool


HOME = Path.home()
DEFAULT_DOWNLOADS_FOLDER = os.path.join(HOME, "StreamripDownloads")
DEFAULT_DOWNLOADS_DB_PATH = os.path.join(APP_DIR, "downloads.db")
DEFAULT_FAILED_DOWNLOADS_DB_PATH = os.path.join(APP_DIR, "failed_downloads.db")
DEFAULT_YOUTUBE_VIDEO_DOWNLOADS_FOLDER = os.path.join(
    DEFAULT_DOWNLOADS_FOLDER,
    "YouTubeVideos",
)
BLANK_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.toml")
assert os.path.isfile(BLANK_CONFIG_PATH), "Template config not found"


@dataclass(slots=True)
class ConfigData:
    toml: TOMLDocument
    downloads: DownloadsConfig

    qobuz: QobuzConfig
    tidal: TidalConfig
    deezer: DeezerConfig
    soundcloud: SoundcloudConfig
    youtube: YoutubeConfig
    lastfm: LastFmConfig

    filepaths: FilepathsConfig
    artwork: ArtworkConfig
    metadata: MetadataConfig
    qobuz_filters: QobuzDiscographyFilterConfig

    cli: CliConfig
    database: DatabaseConfig
    conversion: ConversionConfig

    misc: MiscConfig

    _modified: bool = False

    @classmethod
    def from_toml(cls, toml_str: str):
        # TODO: handle the mistake where Windows people forget to escape backslash
        toml = parse(toml_str)
        if (v := toml["misc"]["version"]) != CURRENT_CONFIG_VERSION:  # type: ignore
            raise OutdatedConfigError(
                f"Need to update config from {v} to {CURRENT_CONFIG_VERSION}",
            )

        downloads = DownloadsConfig(**toml["downloads"])  # type: ignore
        qobuz = QobuzConfig(**toml["qobuz"])  # type: ignore
        tidal = TidalConfig(**toml["tidal"])  # type: ignore
        deezer = DeezerConfig(**toml["deezer"])  # type: ignore
        soundcloud = SoundcloudConfig(**toml["soundcloud"])  # type: ignore
        youtube = YoutubeConfig(**toml["youtube"])  # type: ignore
        lastfm = LastFmConfig(**toml["lastfm"])  # type: ignore
        artwork = ArtworkConfig(**toml["artwork"])  # type: ignore
        filepaths = FilepathsConfig(**toml["filepaths"])  # type: ignore
        metadata = MetadataConfig(**toml["metadata"])  # type: ignore
        qobuz_filters = QobuzDiscographyFilterConfig(**toml["qobuz_filters"])  # type: ignore
        cli = CliConfig(**toml["cli"])  # type: ignore
        database = DatabaseConfig(**toml["database"])  # type: ignore
        conversion = ConversionConfig(**toml["conversion"])  # type: ignore
        misc = MiscConfig(**toml["misc"])  # type: ignore

        return cls(
            toml=toml,
            downloads=downloads,
            qobuz=qobuz,
            tidal=tidal,
            deezer=deezer,
            soundcloud=soundcloud,
            youtube=youtube,
            lastfm=lastfm,
            artwork=artwork,
            filepaths=filepaths,
            metadata=metadata,
            qobuz_filters=qobuz_filters,
            cli=cli,
            database=database,
            conversion=conversion,
            misc=misc,
        )

    @classmethod
    def defaults(cls):
        with open(BLANK_CONFIG_PATH) as f:
            return cls.from_toml(f.read())

    def set_modified(self):
        self._modified = True

    @property
    def modified(self):
        return self._modified

    def update_toml(self):
        update_toml_section_from_config(self.toml["downloads"], self.downloads)
        update_toml_section_from_config(self.toml["qobuz"], self.qobuz)
        update_toml_section_from_config(self.toml["tidal"], self.tidal)
        update_toml_section_from_config(self.toml["deezer"], self.deezer)
        update_toml_section_from_config(self.toml["soundcloud"], self.soundcloud)
        update_toml_section_from_config(self.toml["youtube"], self.youtube)
        update_toml_section_from_config(self.toml["lastfm"], self.lastfm)
        update_toml_section_from_config(self.toml["artwork"], self.artwork)
        update_toml_section_from_config(self.toml["filepaths"], self.filepaths)
        update_toml_section_from_config(self.toml["metadata"], self.metadata)
        update_toml_section_from_config(self.toml["qobuz_filters"], self.qobuz_filters)
        update_toml_section_from_config(self.toml["cli"], self.cli)
        update_toml_section_from_config(self.toml["database"], self.database)
        update_toml_section_from_config(self.toml["conversion"], self.conversion)

    def get_source(
        self,
        source: str,
    ) -> QobuzConfig | DeezerConfig | SoundcloudConfig | TidalConfig:
        d = {
            "qobuz": self.qobuz,
            "deezer": self.deezer,
            "soundcloud": self.soundcloud,
            "tidal": self.tidal,
        }
        res = d.get(source)
        if res is None:
            raise Exception(f"Invalid source {source}")
        return res


def update_toml_section_from_config(toml_section, config):
    for field in fields(config):
        toml_section[field.name] = getattr(config, field.name)


class Config:
    def __init__(self, path: str, /):
        self.path = path

        with open(path) as toml_file:
            self.file: ConfigData = ConfigData.from_toml(toml_file.read())

        self.session: ConfigData = copy.deepcopy(self.file)

    def save_file(self):
        if not self.file.modified:
            return

        with open(self.path, "w") as toml_file:
            self.file.update_toml()
            toml_file.write(dumps(self.file.toml))

    @staticmethod
    def _update_file(old_path: str, new_path: str):
        """Updates the current config based on a newer config `new_toml`."""
        with open(new_path) as new_conf:
            new_toml = parse(new_conf.read())

        toml_set_user_defaults(new_toml)

        with open(old_path) as old_conf:
            old_toml = parse(old_conf.read())

        update_config(old_toml, new_toml)

        with open(old_path, "w") as f:
            f.write(dumps(new_toml))

    @classmethod
    def update_file(cls, path: str):
        cls._update_file(path, BLANK_CONFIG_PATH)

    @classmethod
    def defaults(cls):
        return cls(BLANK_CONFIG_PATH)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.save_file()


def set_user_defaults(path: str, /):
    """Update the TOML file at the path with user-specific default values."""
    shutil.copy(BLANK_CONFIG_PATH, path)

    with open(path) as f:
        toml = parse(f.read())

    toml_set_user_defaults(toml)

    with open(path, "w") as f:
        f.write(dumps(toml))


def toml_set_user_defaults(toml: TOMLDocument):
    toml["downloads"]["folder"] = DEFAULT_DOWNLOADS_FOLDER  # type: ignore
    toml["database"]["downloads_path"] = DEFAULT_DOWNLOADS_DB_PATH  # type: ignore
    toml["database"]["failed_downloads_path"] = DEFAULT_FAILED_DOWNLOADS_DB_PATH  # type: ignore
    toml["youtube"]["video_downloads_folder"] = DEFAULT_YOUTUBE_VIDEO_DOWNLOADS_FOLDER  # type: ignore


def _get_dict_keys_r(d: dict) -> set[tuple]:
    """Get all possible key combinations in nested dicts.

    See tests/test_config.py for example.
    """
    keys = d.keys()
    ret = set()
    for cur in keys:
        val = d[cur]
        if isinstance(val, dict):
            ret.update((cur, *remaining) for remaining in _get_dict_keys_r(val))
        else:
            ret.add((cur,))
    return ret


def _nested_get(dictionary, *keys, default=None):
    return functools.reduce(
        lambda d, key: d.get(key, default) if isinstance(d, dict) else default,
        keys,
        dictionary,
    )


def _nested_set(dictionary, *keys, val):
    """Nested set. Throws exception if keys are invalid."""
    assert len(keys) > 0
    final = functools.reduce(lambda d, key: d.get(key), keys[:-1], dictionary)
    final[keys[-1]] = val


def update_config(old_with_data: dict, new_without_data: dict):
    """Used to update config when a new config version is detected.

    All data associated with keys that are shared between the old and
    new configs are copied from old to new. The remaining keep their default value.

    Assumes that new_without_data contains default config values of the
    latest version.
    """
    old_keys = _get_dict_keys_r(old_with_data)
    new_keys = _get_dict_keys_r(new_without_data)
    common = old_keys.intersection(new_keys)
    common.discard(("misc", "version"))

    for k in common:
        old_val = _nested_get(old_with_data, *k)
        _nested_set(new_without_data, *k, val=old_val)
