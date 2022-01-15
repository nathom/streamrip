"""Bases that handle parsing and downloading media. """

import abc
import concurrent.futures
import hashlib
import logging
import os
import re
import shutil
import subprocess
from tempfile import gettempdir
from typing import (
    Any,
    Dict,
    Generator,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from click import echo, secho, style
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from pathvalidate import sanitize_filepath

from . import converter
from .clients import Client, DeezloaderClient
from .constants import (
    ALBUM_KEYS,
    FLAC_MAX_BLOCKSIZE,
    FOLDER_FORMAT,
    TRACK_FORMAT,
)
from .downloadtools import DownloadPool, DownloadStream
from .exceptions import (
    InvalidQuality,
    InvalidSourceError,
    ItemExists,
    NonStreamable,
    PartialFailure,
    TooLargeCoverArt,
)
from .metadata import TrackMetadata
from .utils import (
    clean_filename,
    clean_format,
    decrypt_mqa_file,
    downsize_image,
    ext,
    get_container,
    get_cover_urls,
    get_stats_from_quality,
    get_tqdm_bar,
    safe_get,
    tidal_cover_url,
    tqdm_stream,
)

logger = logging.getLogger("streamrip")

TYPE_REGEXES = {
    "remaster": re.compile(r"(?i)(re)?master(ed)?"),
    "extra": re.compile(r"(?i)(anniversary|deluxe|live|collector|demo|expanded)"),
}


class Media(abc.ABC):
    """An interface for a downloadable item."""

    @abc.abstractmethod
    def download(self, **kwargs):
        """Download the item.

        :param kwargs:
        """
        pass

    @abc.abstractmethod
    def load_meta(self, **kwargs):
        """Load all of the metadata for an item.

        :param kwargs:
        """
        pass

    @abc.abstractmethod
    def tag(self, **kwargs):
        """Tag this item with metadata, if applicable.

        :param kwargs:
        """
        pass

    @abc.abstractmethod
    def convert(self, **kwargs):
        """Convert this item between file formats.

        :param kwargs:
        """
        pass

    @abc.abstractmethod
    def __repr__(self):
        """Return a string representation of the item."""
        pass

    @abc.abstractmethod
    def __str__(self):
        """Get a readable representation of the item."""
        pass

    @property
    @abc.abstractmethod
    def type(self):
        """Return the type of the item."""
        pass

    @property
    @abc.abstractmethod
    def downloaded_ids(self):
        """If the item is a collection, this is a set of downloaded IDs."""
        pass

    @downloaded_ids.setter
    def downloaded_ids(self, other):
        pass

    @property
    @abc.abstractmethod
    def id(self):
        pass

    @id.setter
    def id(self, other):
        pass


class Track(Media):
    """Represents a downloadable track.

    Loading metadata as a single track:
    >>> t = Track(client, id='20252078')
    >>> t.load_meta()  # load metadata from api

    Loading metadata as part of an Album:
    >>> t = Track.from_album_meta(api_track_dict, client)

    where `api_track_dict` is a track entry in an album tracklist.

    Downloading and tagging:
    >>> t.download()
    >>> t.tag()
    """

    id = None
    downloaded_ids: set = set()
    downloaded: bool = False
    tagged: bool = False
    converted: bool = False

    quality: int
    folder: str
    meta: TrackMetadata

    final_path: str
    container: str

    def __init__(self, client: Client, **kwargs):
        """Create a track object.

        The only required parameter is client, but passing at an id is
        highly recommended. Every value in kwargs will be set as an attribute
        of the object. (TODO: make this safer)

        :param track_id: track id returned by Qobuz API
        :type track_id: Optional[Union[str, int]]
        :param client: qopy client
        :type client: Client
        :param meta: TrackMetadata object
        :type meta: Optional[TrackMetadata]
        :param kwargs: id, filepath_format, meta, quality, folder
        """
        logger.debug(kwargs)

        self.client = client
        self.__dict__.update(kwargs)

        self.part_of_tracklist = kwargs.get("part_of_tracklist", False)

        if isinstance(kwargs.get("meta"), TrackMetadata):
            self.meta = kwargs["meta"]

        if (u := kwargs.get("cover_url")) is not None:
            logger.debug("Cover url: %s", u)
            self.cover_url = u

    def load_meta(self, **kwargs):
        """Send a request to the client to get metadata for this Track.

        Usually only called for single tracks and last.fm playlists.
        """
        assert self.id is not None, "id must be set before loading metadata"

        source = self.client.source

        self.resp = self.client.get(self.id, media_type="track")
        self.meta = TrackMetadata(
            track=self.resp, source=source
        )  # meta dict -> TrackMetadata object

        # Because the cover urls are not parsed when only the track metadata
        # is loaded, we need to do this ourselves

        # Default to large if chosen size is not available
        self.cover_url = self.meta.cover_urls.get(
            kwargs.get("embed_cover_size", "large"),
            self.meta.cover_urls.get("large"),
        )

    def _prepare_download(self, **kwargs):
        """Do preprocessing before downloading items.

        It creates the directories, downloads cover art, and (optionally)
        downloads booklets.

        :param kwargs:
        """
        # args override attributes
        self.quality = min(
            kwargs["quality"], self.client.max_quality, self.meta.quality
        )

        self.folder = kwargs["parent_folder"] or self.folder

        if not self.part_of_tracklist and kwargs["add_singles_to_folder"]:
            self.folder = os.path.join(
                self.folder,
                clean_format(
                    kwargs.get("folder_format", FOLDER_FORMAT),
                    self.meta.get_album_formatter(self.quality),
                    restrict=kwargs.get("restrict_filenames", False),
                ),
            )

        self.file_format = kwargs.get("track_format", TRACK_FORMAT)

        self.folder = sanitize_filepath(self.folder, platform="auto")
        self.format_final_path(
            restrict=kwargs.get("restrict_filenames", False)
        )  # raises: ItemExists

        os.makedirs(self.folder, exist_ok=True)

        if hasattr(self, "cover_url"):
            try:
                self.download_cover(
                    width=kwargs.get("max_artwork_width", 999999),
                    height=kwargs.get("max_artwork_height", 999999),
                )  # only downloads for playlists and singles
            except ItemExists as e:
                logger.debug(e)

        self.path = os.path.join(gettempdir(), f"{hash(self.id)}_{self.quality}.tmp")

    def download(  # noqa
        self,
        quality: int = 3,
        parent_folder: str = "StreamripDownloads",
        progress_bar: bool = True,
        **kwargs,
    ):
        """Download the track.

        :param quality: (0, 1, 2, 3, 4)
        :type quality: int
        :param folder: folder to download the files to
        :type folder: Optional[Union[str, os.PathLike]]
        :param progress_bar: turn on/off progress bar
        :type progress_bar: bool
        """
        if not self.part_of_tracklist and not self.client.source == "soundcloud":
            secho(f"Downloading {self!s}\n", bold=True)

        self._prepare_download(
            quality=quality,
            parent_folder=parent_folder,
            progress_bar=progress_bar,
            **kwargs,
        )

        if self.client.source == "soundcloud":
            # soundcloud client needs whole dict to get file url
            url_id = self.resp
        else:
            url_id = self.id

        try:
            dl_info = self.client.get_file_url(url_id, self.quality)
        except Exception as e:
            logger.debug(repr(e))
            raise NonStreamable(e)

        if self.client.source == "qobuz":
            if not self.__validate_qobuz_dl_info(dl_info):
                raise NonStreamable("Track is not available for download")

            self.sampling_rate = dl_info.get("sampling_rate")
            self.bit_depth = dl_info.get("bit_depth")

        # --------- Download Track ----------
        if self.client.source in {"qobuz", "tidal"}:
            logger.debug("Downloadable URL found: %s", dl_info.get("url"))
            try:
                download_url = dl_info["url"]
            except KeyError as e:
                if restrictions := dl_info["restrictions"]:
                    # Turn CamelCase code into a readable sentence
                    words = re.findall(r"([A-Z][a-z]+)", restrictions[0]["code"])
                    raise NonStreamable(
                        words[0] + " " + " ".join(map(str.lower, words[1:])) + "."
                    )

                secho(f"Panic: {e} dl_info = {dl_info}", fg="red")
                raise NonStreamable

            _quick_download(download_url, self.path, desc=self._progress_desc)

        elif isinstance(self.client, DeezloaderClient):
            _quick_download(dl_info["url"], self.path, desc=self._progress_desc)

        elif self.client.source == "deezer":
            # We can only find out if the requested quality is available
            # after the streaming request is sent for deezer

            try:
                stream = DownloadStream(
                    dl_info["url"], source="deezer", item_id=self.id
                )
            except NonStreamable:
                self.id = dl_info["fallback_id"]
                dl_info = self.client.get_file_url(self.id, self.quality)
                assert isinstance(dl_info, dict)
                stream = DownloadStream(
                    dl_info["url"], source="deezer", item_id=self.id
                )

            stream_size = len(stream)
            stream_quality = dl_info["size_to_quality"][stream_size]
            if self.quality != stream_quality:
                # The chosen quality is not available
                self.quality = stream_quality
                self.format_final_path(
                    restrict=kwargs.get("restrict_filenames", False)
                )  # If the extension is different

            with open(self.path, "wb") as file:
                for chunk in tqdm_stream(stream, desc=self._progress_desc):
                    file.write(chunk)

        elif self.client.source == "soundcloud":
            self._soundcloud_download(dl_info)

        else:
            raise InvalidSourceError(self.client.source)

        if (
            self.client.source == "tidal"
            and isinstance(dl_info, dict)
            and dl_info.get("enc_key", False)
        ):
            out_path = f"{self.path}_dec"
            logger.debug("Decrypting MQA file")
            decrypt_mqa_file(self.path, out_path, dl_info["enc_key"])
            self.path = out_path

        if not kwargs.get("stay_temp", False):
            self.move(self.final_path)

        logger.debug("Downloaded: %s -> %s", self.path, self.final_path)

        self.downloaded = True

        if not kwargs.get("keep_cover", True) and hasattr(self, "cover_path"):
            os.remove(self.cover_path)

    def __validate_qobuz_dl_info(self, info: dict) -> bool:
        """Check if the download info dict returned by Qobuz is downloadable.

        :param info:
        :type info: dict
        :rtype: bool
        """
        return all(
            (
                info.get("sampling_rate"),
                info.get("bit_depth"),
                not info.get("sample"),
            )
        )

    def move(self, path: str):
        """Move the Track and set self.path to the new path.

        :param path:
        :type path: str
        """
        os.makedirs(os.path.dirname(path), exist_ok=True)

        try:
            shutil.move(self.path, path)
        except FileNotFoundError as e:
            # This sometimes happens when using Music.app's Auto folder
            logger.debug("%s during shutil.move", e)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            shutil.move(self.path, path)

        self.path = path

    def _soundcloud_download(self, dl_info: dict):
        """Download a soundcloud track.

        This requires a seperate function because there are three methods that
        can be used to download a track:
            * original file downloads
            * direct mp3 downloads
            * hls stream ripping
        All three of these need special processing.

        :param dl_info:
        :type dl_info: dict
        :rtype: str
        """
        logger.debug("dl_info: %s", dl_info)
        if dl_info["type"] == "mp3":
            import m3u8
            import requests

            parsed_m3u = m3u8.loads(requests.get(dl_info["url"]).text)
            self.path += ".mp3"

            with DownloadPool(segment.uri for segment in parsed_m3u.segments) as pool:

                bar = get_tqdm_bar(len(pool), desc=self._progress_desc, unit="Chunk")

                def update_tqdm_bar():
                    bar.update(1)

                pool.download(callback=update_tqdm_bar)
                subprocess.call(
                    (
                        "ffmpeg",
                        "-i",
                        f"concat:{'|'.join(pool.files)}",
                        "-acodec",
                        "copy",
                        "-loglevel",
                        "panic",
                        self.path,
                    )
                )

        elif dl_info["type"] == "original":
            _quick_download(dl_info["url"], self.path, desc=self._progress_desc)

            # if a wav is returned, convert to flac
            engine = converter.FLAC(self.path)
            self.path = f"{self.path}.flac"
            engine.convert(custom_fn=self.path)

            self.final_path = self.final_path.replace(".mp3", ".flac")
            self.quality = 2

    @property
    def type(self) -> str:
        """Return "track".

        :rtype: str
        """
        return "track"

    @property
    def _progress_desc(self) -> str:
        """Get the description that is used on the progress bar.

        :rtype: str
        """
        return style(f"Track {self.meta.tracknumber:02}", fg="blue")

    def download_cover(self, width=999999, height=999999):
        """Download the cover art, if cover_url is given."""
        self.cover_path = os.path.join(gettempdir(), f"cover{hash(self.cover_url)}.jpg")
        logger.debug("Downloading cover from %s", self.cover_url)

        if not os.path.exists(self.cover_path):
            _cover_download(self.cover_url, self.cover_path)
            downsize_image(self.cover_path, width, height)
        else:
            logger.debug("Cover already exists, skipping download")
            raise ItemExists(self.cover_path)

    def format_final_path(self, restrict: bool = False) -> str:
        """Return the final filepath of the downloaded file.

        This uses the `get_formatter` method of TrackMetadata, which returns
        a dict with the keys allowed in formatter strings, and their values in
        the TrackMetadata object.
        """
        formatter = self.meta.get_formatter(max_quality=self.quality)
        logger.debug("Track meta formatter %s", formatter)
        filename = clean_format(self.file_format, formatter, restrict=restrict)
        self.final_path = os.path.join(self.folder, filename)[:250].strip() + ext(
            self.quality, self.client.source
        )

        logger.debug("Formatted path: %s", self.final_path)

        if os.path.isfile(self.final_path):  # track already exists
            self.downloaded = True
            self.tagged = True
            self.path = self.final_path
            raise ItemExists(self.final_path)

        return self.final_path

    @classmethod
    def from_album_meta(cls, album: TrackMetadata, track: dict, client: Client):
        """Return a new Track object initialized with info.

        :param album: album metadata returned by API
        :param pos: index of the track
        :param client: qopy client object
        :type client: Client
        :raises: IndexError
        """
        meta = TrackMetadata(album=album, track=track, source=client.source)
        return cls(client=client, meta=meta, id=track["id"], part_of_tracklist=True)

    @classmethod
    def from_api(cls, item: dict, client: Client):
        """Return a new Track initialized from search result.

        :param item:
        :type item: dict
        :param client:
        :type client: Client
        """
        meta = TrackMetadata(track=item, source=client.source)
        cover_url: Optional[str]
        try:
            if client.source == "qobuz":
                cover_url = item["album"]["image"]["large"]
            elif client.source == "tidal":
                cover_url = tidal_cover_url(item["album"]["cover"], 640)
            elif client.source == "deezer":
                cover_url = item["album"]["cover_big"]
            elif client.source == "soundcloud":
                if (small_url := item["artwork_url"]) is not None:
                    cover_url = small_url.replace("large", "t500x500")
                else:
                    raise KeyError
            else:
                raise InvalidSourceError(client.source)

        except KeyError:
            logger.debug("No cover found")
            cover_url = None

        return cls(
            client=client,
            meta=meta,
            id=item["id"],
            cover_url=cover_url,
        )

    def tag(  # noqa
        self,
        album_meta: dict = None,
        cover: Union[Picture, APIC, MP4Cover] = None,
        embed_cover: bool = True,
        exclude_tags: Optional[Sequence] = None,
        **kwargs,
    ):
        """Tag the track using the stored metadata.

        The info stored in the TrackMetadata object (self.meta) can be updated
        with album metadata if necessary. The cover must be a mutagen cover-type
        object that already has the bytes loaded.

        :param album_meta: album metadata to update Track with
        :type album_meta: dict
        :param cover: initialized mutagen cover object
        :type cover: Union[Picture, APIC]
        :param embed_cover: Embed cover art into file
        :type embed_cover: bool
        """
        assert isinstance(self.meta, TrackMetadata), "meta must be TrackMetadata"
        if not self.downloaded:
            logger.info(
                "Track %s not tagged because it was not downloaded",
                self["title"],
            )
            return

        if self.tagged:
            logger.info(
                "Track %s not tagged because it is already tagged",
                self["title"],
            )
            return

        if album_meta is not None:
            self.meta.add_album_meta(album_meta)  # extend meta with album info

        # TODO: make this cleaner
        if self.converted:
            if self.container == "FLAC":
                audio = FLAC(self.path)
            elif self.container in ("AAC", "ALAC", "MP4"):
                audio = MP4(self.path)
            elif self.container == "MP3":
                audio = ID3()
                try:
                    audio = ID3(self.path)
                except ID3NoHeaderError:
                    audio = ID3()
        else:
            if self.quality in (2, 3, 4):
                self.container = "FLAC"
                logger.debug("Tagging file with %s container", self.container)
                audio = FLAC(self.path)
            elif self.quality <= 1:
                if self.client.source == "tidal":
                    self.container = "AAC"
                    audio = MP4(self.path)
                else:
                    self.container = "MP3"
                    try:
                        audio = ID3(self.path)
                    except ID3NoHeaderError:
                        audio = ID3()

                logger.debug("Tagging file with %s container", self.container)
            else:
                raise InvalidQuality(f'Invalid quality: "{self.quality}"')

        # automatically generate key, value pairs based on container
        tags = self.meta.tags(
            self.container,
            set(exclude_tags) if exclude_tags is not None else None,
        )
        for k, v in tags:
            logger.debug("Setting %s tag to %s", k, v)
            audio[k] = v

        if embed_cover and cover is None:
            assert hasattr(self, "cover_path")
            cover = Tracklist.get_cover_obj(
                self.cover_path, self.container, self.client.source
            )

        if isinstance(audio, FLAC):
            if embed_cover:
                audio.add_picture(cover)
            audio.save()
        elif isinstance(audio, ID3):
            if embed_cover:
                audio.add(cover)
            audio.save(self.path, "v2_version=3")
        elif isinstance(audio, MP4):
            audio["covr"] = [cover]
            audio.save()
        else:
            raise ValueError(f"Unknown container type: {audio}")

        self.tagged = True

    def convert(self, codec: str = "ALAC", **kwargs):
        """Convert the track to another codec.

        Valid values for codec:
            * FLAC
            * ALAC
            * MP3
            * OPUS
            * OGG
            * VORBIS
            * AAC
            * M4A

        :param codec: the codec to convert the track to
        :type codec: str
        :param kwargs:
        """
        if not self.downloaded:
            logger.debug("Track not downloaded, skipping conversion")
            secho("Track not downloaded, skipping conversion", fg="magenta")
            return

        CONV_CLASS = {
            "FLAC": converter.FLAC,
            "ALAC": converter.ALAC,
            "MP3": converter.LAME,
            "OPUS": converter.OPUS,
            "OGG": converter.Vorbis,
            "VORBIS": converter.Vorbis,
            "AAC": converter.AAC,
            "M4A": converter.AAC,
        }

        try:
            self.container = codec.upper()
        except AttributeError:
            secho("Error: No audio codec chosen to convert to.", fg="red")
            exit()

        if not hasattr(self, "final_path"):
            self.format_final_path(kwargs.get("restrict_filenames", False))

        if not os.path.isfile(self.path):
            logger.info("File %s does not exist. Skipping conversion.", self.path)
            secho(f"{self!s} does not exist. Skipping conversion.", fg="red")
            return

        assert (
            self.container in CONV_CLASS
        ), f"Invalid codec {codec}. Must be in {CONV_CLASS.keys()}"

        engine = CONV_CLASS[self.container](
            filename=self.path,
            sampling_rate=kwargs.get("sampling_rate"),
            remove_source=kwargs.get("remove_source", True),
        )
        engine.convert()
        self.path = engine.final_fn
        self.final_path = self.final_path.replace(
            ext(self.quality, self.client.source), f".{engine.container}"
        )

        if not kwargs.get("stay_temp", False):
            self.move(self.final_path)

        self.converted = True

    @property
    def title(self) -> str:
        """Get the title of the track.

        :rtype: str
        """
        try:
            _title = self.meta.title
        except AttributeError:
            raise Exception("Track must be loaded before accessing title")

        if self.meta.explicit:
            _title = f"{_title} (Explicit)"
        return _title

    def get(self, *keys, default=None) -> Any:
        """Safe get method that allows for layered access.

        :param keys:
        :param default:
        """
        return safe_get(self.meta, *keys, default=default)  # type: ignore

    def set(self, key, val):
        """Set attribute `key` to `val`.

        Equivalent to __setitem__. Implemented only for consistency.

        :param key:
        :param val:
        """
        self.__setitem__(key, val)

    def __getitem__(self, key: str) -> Any:
        """Dict-like interface for Track metadata.

        :param key:
        """
        return getattr(self.meta, key)

    def __setitem__(self, key: str, val: Any):
        """Dict-like interface for Track metadata.

        :param key:
        :param val:
        """
        setattr(self.meta, key, val)

    def __repr__(self) -> str:
        """Return a string representation of the track.

        :rtype: str
        """
        return f"<Track - {self['title']}>"

    def __str__(self) -> str:
        """Return a readable string representation of this track.

        :rtype: str
        """
        return f"{self['artist']} - {self['title']}"

    def __bool__(self):
        """Return True."""
        return True


class Video(Media):
    """Only for Tidal."""

    id = None
    downloaded_ids: set = set()

    def __init__(self, client: Client, id: str, **kwargs):
        """Initialize a Video object.

        :param client:
        :type client: Client
        :param id: The TIDAL Video ID
        :type id: str
        :param kwargs: title, explicit, and tracknumber
        """
        self.id = id
        self.client = client

    def load_meta(self, **kwargs):
        """Given an id at contruction, get the metadata of the video."""
        resp = self.client.get(self.id, "video")
        self.title = resp["title"]
        self.explicit = resp["explicit"]
        self.tracknumber = resp["trackNumber"]

    def download(self, **kwargs):
        """Download the Video.

        :param kwargs:
        """

        if not kwargs.get("download_videos", True):
            return

        import m3u8
        import requests

        # secho(
        #     f"Downloading {self.title} (Video). This may take a while.",
        #     fg="blue",
        # )

        self.parent_folder = kwargs.get("parent_folder", "StreamripDownloads")
        url = self.client.get_file_url(self.id, video=True)

        parsed_m3u = m3u8.loads(requests.get(url).text)
        # Asynchronously download the streams

        with DownloadPool(segment.uri for segment in parsed_m3u.segments) as pool:
            bar = get_tqdm_bar(len(pool), desc=self._progress_desc, unit="Chunk")

            def update_tqdm_bar():
                bar.update(1)

            pool.download(callback=update_tqdm_bar)

            # Put the filenames in a tempfile that ffmpeg
            # can read from
            file_list_path = os.path.join(gettempdir(), "__streamrip_video_files")
            with open(file_list_path, "w") as file_list:
                text = "\n".join(f"file '{path}'" for path in pool.files)
                file_list.write(text)

            # Use ffmpeg to concat the files
            subprocess.call(
                (
                    "ffmpeg",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    file_list_path,
                    "-c",
                    "copy",
                    "-loglevel",
                    "panic",
                    self.path,
                )
            )

            os.remove(file_list_path)

    def tag(self, *args, **kwargs):
        """Return False.

        This is a dummy method.

        :param args:
        :param kwargs:
        """
        return False

    @classmethod
    def from_album_meta(cls, track: dict, client: Client):
        """Return a new Video object given an album API response.

        :param track: track dict from album
        :type track: dict
        :param client:
        :type client: Client
        """
        return cls(
            client,
            id=track["id"],
            title=track["title"],
            explicit=track["explicit"],
            tracknumber=track["trackNumber"],
        )

    def convert(self, *args, **kwargs):
        """Return None.

        Dummy method.

        :param args:
        :param kwargs:
        """
        pass

    @property
    def _progress_desc(self) -> str:
        return style(f"Video {self.tracknumber:02}", fg="blue")

    @property
    def path(self) -> str:
        """Get path to download the mp4 file.

        :rtype: str
        """
        os.makedirs(self.parent_folder, exist_ok=True)
        fname = self.title
        if self.explicit:
            fname = f"{fname} (Explicit)"
        if self.tracknumber is not None:
            fname = f"{self.tracknumber:02}. {fname}"

        return os.path.join(self.parent_folder, f"{fname}.mp4")

    @property
    def type(self) -> str:
        """Return "video".

        :rtype: str
        """
        return "video"

    def __str__(self) -> str:
        """Return the title.

        :rtype: str
        """
        return self.title

    def __repr__(self) -> str:
        """Return a string representation of self.

        :rtype: str
        """
        return f"<Video - {self.title}>"

    def __bool__(self):
        """Return True."""
        return True


class YoutubeVideo(Media):
    """Dummy class implemented for consistency with the Media API."""

    id = None
    downloaded_ids = set()

    class DummyClient:
        """Used because YouTube downloads use youtube-dl, not a client."""

        source = "youtube"

    def __init__(self, url: str):
        """Create a YoutubeVideo object.

        :param url: URL to the youtube video.
        :type url: str
        """
        self.id = url
        self.client = self.DummyClient()

    def download(
        self,
        parent_folder: str = "StreamripDownloads",
        download_youtube_videos: bool = False,
        youtube_video_downloads_folder: str = "StreamripDownloads",
        **kwargs,
    ):
        """Download the video using 'youtube-dl'.

        :param parent_folder:
        :type parent_folder: str
        :param download_youtube_videos: True if the video should be downloaded.
        :type download_youtube_videos: bool
        :param youtube_video_downloads_folder: Folder to put videos if
        downloaded.
        :type youtube_video_downloads_folder: str
        :param kwargs:
        """
        secho(f"Downloading url {self.id}", fg="blue")
        filename_formatter = "%(track_number)s.%(track)s.%(container)s"
        filename = os.path.join(parent_folder, filename_formatter)

        assert isinstance(self.id, str)
        p = subprocess.Popen(
            [
                "youtube-dl",
                "-x",  # audio only
                "-q",  # quiet mode
                "--add-metadata",
                "--audio-format",
                "mp3",
                "--embed-thumbnail",
                "-o",
                filename,
                self.id,
            ]
        )

        if download_youtube_videos:
            secho("Downloading video stream", fg="blue")
            pv = subprocess.Popen(
                [
                    "youtube-dl",
                    "-q",
                    "-o",
                    os.path.join(
                        youtube_video_downloads_folder,
                        "%(title)s.%(container)s",
                    ),
                    self.id,
                ]
            )
            pv.wait()
        p.wait()
        self.downloaded_ids.add(self.id)

    def load_meta(self, *args, **kwargs):
        """Return None.

        Dummy method.

        :param args:
        :param kwargs:
        """
        pass

    def tag(self, *args, **kwargs):
        """Return None.

        Dummy method.

        :param args:
        :param kwargs:
        """
        pass

    def convert(self, *args, **kwargs):
        raise NotImplementedError

    def type(self):
        return "youtubevideo"

    def __repr__(self, *args, **kwargs):
        return f"YoutubeVideo({self.url})"

    def __str__(self):
        return repr(self)

    def __bool__(self):
        """Return True."""
        return True


class Booklet:
    """Only for Qobuz."""

    id = None

    def __init__(self, resp: dict):
        """Initialize from the `goodies` field of the Qobuz API response.

        Usage:
        >>> album_meta = client.get('v4m7e0qiorycb', 'album')
        >>> booklet = Booklet(album_meta['goodies'][0])
        >>> booklet.download()

        :param resp:
        :type resp: dict
        """
        self.url: str
        self.description: str

        self.__dict__.update(resp)

    def download(self, parent_folder: str, **kwargs):
        """Download the Booklet.

        :param parent_folder:
        :type parent_folder: str
        :param kwargs:
        """
        fn = clean_filename(self.description, restrict=kwargs.get("restrict_filenames"))
        filepath = os.path.join(parent_folder, f"{fn}.pdf")

        _quick_download(self.url, filepath, "Booklet")

    def type(self) -> str:
        """Return "booklet".

        :rtype: str
        """
        return "booklet"

    def __bool__(self):
        """Return True."""
        return True


class Tracklist(list):
    """A base class for tracklist-like objects.

    Implements methods to give it dict-like behavior. If a Tracklist
    subclass is subscripted with [s: str], it will return an attribute s.
    If it is subscripted with [i: int] it will return the i'th track in
    the tracklist.
    """

    id = None
    # anything not in parentheses or brackets
    essence_regex = re.compile(r"([^\(]+)(?:\s*[\(\[][^\)][\)\]])*")

    def download(self, **kwargs):
        """Download all of the items in the tracklist.

        :param kwargs:
        """
        self._prepare_download(**kwargs)
        if kwargs.get("conversion", False):
            has_conversion = kwargs["conversion"]["enabled"]
        else:
            has_conversion = False
            kwargs["stay_temp"] = False

        if has_conversion:
            target = self._download_and_convert_item
        else:
            target = self._download_item

        # TODO: make this function return the items that have not been downloaded
        failed_downloads: List[Tuple[str, str, str]] = []
        if kwargs.get("concurrent_downloads", True):
            echo()  # To separate cover progress bars and the rest
            with concurrent.futures.ThreadPoolExecutor(
                kwargs.get("max_connections", 3)
            ) as executor:
                future_map = {
                    executor.submit(target, item, **kwargs): item for item in self
                }
                try:
                    concurrent.futures.wait(future_map.keys())
                    for future in future_map.keys():
                        try:
                            future.result()
                        except NonStreamable as e:
                            item = future_map[future]
                            e.print(item)
                            failed_downloads.append(
                                (item.client.source, item.type, item.id)
                            )

                except (KeyboardInterrupt, SystemExit):
                    executor.shutdown()
                    echo("Aborted! May take some time to shutdown.")
                    exit()

        else:
            for item in self:
                if self.client.source != "soundcloud":
                    # soundcloud only gets metadata after `target` is called
                    # message will be printed in `target`
                    secho(f'\nDownloading "{item!s}"', bold=True, fg="green")
                try:
                    target(item, **kwargs)
                except ItemExists:
                    secho(f"{item!s} exists. Skipping.", fg="yellow")
                except NonStreamable as e:
                    e.print(item)
                    failed_downloads.append((item.client.source, item.type, item.id))

        self.downloaded = True

        if failed_downloads:
            raise PartialFailure(failed_downloads)

    def _download_and_convert_item(self, item: Media, **kwargs):
        """Download and convert an item.

        :param item:
        :param kwargs: should contain a `conversion` dict.
        """
        self._download_item(item, **kwargs)
        item.convert(**kwargs["conversion"])

    def _download_item(self, item: Media, **kwargs: Any):
        """Abstract method.

        :param item:
        :param kwargs:
        """
        raise NotImplementedError

    def _prepare_download(**kwargs):
        """Abstract method.

        :param kwargs:
        """
        raise NotImplementedError

    def get(self, key: Union[str, int], default=None):
        """Get an item if key is int, otherwise get an attr.

        :param key: If it is a str, get an attribute. If an int, get the item
        at the index.
        :type key: Union[str, int]
        :param default:
        """
        if isinstance(key, str):
            if hasattr(self, key):
                return getattr(self, key)

            return default

        if isinstance(key, int):
            if 0 <= key < len(self):
                return self[key]

            return default

    def set(self, key, val):
        """For consistency with `Tracklist.get`.

        :param key:
        :param val:
        """
        self.__setitem__(key, val)

    def convert(self, codec="ALAC", **kwargs):
        """Convert every item in `self`.

        Deprecated. Use _download_and_convert_item instead.

        :param codec:
        :param kwargs:
        """
        if sr := kwargs.get("sampling_rate"):
            if sr < 44100:
                logger.warning(
                    "Sampling rate %d is lower than 44.1kHz."
                    "This may cause distortion and ruin the track.",
                    kwargs["sampling_rate"],
                )
            else:
                logger.debug("Downsampling to %skHz", sr / 1000)

        for track in self:
            track.convert(codec, **kwargs)

    @classmethod
    def from_api(cls, item: dict, client: Client):
        """Create an Album object from an API response.

        :param resp: response dict
        :type resp: dict
        :param source: in ('qobuz', 'deezer', 'tidal')
        :type source: str
        """
        info = cls._parse_get_resp(item, client=client)

        # equivalent to Album(client=client, **info)
        return cls(client=client, **info)  # type: ignore

    @staticmethod
    def get_cover_obj(cover_path: str, container: str, source: str):
        """Return an initialized cover object that is reused for every track.

        :param cover_path: Path to the image, must be a JPEG.
        :type cover_path: str
        :param quality: quality ID
        :type quality: int
        :rtype: Union[Picture, APIC]
        """

        def flac_mp3_cover_obj(cover):
            cover_obj = cover()
            cover_obj.type = 3
            cover_obj.mime = "image/jpeg"
            with open(cover_path, "rb") as img:
                cover_obj.data = img.read()

            return cover_obj

        if container == "FLAC":
            cover = Picture
        elif container == "MP3":
            cover = APIC
        elif container in ("AAC", "ALAC", "MP4"):
            cover = MP4Cover
        else:
            raise Exception(container)

        if cover is Picture:
            size_ = os.path.getsize(cover_path)
            if size_ > FLAC_MAX_BLOCKSIZE:
                raise TooLargeCoverArt(
                    f"Not suitable for Picture embed: {size_ / 10 ** 6} MB"
                )
            return flac_mp3_cover_obj(cover)

        elif cover is APIC:
            return flac_mp3_cover_obj(cover)

        elif cover is MP4Cover:
            with open(cover_path, "rb") as img:
                return cover(img.read(), imageformat=MP4Cover.FORMAT_JPEG)

    def download_message(self):
        """Get the message to display after calling `Tracklist.download`.

        :rtype: str
        """
        secho(
            f"\n\nDownloading {self.title} ({self.__class__.__name__})\n",
            fg="magenta",
            bold=True,
        )

    @staticmethod
    def _parse_get_resp(item, client):
        """Abstract.

        :param item:
        :param client:
        """
        raise NotImplementedError

    @staticmethod
    def essence(album: str) -> str:
        """Ignore text in parens/brackets, return all lowercase.

        Used to group two albums that may be named similarly, but not exactly
        the same.
        """
        match = Tracklist.essence_regex.match(album)
        if match:
            return match.group(1).strip().lower()

        return album

    @property
    def type(self) -> str:
        """Return "booklet".

        :rtype: str
        """
        return "booklet"

    @property
    def downloaded_ids(self):
        """Return the IDs of tracks that have been downloaded."""
        raise NotImplementedError

    def __getitem__(self, key):
        """Get an item if key is int, otherwise get an attr.

        :param key:
        """
        if isinstance(key, str):
            return getattr(self, key)

        if isinstance(key, int):
            return super().__getitem__(key)

    def __setitem__(self, key, val):
        """Set an item if key is int, otherwise set an attr.

        :param key:
        :param val:
        """
        if isinstance(key, str):
            setattr(self, key, val)

        if isinstance(key, int):
            super().__setitem__(key, val)

    def __bool__(self):
        """Return True."""
        return True


class Album(Tracklist, Media):
    """Represents a downloadable album.

    >>> resp = client.get('fleetwood mac rumours', 'album')
    >>> album = Album.from_api(resp['items'][0], client)
    >>> album.load_meta()
    >>> album.download()

    """

    downloaded_ids: set = set()
    id = None

    def __init__(self, client: Client, **kwargs):
        """Create a new Album object.

        :param client: a qopy client instance
        :param album_id: album id returned by qobuz api
        :type album_id: Union[str, int]
        :param kwargs:
        """
        self.client = client

        self.sampling_rate = None
        self.bit_depth = None
        self.container: Optional[str] = None

        self.disctotal: int
        self.tracktotal: int
        self.albumartist: str

        # usually an unpacked TrackMetadata.asdict()
        self.__dict__.update(kwargs)

        # to improve from_api method speed
        if kwargs.get("load_on_init", False):
            self.load_meta()

        self.loaded = False
        self.downloaded = False

    def load_meta(self, **kwargs):
        """Load detailed metadata from API using the id."""
        assert hasattr(self, "id"), "id must be set to load metadata"
        resp = self.client.get(self.id, media_type="album")

        # update attributes based on response
        self.meta = self._parse_get_resp(resp, self.client)
        self.__dict__.update(self.meta.asdict())  # used for identification

        if not self.get("streamable", False):
            raise NonStreamable(f"This album is not streamable ({self.id} ID)")

        self._load_tracks(resp, kwargs.get("download_videos", True))
        self.loaded = True

    @classmethod
    def from_api(cls, resp: dict, client: Client):
        """Create an Album object from an API response.

        :param resp:
        :type resp: dict
        :param client:
        :type client: Client
        """
        if client.source == "soundcloud":
            return Playlist.from_api(resp, client)

        info = cls._parse_get_resp(resp, client)
        return cls(client, **info.asdict())

    def _prepare_download(self, **kwargs):
        """Prepare the download of the album.

        :param kwargs:
        """
        # Generate the folder name
        self.folder_format = kwargs.get("folder_format", FOLDER_FORMAT)
        self.quality = min(kwargs.get("quality", 3), self.client.max_quality)

        self.container = get_container(self.quality, self.client.source)
        # necessary to format the folder
        if self.container in ("AAC", "MP3"):
            # lossy codecs don't have these metrics
            self.bit_depth = self.sampling_rate = None

        parent_folder = kwargs.get("parent_folder", "StreamripDownloads")
        if self.folder_format:
            self.folder = self._get_formatted_folder(
                parent_folder, restrict=kwargs.get("restrict_filenames", False)
            )
        else:
            self.folder = parent_folder

        os.makedirs(self.folder, exist_ok=True)

        self.download_message()

        cover_path = _choose_and_download_cover(
            self.cover_urls,
            kwargs.get("embed_cover_size", "large"),
            self.folder,
            kwargs.get("keep_hires_cover", True),
            (
                kwargs.get("max_artwork_width", 999999),
                kwargs.get("max_artwork_height", 999999),
            ),
        )

        if kwargs.get("embed_cover", True):  # embed by default
            logger.debug("Getting cover_obj from %s", cover_path)
            # container generated when formatting folder name
            self.cover_obj = self.get_cover_obj(
                cover_path, self.container, self.client.source
            )
        else:
            self.cover_obj = None

        # Download the booklet if applicable
        if (
            self.get("booklets")
            and kwargs.get("download_booklets", True)
            and not any(f.endswith(".pdf") for f in os.listdir(self.folder))
        ):
            secho("\nDownloading booklets", bold=True)
            for item in self.booklets:
                Booklet(item).download(parent_folder=self.folder)

    def _download_item(self, item: Media, **kwargs: Any):
        """Download an item.

        :param track: The item.
        :type track: Union[Track, Video]
        :param quality:
        :type quality: int
        :param kwargs:
        :rtype: bool
        """
        logger.debug("Downloading track to %s", self.folder)
        if (
            self.disctotal > 1
            and isinstance(item, Track)
            and kwargs.get("folder_format")
        ):
            disc_folder = os.path.join(self.folder, f"Disc {item.meta.discnumber}")
            kwargs["parent_folder"] = disc_folder
        else:
            kwargs["parent_folder"] = self.folder

        quality = kwargs.get("quality", 3)
        kwargs.pop("quality")
        item.download(quality=min(self.quality, quality), **kwargs)

        logger.debug("tagging tracks")
        # deezer tracks come tagged
        if kwargs.get("tag_tracks", True):
            item.tag(
                cover=self.cover_obj,
                embed_cover=kwargs.get("embed_cover", True),
                exclude_tags=kwargs.get("exclude_tags"),
            )

        self.downloaded_ids.add(item.id)

    @staticmethod
    def _parse_get_resp(resp: dict, client: Client) -> TrackMetadata:
        """Parse information from a client.get(query, 'album') call.

        :param resp:
        :type resp: dict
        :rtype: dict
        """
        meta = TrackMetadata(album=resp, source=client.source)
        meta.id = resp["id"]
        return meta

    def _load_tracks(self, resp, download_videos: bool = True):
        """Load the tracks into self from an API response.

        This uses a classmethod to convert an item into a Track object, which
        stores the metadata inside a TrackMetadata object.
        """
        logging.debug("Loading %d tracks to album", self.tracktotal)
        for track in _get_tracklist(resp, self.client.source):
            if track.get("type") == "Music Video":
                if download_videos:
                    self.append(Video.from_album_meta(track, self.client))
            else:
                self.append(
                    Track.from_album_meta(
                        album=self.meta, track=track, client=self.client
                    )
                )

    def _get_formatter(self) -> dict:
        """Get a formatter that is used for naming folders and previews.

        :rtype: dict
        """
        fmt = {key: self.get(key) for key in ALBUM_KEYS}

        # Get minimum of both bit depth and sampling rate
        stats = tuple(
            min(stat1, stat2)
            for stat1, stat2 in zip(
                (self.meta.bit_depth, self.meta.sampling_rate),
                get_stats_from_quality(self.quality),
            )
            if stat1 is not None and stat2 is not None
        )
        logger.debug("Sampling rate, bit depth = %s", stats)

        if not stats:
            stats = (None, None)

        # The quality chosen is not the maximum available quality
        if stats != (fmt.get("sampling_rate"), fmt.get("bit_depth")):
            fmt["bit_depth"] = stats[0]
            fmt["sampling_rate"] = stats[1]

        if sr := fmt.get("sampling_rate"):
            if sr % 1000 == 0:
                # truncate the decimal .0 when converting to str
                fmt["sampling_rate"] = int(sr / 1000)
            else:
                fmt["sampling_rate"] = sr / 1000

        logger.debug("Formatter: %s", fmt)
        return fmt

    def _get_formatted_folder(self, parent_folder: str, restrict: bool = False) -> str:
        """Generate the folder name for this album.

        :param parent_folder:
        :type parent_folder: str
        :param quality:
        :type quality: int
        :rtype: str
        """

        formatted_folder = clean_format(
            self.folder_format,
            self._get_formatter(),
            restrict=restrict,
        )

        return os.path.join(parent_folder, formatted_folder)

    @property
    def title(self) -> str:
        """Get the title of the album.

        :rtype: str
        """
        return self.album

    @title.setter
    def title(self, val: str):
        """Set the title of the Album.

        :param val:
        :type val: str
        """
        self.album = val

    def __repr__(self) -> str:
        """Return a string representation of this Album object.

        :rtype: str
        """
        # Avoid AttributeError if load_on_init key is not set
        if hasattr(self, "albumartist"):
            return f"<Album: {self.albumartist} - {self.title}>"

        return f"<Album: V/A - {self.title}>"

    def __str__(self) -> str:
        """Return a readable string representation of this album.

        :rtype: str
        """
        return f"{self['albumartist']} - {self['title']}"

    def __len__(self) -> int:
        """Get the length of the album.

        :rtype: int
        """
        return self.tracktotal

    def __hash__(self):
        """Hash the album."""
        return hash(self.id)


class Playlist(Tracklist, Media):
    """Represents a downloadable playlist.

    Usage:
    >>> resp = client.search('hip hop', 'playlist')
    >>> pl = Playlist.from_api(resp['items'][0], client)
    >>> pl.load_meta()
    >>> pl.download()
    """

    id = None
    downloaded_ids: set = set()

    def __init__(self, client: Client, **kwargs):
        """Create a new Playlist object.

        :param client: a qopy client instance
        :param album_id: playlist id returned by qobuz api
        :type album_id: Union[str, int]
        :param kwargs:
        """
        self.name: str
        self.client = client
        logger.debug(kwargs)

        for k, v in kwargs.items():
            setattr(self, k, v)

        # to improve from_api method speed
        if kwargs.get("load_on_init"):
            self.load_meta()

        self.loaded = False

    @classmethod
    def from_api(cls, resp: dict, client: Client):
        """Return a Playlist object from an API response.

        :param resp: a single search result entry of a playlist
        :type resp: dict
        :param client:
        :type client: Client
        """
        info = cls._parse_get_resp(resp, client)
        return cls(client, **info)

    def load_meta(self, **kwargs):
        """Send a request to fetch the tracklist from the api.

        :param new_tracknumbers: replace the tracknumber with playlist position
        :type new_tracknumbers: bool
        :param kwargs:
        """
        self.meta = self.client.get(self.id, media_type="playlist")
        logger.debug(self.meta)
        self._load_tracks(**kwargs)
        self.loaded = True

    def _load_tracks(self, new_tracknumbers: bool = True, **kwargs):
        """Parse the tracklist returned by the API.

        :param new_tracknumbers: replace tracknumber tag with playlist position
        :type new_tracknumbers: bool
        """
        if self.client.source == "qobuz":
            self.name = self.meta["name"]
            self.image = self.meta["images"]
            self.creator = safe_get(self.meta, "owner", "name", default="Qobuz")

            tracklist = self.meta["tracks"]["items"]

            def meta_args(track):
                return {"track": track, "album": track["album"]}

        elif self.client.source == "tidal":
            self.name = self.meta["title"]
            self.image = tidal_cover_url(
                self.meta["image"] or self.meta["squareImage"], 640
            )
            self.creator = safe_get(self.meta, "creator", "name", default="TIDAL")

            tracklist = self.meta["tracks"]

            def meta_args(track):
                return {
                    "track": track,
                    "source": self.client.source,
                }

        elif self.client.source == "deezer":
            self.name = self.meta["title"]
            self.image = self.meta["picture_big"]
            self.creator = safe_get(self.meta, "creator", "name", default="Deezer")

            tracklist = self.meta["tracks"]

        elif self.client.source == "soundcloud":
            self.name = self.meta["title"]
            # self.image = self.meta.get("artwork_url").replace("large", "t500x500")
            self.creator = self.meta["user"]["username"]
            tracklist = self.meta["tracks"]

        else:
            raise NotImplementedError

        self.tracktotal = len(tracklist)
        if self.client.source == "soundcloud":
            # No meta is included in soundcloud playlist
            # response, so it is loaded at download time
            for track in tracklist:
                self.append(Track(self.client, id=track["id"]))
        else:
            for track in tracklist:
                # TODO: This should be managed with .m3u files and alike. Arbitrary
                # tracknumber tags might cause conflicts if the playlist files are
                # inside of a library folder
                meta = TrackMetadata(track=track, source=self.client.source)
                cover_url = get_cover_urls(track["album"], self.client.source)[
                    kwargs.get("embed_cover_size", "large")
                ]

                self.append(
                    Track(
                        self.client,
                        id=track.get("id"),
                        meta=meta,
                        cover_url=cover_url,
                        part_of_tracklist=True,
                    )
                )

        logger.debug("Loaded %d tracks from playlist %s", len(self), self.name)

    def _prepare_download(self, parent_folder: str = "StreamripDownloads", **kwargs):
        if kwargs.get("folder_format"):
            fname = clean_filename(self.name, kwargs.get("restrict_filenames", False))
            self.folder = os.path.join(parent_folder, fname)
        else:
            self.folder = parent_folder

        # Used for safe concurrency with tracknumbers instead of an object
        # level that stores an index
        self.__indices = iter(range(1, len(self) + 1))
        self.download_message()

    def _download_item(self, item: Media, **kwargs):
        assert isinstance(item, Track)

        kwargs["parent_folder"] = self.folder
        if self.client.source == "soundcloud":
            item.load_meta()

        if kwargs.get("set_playlist_to_album", False):
            item.meta.album = self.name
            item.meta.albumartist = self.creator

        if kwargs.get("new_tracknumbers", True):
            item.meta.tracknumber = next(self.__indices)
            item.meta.discnumber = 1

        item.download(**kwargs)

        item.tag(
            embed_cover=kwargs.get("embed_cover", True),
            exclude_tags=kwargs.get("exclude_tags"),
        )

        self.downloaded_ids.add(item.id)

    @staticmethod
    def _parse_get_resp(item: dict, client: Client) -> dict:
        """Parse information from a search result returned by a client.search call.

        :param item:
        :type item: dict
        :param client:
        :type client: Client
        """
        if client.source == "qobuz":
            return {
                "name": item["name"],
                "id": item["id"],
            }
        elif client.source == "tidal":
            return {
                "name": item["title"],
                "id": item["uuid"],
            }
        elif client.source == "deezer":
            return {
                "name": item["title"],
                "id": item["id"],
            }
        elif client.source == "soundcloud":
            return {
                "name": item["title"],
                "id": item["permalink_url"],
                "description": item["description"],
                "popularity": f"{item['likes_count']} likes",
                "tracktotal": len(item["tracks"]),
            }

        raise InvalidSourceError(client.source)

    @property
    def title(self) -> str:
        """Get the title.

        :rtype: str
        """
        return self.name

    def __repr__(self) -> str:
        """Return a string representation of this Playlist object.

        :rtype: str
        """
        return f"<Playlist: {self.name}>"

    def tag(self):
        """Raise NotImplementedError."""
        raise NotImplementedError

    def __str__(self) -> str:
        """Return a readable string representation of this track.

        :rtype: str
        """
        return f"{self.name} ({len(self)} tracks)"


class Artist(Tracklist, Media):
    """Represents a downloadable artist.

    Usage:
    >>> resp = client.get('fleetwood mac', 'artist')
    >>> artist = Artist.from_api(resp['items'][0], client)
    >>> artist.load_meta()
    >>> artist.download()
    """

    id = None
    downloaded_ids: set = set()

    def __init__(self, client: Client, **kwargs):
        """Create a new Artist object.

        :param client: a qopy client instance
        :param album_id: artist id returned by qobuz api
        :type album_id: Union[str, int]
        :param kwargs:
        """
        self.client = client
        self.downloaded_ids = set()

        for k, v in kwargs.items():
            setattr(self, k, v)

        # to improve from_api method speed
        if kwargs.get("load_on_init"):
            self.load_meta()

        self.loaded = False

    def load_meta(self, **kwargs):
        """Send an API call to get album info based on id."""
        self.meta = self.client.get(self.id, media_type="artist")
        self._load_albums()
        self.loaded = True

    # override
    def download(self, **kwargs):
        """Download all items in self.

        :param kwargs:
        """
        iterator = self._prepare_download(**kwargs)
        for item in iterator:
            self._download_item(item, **kwargs)

    def _load_albums(self):
        """Load Album objects to self.

        This parses the response of client.get(query, 'artist') responses.
        """
        if self.client.source == "qobuz":
            self.name = self.meta["name"]
            albums = self.meta["albums"]["items"]

        elif self.client.source == "tidal":
            self.name = self.meta["name"]
            albums = self.meta["albums"]

        elif self.client.source == "deezer":
            self.name = self.meta["name"]
            albums = self.meta["albums"]

        else:
            raise InvalidSourceError(self.client.source)

        for album in albums:
            logger.debug("Appending album: %s", album.get("title"))
            self.append(Album.from_api(album, self.client))

    def _prepare_download(
        self,
        parent_folder: str = "StreamripDownloads",
        filters: tuple = (),
        **kwargs,
    ) -> Iterable:
        """Prepare the download.

        :param parent_folder:
        :type parent_folder: str
        :param filters:
        :type filters: tuple
        :param kwargs:
        :rtype: Iterable
        """
        if kwargs.get("folder_format"):
            folder = clean_filename(self.name, kwargs.get("restrict_filenames", False))
            self.folder = os.path.join(parent_folder, folder)
        else:
            self.folder = parent_folder

        logger.debug("Artist folder: %s", folder)
        logger.debug("Length of tracklist %d", len(self))
        logger.debug("Filters: %s", filters)

        final: Iterable
        if "repeats" in filters:
            final = self._remove_repeats(bit_depth=max, sampling_rate=min)
            filters = tuple(f for f in filters if f != "repeats")
        else:
            final = self

        if isinstance(filters, tuple) and self.client.source == "qobuz":
            filter_funcs = (getattr(self, f"_{filter_}") for filter_ in filters)
            for func in filter_funcs:
                final = filter(func, final)

        self.download_message()
        return final

    def _download_item(self, item: Media, **kwargs):
        """Download an item.

        :param item:
        :param parent_folder:
        :type parent_folder: str
        :param quality:
        :type quality: int
        :param kwargs:
        :rtype: bool
        """
        try:
            item.load_meta()
        except NonStreamable as e:
            e.print(item)
            return

        kwargs.pop("parent_folder")
        # always an Album
        try:
            item.download(
                parent_folder=self.folder,
                **kwargs,
            )
        except PartialFailure:
            pass

        self.downloaded_ids.update(item.downloaded_ids)

    @property
    def title(self) -> str:
        """Get the artist name.

        Implemented for consistency.

        :rtype: str
        """
        return self.name

    @classmethod
    def from_api(cls, item: dict, client: Client, source: str = "qobuz"):
        """Create an Artist object from the api response of Qobuz, Tidal, or Deezer.

        :param resp: response dict
        :type resp: dict
        :param source: in ('qobuz', 'deezer', 'tidal')
        :type source: str
        """
        logging.debug("Loading item from API")
        info = cls._parse_get_resp(item, client)

        # equivalent to Artist(client=client, **info)
        return cls(client=client, **info)

    @staticmethod
    def _parse_get_resp(item: dict, client: Client) -> dict:
        """Parse a result from a client.search call.

        :param item: the item to parse
        :type item: dict
        :param client:
        :type client: Client
        """
        if client.source in ("qobuz", "deezer"):
            info = {
                "name": item.get("name"),
                "id": item.get("id"),
            }
        elif client.source == "tidal":
            info = {
                "name": item["name"],
                "id": item["id"],
            }
        else:
            raise InvalidSourceError(client.source)

        return info

    # ----------- Filters --------------

    TYPE_REGEXES = {
        "remaster": re.compile(r"(?i)(re)?master(ed)?"),
        "extra": re.compile(
            r"(?i)(anniversary|deluxe|live|collector|demo|expanded|remix)"
        ),
    }

    def _remove_repeats(self, bit_depth=max, sampling_rate=max) -> Generator:
        """Remove the repeated albums from self.

        May remove different versions of the same album.

        :param bit_depth: either max or min functions
        :param sampling_rate: either max or min functions
        """
        groups: Dict[str, list] = {}
        for album in self:
            if (t := self.essence(album.title)) not in groups:
                groups[t] = []
            groups[t].append(album)

        for group in groups.values():
            assert bit_depth in (min, max) and sampling_rate in (min, max)
            best_bd = bit_depth(a["bit_depth"] for a in group)
            best_sr = sampling_rate(a["sampling_rate"] for a in group)
            for album in group:
                if album["bit_depth"] == best_bd and album["sampling_rate"] == best_sr:
                    yield album
                    break

    def _non_studio_albums(self, album: Album) -> bool:
        """Filter non-studio-albums.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        return (
            album["albumartist"] != "Various Artists"
            and self.TYPE_REGEXES["extra"].search(album.title) is None
        )

    def _features(self, album: Album) -> bool:
        """Filter features.

        This will download only albums where the requested
        artist is the album artist.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        return self["name"] == album["albumartist"]

    def _extras(self, album: Album) -> bool:
        """Filter extras.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        return self.TYPE_REGEXES["extra"].search(album.title) is None

    def _non_remasters(self, album: Album) -> bool:
        """Filter non remasters.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        return self.TYPE_REGEXES["remaster"].search(album.title) is not None

    def _non_albums(self, album: Album) -> bool:
        """Filter releases that are not albums.

        :param artist: usually self
        :param album: the album to check
        :type album: Album
        :rtype: bool
        """
        return len(album) > 1

    # --------- Magic Methods --------

    def __repr__(self) -> str:
        """Return a string representation of this Artist object.

        :rtype: str
        """
        return f"<Artist: {self.name}>"

    def __str__(self) -> str:
        """Return a readable string representation of this Artist.

        :rtype: str
        """
        return self.name

    def __hash__(self):
        """Hash self."""
        return hash(self.id)


class Label(Artist):
    """Represents a downloadable Label."""

    id = None

    def load_meta(self, **kwargs):
        """Load metadata given an id."""
        assert self.client.source == "qobuz", "Label source must be qobuz"

        resp = self.client.get(self.id, "label")
        self.name = resp["name"]
        for album in resp["albums"]["items"]:
            self.append(Album.from_api(album, client=self.client))

        self.loaded = True

    def __repr__(self):
        """Return a string representation of the Label."""
        return f"<Label - {self.name}>"

    def __str__(self) -> str:
        """Return the name of the Label.

        :rtype: str
        """
        return self.name


# ---------- misc utility functions -----------


def _get_tracklist(resp: dict, source: str) -> list:
    """Return the tracklist from an API response.

    :param resp:
    :type resp: dict
    :param source:
    :type source: str
    :rtype: list
    """
    if source == "qobuz":
        return resp["tracks"]["items"]
    if source in ("tidal", "deezer"):
        return resp["tracks"]

    raise NotImplementedError(source)


def _quick_download(url: str, path: str, desc: str = None):
    with open(path, "wb") as file:
        for chunk in tqdm_stream(DownloadStream(url), desc=desc):
            file.write(chunk)


def _cover_download(url: str, path: str):
    _quick_download(url, path, style("Cover", fg="blue"))


def _choose_and_download_cover(
    cover_urls: dict,
    preferred_size: str,
    directory: str,
    keep_hires_cover: bool = True,
    downsize: Tuple[int, int] = (999999, 999999),
) -> str:
    # choose optimal cover size and download it

    hashcode: str = hashlib.md5(
        "".join(
            sorted(
                map(
                    str,
                    cover_urls.values(),
                )
            )
        ).encode("utf-8", errors="ignore")
    ).hexdigest()
    # hashcode: str = hashlib.md5(str(sorted_list(cover_urls.values())).encode('utf-8', errors='replace')).hexdigest()

    temp_cover_path = os.path.join(gettempdir(), f"cover_{hashcode}.jpg")

    secho(f"Downloading cover art ({preferred_size})", bold=True)

    assert (
        preferred_size in cover_urls
    ), f"Invalid cover size. Must be in {cover_urls.keys()}"

    embed_cover_url = cover_urls[preferred_size]
    logger.debug("Chosen cover url: %s", embed_cover_url)
    if not os.path.exists(temp_cover_path):
        # Sometimes a size isn't available. When this is the case, find
        # the first `not None` url.
        if embed_cover_url is None:
            embed_cover_url = next(filter(None, cover_urls.values()))

        logger.debug("Downloading cover from url %s", embed_cover_url)

        _cover_download(embed_cover_url, temp_cover_path)

    hires_cov_path = os.path.join(directory, "cover.jpg")
    if keep_hires_cover and not os.path.exists(hires_cov_path):
        logger.debug("Downloading hires cover")
        _cover_download(cover_urls["original"], hires_cov_path)

    cover_size = os.path.getsize(temp_cover_path)
    if cover_size > FLAC_MAX_BLOCKSIZE:  # 16.77 MB
        secho(
            "Downgrading embedded cover size, too large ({cover_size}).",
            fg="bright_yellow",
        )
        # large is about 600x600px which is guaranteed < 16.7 MB
        _cover_download(cover_urls["large"], temp_cover_path)

    downsize_image(temp_cover_path, *downsize)

    return temp_cover_path
