"""The stuff that ties everything together for the CLI to use."""

import concurrent.futures
import html
import logging
import os
import re
from getpass import getpass
from hashlib import md5
from string import Formatter
from typing import Dict, Generator, List, Optional, Tuple, Type, Union

import click
import requests
from tqdm import tqdm

from .bases import Track, Video, YoutubeVideo
from .clients import (
    Client,
    DeezerClient,
    QobuzClient,
    SoundCloudClient,
    TidalClient,
)
from .config import Config
from .constants import (
    CONFIG_PATH,
    DB_PATH,
    LASTFM_URL_REGEX,
    MEDIA_TYPES,
    QOBUZ_INTERPRETER_URL_REGEX,
    SOUNDCLOUD_URL_REGEX,
    URL_REGEX,
    YOUTUBE_URL_REGEX,
)
from .db import MusicDB
from .exceptions import (
    AuthenticationError,
    NonStreamable,
    NoResultsFound,
    ParsingError,
)
from .tracklists import Album, Artist, Label, Playlist, Tracklist
from .utils import extract_interpreter_url

logger = logging.getLogger("streamrip")


Media = Union[
    Type[Album],
    Type[Playlist],
    Type[Artist],
    Type[Track],
    Type[Label],
    Type[Video],
]
MEDIA_CLASS: Dict[str, Media] = {
    "album": Album,
    "playlist": Playlist,
    "artist": Artist,
    "track": Track,
    "label": Label,
    "video": Video,
}


class MusicDL(list):
    """MusicDL."""

    def __init__(
        self,
        config: Optional[Config] = None,
    ):
        """Create a MusicDL object.

        :param config:
        :type config: Optional[Config]
        """
        self.url_parse = re.compile(URL_REGEX)
        self.soundcloud_url_parse = re.compile(SOUNDCLOUD_URL_REGEX)
        self.lastfm_url_parse = re.compile(LASTFM_URL_REGEX)
        self.interpreter_url_parse = re.compile(QOBUZ_INTERPRETER_URL_REGEX)
        self.youtube_url_parse = re.compile(YOUTUBE_URL_REGEX)

        self.config: Config
        if config is None:
            self.config = Config(CONFIG_PATH)
        else:
            self.config = config

        self.clients = {
            "qobuz": QobuzClient(),
            "tidal": TidalClient(),
            "deezer": DeezerClient(),
            "soundcloud": SoundCloudClient(),
        }

        self.db: Union[MusicDB, list]
        if self.config.session["database"]["enabled"]:
            if self.config.session["database"]["path"] is not None:
                self.db = MusicDB(self.config.session["database"]["path"])
            else:
                self.db = MusicDB(DB_PATH)
                self.config.file["database"]["path"] = DB_PATH
                self.config.save()
        else:
            self.db = []

    def handle_urls(self, url: str):
        """Download a url.

        :param url:
        :type url: str
        :raises InvalidSourceError
        :raises ParsingError
        """
        # youtube is handled by youtube-dl, so much of the
        # processing is not necessary
        youtube_urls = self.youtube_url_parse.findall(url)
        if youtube_urls != []:
            self.extend(YoutubeVideo(u) for u in youtube_urls)

        parsed = self.parse_urls(url)
        if not parsed and len(self) == 0:
            if "last.fm" in url:
                message = (
                    f"For last.fm urls, use the {click.style('lastfm', fg='yellow')} "
                    f"command. See {click.style('rip lastfm --help', fg='yellow')}."
                )
            else:
                message = url

            raise ParsingError(message)

        for source, url_type, item_id in parsed:
            if item_id in self.db:
                logger.info(
                    f"ID {item_id} already downloaded, use --no-db to override."
                )
                click.secho(
                    f"ID {item_id} already downloaded, use --no-db to override.",
                    fg="magenta",
                )
                continue

            self.handle_item(source, url_type, item_id)

    def handle_item(self, source: str, media_type: str, item_id: str):
        """Get info and parse into a Media object.

        :param source:
        :type source: str
        :param media_type:
        :type media_type: str
        :param item_id:
        :type item_id: str
        """
        self.assert_creds(source)

        client = self.get_client(source)

        if media_type not in MEDIA_TYPES:
            if "playlist" in media_type:  # for SoundCloud
                media_type = "playlist"

        assert media_type in MEDIA_TYPES, media_type
        item = MEDIA_CLASS[media_type](client=client, id=item_id)
        self.append(item)

    def _get_download_args(self) -> dict:
        """Get the arguments to pass to Media.download.

        :rtype: dict
        """
        return {
            "database": self.db,
            "parent_folder": self.config.session["downloads"]["folder"],
            "folder_format": self.config.session["path_format"]["folder"],
            "track_format": self.config.session["path_format"]["track"],
            "embed_cover": self.config.session["artwork"]["embed"],
            "embed_cover_size": self.config.session["artwork"]["size"],
            "keep_hires_cover": self.config.session["artwork"][
                "keep_hires_cover"
            ],
            "set_playlist_to_album": self.config.session["metadata"][
                "set_playlist_to_album"
            ],
            "stay_temp": self.config.session["conversion"]["enabled"],
            "conversion": self.config.session["conversion"],
            "concurrent_downloads": self.config.session[
                "concurrent_downloads"
            ],
            "new_tracknumbers": self.config.session["metadata"][
                "new_playlist_tracknumbers"
            ],
            "download_videos": self.config.session["tidal"]["download_videos"],
            "download_booklets": self.config.session["qobuz"][
                "download_booklets"
            ],
            "download_youtube_videos": self.config.session["youtube"][
                "download_videos"
            ],
            "youtube_video_downloads_folder": self.config.session["youtube"][
                "video_downloads_folder"
            ],
        }

    def download(self):
        """Download all the items in self."""
        try:
            arguments = self._get_download_args()
        except KeyError:
            self._config_updating_message()
            self.config.update()
            exit()
        except Exception as err:
            self._config_corrupted_message(err)
            exit()

        logger.debug("Arguments from config: %s", arguments)

        source_subdirs = self.config.session["downloads"][
            "source_subdirectories"
        ]
        for item in self:
            if source_subdirs:
                arguments["parent_folder"] = self.__get_source_subdir(
                    item.client.source
                )

            if item is YoutubeVideo:
                item.download(**arguments)
                continue

            arguments["quality"] = self.config.session[item.client.source][
                "quality"
            ]
            if isinstance(item, Artist):
                filters_ = tuple(
                    k for k, v in self.config.session["filters"].items() if v
                )
                arguments["filters"] = filters_
                logger.debug(
                    "Added filter argument for artist/label: %s", filters_
                )

            if not (isinstance(item, Tracklist) and item.loaded):
                logger.debug("Loading metadata")
                try:
                    item.load_meta()
                except NonStreamable:
                    click.secho(
                        f"{item!s} is not available, skipping.", fg="red"
                    )
                    continue

            item.download(**arguments)
            if isinstance(item, Track):
                item.tag()
                if arguments["conversion"]["enabled"]:
                    item.convert(**arguments["conversion"])

            if self.db != [] and hasattr(item, "id"):
                self.db.add(item.id)

    def get_client(self, source: str) -> Client:
        """Get a client given the source and log in.

        :param source:
        :type source: str
        :rtype: Client
        """
        client = self.clients[source]
        if not client.logged_in:
            self.assert_creds(source)
            self.login(client)
        return client

    def login(self, client):
        """Log into a client, if applicable.

        :param client:
        """
        creds = self.config.creds(client.source)
        if not client.logged_in:
            while True:
                try:
                    client.login(**creds)
                    break
                except AuthenticationError:
                    click.secho("Invalid credentials, try again.")
                    self.prompt_creds(client.source)
            if (
                client.source == "qobuz"
                and not creds.get("secrets")
                and not creds.get("app_id")
            ):
                (
                    self.config.file["qobuz"]["app_id"],
                    self.config.file["qobuz"]["secrets"],
                ) = client.get_tokens()
                self.config.save()
            elif client.source == "tidal":
                self.config.file["tidal"].update(client.get_tokens())
                self.config.save()

    def parse_urls(self, url: str) -> List[Tuple[str, str, str]]:
        """Return the type of the url and the id.

        Compatible with urls of the form:
            https://www.qobuz.com/us-en/{type}/{name}/{id}
            https://open.qobuz.com/{type}/{id}
            https://play.qobuz.com/{type}/{id}
            /us-en/{type}/-/{id}

            https://www.deezer.com/us/{type}/{id}
            https://tidal.com/browse/{type}/{id}

        :raises exceptions.ParsingError
        """
        parsed: List[Tuple[str, str, str]] = []

        interpreter_urls = self.interpreter_url_parse.findall(url)
        if interpreter_urls:
            click.secho(
                "Extracting IDs from Qobuz interpreter urls. Use urls "
                "that include the artist ID for faster preprocessing.",
                fg="yellow",
            )
            parsed.extend(
                ("qobuz", "artist", extract_interpreter_url(u))
                for u in interpreter_urls
            )
            url = self.interpreter_url_parse.sub("", url)

        parsed.extend(self.url_parse.findall(url))  # Qobuz, Tidal, Dezer
        soundcloud_urls = self.soundcloud_url_parse.findall(url)
        soundcloud_items = [
            self.clients["soundcloud"].get(u) for u in soundcloud_urls
        ]

        parsed.extend(
            ("soundcloud", item["kind"], url)
            for item, url in zip(soundcloud_items, soundcloud_urls)
        )

        logger.debug(f"Parsed urls: {parsed}")

        return parsed

    def handle_lastfm_urls(self, urls: str):
        """Get info from lastfm url, and parse into Media objects.

        This works by scraping the last.fm page and using a regex to
        find the track titles and artists. The information is queried
        in a Client.search(query, 'track') call and the first result is
        used.

        :param urls:
        """

        # Available keys: ['artist', 'title']
        QUERY_FORMAT: Dict[str, str] = {
            "tidal": "{title}",
            "qobuz": "{title} {artist}",
            "deezer": "{title} {artist}",
            "soundcloud": "{title} {artist}",
        }

        # For testing:
        # https://www.last.fm/user/nathan3895/playlists/12058911
        user_regex = re.compile(
            r"https://www\.last\.fm/user/([^/]+)/playlists/\d+"
        )
        lastfm_urls = self.lastfm_url_parse.findall(urls)
        try:
            lastfm_source = self.config.session["lastfm"]["source"]
            lastfm_fallback_source = self.config.session["lastfm"][
                "fallback_source"
            ]
        except KeyError:
            self._config_updating_message()
            self.config.update()
            exit()
        except Exception as err:
            self._config_corrupted_message(err)
            raise click.Abort

        def search_query(title, artist, playlist) -> bool:
            """Search for a query and add the first result to playlist.

            :param query:
            :type query: str
            :param playlist:
            :type playlist: Playlist
            :rtype: bool
            """

            def try_search(source) -> Optional[Track]:
                if source == lastfm_fallback_source:
                    click.secho("using fallback", fg="red")
                try:
                    query = QUERY_FORMAT[lastfm_source].format(
                        title=title, artist=artist
                    )
                    return next(self.search(source, query, media_type="track"))
                except (NoResultsFound, StopIteration):
                    return None

            track = try_search(lastfm_source) or try_search(
                lastfm_fallback_source
            )
            if track is None:
                return False

            if self.config.session["metadata"]["set_playlist_to_album"]:
                # so that the playlist name (actually the album) isn't
                # amended to include version and work tags from individual tracks
                track.meta.version = track.meta.work = None

            playlist.append(track)
            return True

        for purl in lastfm_urls:
            click.secho(f"Fetching playlist at {purl}", fg="blue")
            title, queries = self.get_lastfm_playlist(purl)

            pl = Playlist(client=self.get_client(lastfm_source), name=title)
            creator_match = user_regex.search(purl)
            if creator_match is not None:
                pl.creator = creator_match.group(1)

            tracks_not_found = 0
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=15
            ) as executor:
                futures = [
                    executor.submit(search_query, title, artist, pl)
                    for title, artist in queries
                ]
                # only for the progress bar
                for search_attempt in tqdm(
                    concurrent.futures.as_completed(futures),
                    total=len(futures),
                    desc="Searching",
                ):
                    if not search_attempt.result():
                        tracks_not_found += 1

            pl.loaded = True

            if tracks_not_found > 0:
                click.secho(
                    f"{tracks_not_found} tracks not found.", fg="yellow"
                )
            self.append(pl)

    def handle_txt(self, filepath: Union[str, os.PathLike]):
        """
        Handle a text file containing URLs. Lines starting with `#` are ignored.

        :param filepath:
        :type filepath: Union[str, os.PathLike]
        :raises OSError
        :raises exceptions.ParsingError
        """
        with open(filepath) as txt:
            self.handle_urls(txt.read())

    def search(
        self,
        source: str,
        query: str,
        media_type: str = "album",
        limit: int = 200,
    ) -> Generator:
        """Universal search.

        :param source:
        :type source: str
        :param query:
        :type query: str
        :param media_type:
        :type media_type: str
        :param limit: Not Implemented
        :type limit: int
        :rtype: Generator
        """
        logger.debug("searching for %s", query)

        client = self.get_client(source)
        results = client.search(query, media_type)

        if isinstance(results, Generator):  # QobuzClient
            for page in results:
                tracklist = (
                    page[f"{media_type}s"]["items"]
                    if media_type != "featured"
                    else page["albums"]["items"]
                )
                for i, item in enumerate(tracklist):
                    yield MEDIA_CLASS[  # type: ignore
                        media_type if media_type != "featured" else "album"
                    ].from_api(item, client)
                    if i > limit:
                        return
        else:
            logger.debug("Not generator")
            items = (
                results.get("data")
                or results.get("items")
                or results.get("collection")
            )
            if items is None:
                raise NoResultsFound(query)
            logger.debug("Number of results: %d", len(items))

            for i, item in enumerate(items):
                logger.debug(item["title"])
                yield MEDIA_CLASS[media_type].from_api(item, client)  # type: ignore
                if i > limit:
                    return

    def preview_media(self, media) -> str:
        """Return a preview string of a Media object.

        :param media:
        """
        if isinstance(media, Album):
            fmt = (
                "{albumartist} - {album}\n"
                "Released on {year}\n{tracktotal} tracks\n"
                "{bit_depth} bit / {sampling_rate} Hz\n"
                "Version: {version}\n"
                "Genre: {genre}"
            )
        elif isinstance(media, Artist):
            fmt = "{name}"
        elif isinstance(media, Track):
            fmt = "{artist} - {title}\nReleased on {year}"
        elif isinstance(media, Playlist):
            fmt = (
                "{title}\n"
                "{tracktotal} tracks\n"
                "{popularity}\n"
                "Description: {description}"
            )
        else:
            raise NotImplementedError

        fields = (fname for _, fname, _, _ in Formatter().parse(fmt) if fname)
        ret = fmt.format(
            **{k: media.get(k, default="Unknown") for k in fields}
        )
        return ret

    def interactive_search(  # noqa
        self, query: str, source: str = "qobuz", media_type: str = "album"
    ):
        """Show an interactive menu that contains search results.

        :param query:
        :type query: str
        :param source:
        :type source: str
        :param media_type:
        :type media_type: str
        """
        results = tuple(self.search(source, query, media_type, limit=50))

        def title(res):
            if isinstance(res[1], Album):
                return f"{res[0]+1}. {res[1].album}"
            elif isinstance(res[1], Track):
                return f"{res[0]+1}. {res[1].meta.title}"
            elif isinstance(res[1], Playlist):
                return f"{res[0]+1}. {res[1].name}"
            else:
                raise NotImplementedError(type(res[1]).__name__)

        def from_title(s):
            num = []
            for char in s:
                if char != ".":
                    num.append(char)
                else:
                    break
            return self.preview_media(results[int("".join(num)) - 1])

        if os.name == "nt":
            from pick import pick

            choice = pick(
                tuple(enumerate(results)),
                title=(
                    f"{source.capitalize()} {media_type} search.\n"
                    "Press SPACE to select, RETURN to download, ctrl-C to exit."
                ),
                options_map_func=title,
                multiselect=True,
            )

            if isinstance(choice, list):
                for item in choice:
                    self.append(item[0][1])
            elif isinstance(choice, tuple):
                self.append(choice[0][1])

            return True
        else:
            from simple_term_menu import TerminalMenu

            menu = TerminalMenu(
                map(title, enumerate(results)),
                preview_command=from_title,
                preview_size=0.5,
                title=(
                    f"{source.capitalize()} {media_type} search.\n"
                    "SPACE - multiselection, ENTER - download, ESC - exit"
                ),
                cycle_cursor=True,
                clear_screen=True,
                multi_select=True,
            )
            choice = menu.show()
            if choice is None:
                return False
            else:
                if isinstance(choice, int):
                    self.append(results[choice])
                elif isinstance(choice, tuple):
                    for i in choice:
                        self.append(results[i])
                return True

    def get_lastfm_playlist(self, url: str) -> Tuple[str, list]:
        """From a last.fm url, find the playlist title and tracks.

        Each page contains 50 results, so `num_tracks // 50 + 1` requests
        are sent per playlist.

        :param url:
        :type url: str
        :rtype: Tuple[str, list]
        """

        logger.debug("Fetching lastfm playlist")

        info = []
        words = re.compile(r"[\w\s]+")
        title_tags = re.compile('title="([^"]+)"')

        def essence(s):
            s = re.sub(r"&#\d+;", "", s)  # remove HTML entities
            return "".join(words.findall(s))

        def get_titles(s):
            titles = title_tags.findall(s)[2:]
            for i in range(0, len(titles) - 1, 2):
                info.append((essence(titles[i]), essence(titles[i + 1])))

        r = requests.get(url)
        get_titles(r.text)
        remaining_tracks_match = re.search(
            r'data-playlisting-entry-count="(\d+)"', r.text
        )
        if remaining_tracks_match is None:
            raise ParsingError("Error parsing lastfm page: %s", r.text)

        total_tracks = int(remaining_tracks_match.group(1))
        logger.debug("Total tracks: %d", total_tracks)
        remaining_tracks = total_tracks - 50

        playlist_title_match = re.search(
            r'<h1 class="playlisting-playlist-header-title">([^<]+)</h1>',
            r.text,
        )
        if playlist_title_match is None:
            raise ParsingError("Error finding title from response")

        playlist_title = html.unescape(playlist_title_match.group(1))

        if remaining_tracks > 0:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=15
            ) as executor:
                last_page = int(remaining_tracks // 50) + int(
                    remaining_tracks % 50 != 0
                )

                futures = [
                    executor.submit(requests.get, f"{url}?page={page}")
                    for page in range(1, last_page + 1)
                ]

            for future in tqdm(
                concurrent.futures.as_completed(futures),
                total=len(futures),
                desc="Scraping playlist",
            ):
                get_titles(future.result().text)

        return playlist_title, info

    def __get_source_subdir(self, source: str) -> str:
        path = self.config.session["downloads"]["folder"]
        return os.path.join(path, source.capitalize())

    def prompt_creds(self, source: str):
        """Prompt the user for credentials.

        :param source:
        :type source: str
        """
        if source == "qobuz":
            click.secho(f"Enter {source.capitalize()} email:", fg="green")
            self.config.file[source]["email"] = input()
            click.secho(
                f"Enter {source.capitalize()} password (will not show on screen):",
                fg="green",
            )
            self.config.file[source]["password"] = md5(
                getpass(prompt="").encode("utf-8")
            ).hexdigest()

            self.config.save()
            click.secho(
                f'Credentials saved to config file at "{self.config._path}"'
            )
        else:
            raise Exception

    def assert_creds(self, source: str):
        """Ensure that the credentials for `source` are valid.

        :param source:
        :type source: str
        """
        assert source in (
            "qobuz",
            "tidal",
            "deezer",
            "soundcloud",
        ), f"Invalid source {source}"
        if source == "deezer":
            # no login for deezer
            return

        if source == "soundcloud":
            return

        if source == "qobuz" and (
            self.config.file[source]["email"] is None
            or self.config.file[source]["password"] is None
        ):
            self.prompt_creds(source)

    def _config_updating_message(self):
        click.secho(
            "Updating config file... Some settings may be lost. Please run the "
            "command again.",
            fg="magenta",
        )

    def _config_corrupted_message(self, err: Exception):
        click.secho(
            "There was a problem with your config file. This happens "
            "sometimes after updates. Run ",
            nl=False,
            fg="red",
        )
        click.secho("rip config --reset ", fg="yellow", nl=False)
        click.secho("to reset it. You will need to log in again.", fg="red")
        click.secho(str(err), fg="red")
