"""The stuff that ties everything together for the CLI to use."""

import concurrent.futures
import html
import logging
import os
import re
import threading
from getpass import getpass
from hashlib import md5
from string import Formatter
from typing import Dict, Generator, List, Optional, Tuple, Type, Union

import requests
from click import secho, style
from tqdm import tqdm

from streamrip.clients import (
    Client,
    DeezerClient,
    DeezloaderClient,
    QobuzClient,
    SoundCloudClient,
    TidalClient,
)
from streamrip.constants import MEDIA_TYPES
from streamrip.exceptions import (
    AuthenticationError,
    IneligibleError,
    ItemExists,
    MissingCredentials,
    NonStreamable,
    NoResultsFound,
    ParsingError,
    PartialFailure,
)
from streamrip.media import (
    Album,
    Artist,
    Label,
    Playlist,
    Track,
    Tracklist,
    Video,
    YoutubeVideo,
)
from streamrip.utils import TQDM_DEFAULT_THEME, set_progress_bar_theme

from . import db
from .config import Config
from .constants import (
    CONFIG_PATH,
    DB_PATH,
    DEEZER_DYNAMIC_LINK_REGEX,
    FAILED_DB_PATH,
    LASTFM_URL_REGEX,
    QOBUZ_INTERPRETER_URL_REGEX,
    SOUNDCLOUD_URL_REGEX,
    URL_REGEX,
    YOUTUBE_URL_REGEX,
)
from .exceptions import DeezloaderFallback
from .utils import extract_deezer_dynamic_link, extract_interpreter_url

logger = logging.getLogger("streamrip")

# ---------------- Constants ------------------ #
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

DB_PATH_MAP = {"downloads": DB_PATH, "failed_downloads": FAILED_DB_PATH}
# ---------------------------------------------- #


class RipCore(list):
    """RipCore."""

    clients = {
        "qobuz": QobuzClient(),
        "tidal": TidalClient(),
        "deezer": DeezerClient(),
        "soundcloud": SoundCloudClient(),
        "deezloader": DeezloaderClient(),
    }

    def __init__(
        self,
        config: Optional[Config] = None,
    ):
        """Create a RipCore object.

        :param config:
        :type config: Optional[Config]
        """
        self.config: Config
        if config is None:
            self.config = Config(CONFIG_PATH)
        else:
            self.config = config

        if (theme := self.config.file["theme"]["progress_bar"]) != TQDM_DEFAULT_THEME:
            set_progress_bar_theme(theme.lower())

        def get_db(db_type: str) -> db.Database:
            db_settings = self.config.session["database"]
            db_class = db.CLASS_MAP[db_type]

            if db_settings[db_type]["enabled"] and db_settings.get("enabled", True):
                default_db_path = DB_PATH_MAP[db_type]
                path = db_settings[db_type]["path"]

                if path:
                    database = db_class(path)
                else:
                    database = db_class(default_db_path)

                    assert config is not None
                    config.file["database"][db_type]["path"] = default_db_path
                    config.save()
            else:
                database = db_class(None, dummy=True)

            return database

        self.db = get_db("downloads")
        self.failed_db = get_db("failed_downloads")

    def handle_urls(self, urls):
        """Download a url.

        :param url:
        :type url: str
        :raises InvalidSourceError
        :raises ParsingError
        """
        if isinstance(urls, str):
            url = urls
        elif isinstance(urls, tuple):
            url = " ".join(urls)
        else:
            raise Exception(f"Urls has invalid type {type(urls)}")

        # youtube is handled by youtube-dl, so much of the
        # processing is not necessary
        youtube_urls = YOUTUBE_URL_REGEX.findall(url)
        if youtube_urls != []:
            self.extend(YoutubeVideo(u) for u in youtube_urls)

        parsed = self.parse_urls(url)
        if not parsed and len(self) == 0:
            if "last.fm" in url:
                message = (
                    f"For last.fm urls, use the {style('lastfm', fg='yellow')} "
                    f"command. See {style('rip lastfm --help', fg='yellow')}."
                )
            else:
                message = f"Cannot find urls in text: {url}"

            raise ParsingError(message)

        for source, url_type, item_id in parsed:
            if item_id in self.db:
                logger.info(
                    f"ID {item_id} already downloaded, use --ignore-db to override."
                )
                secho(
                    f"ID {item_id} already downloaded, use --ignore-db to override.",
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
        session = self.config.session
        logger.debug(session)
        # So that the dictionary isn't searched for the same keys multiple times
        artwork, conversion, filepaths, metadata = (
            session[key] for key in ("artwork", "conversion", "filepaths", "metadata")
        )
        concurrency = session["downloads"]["concurrency"]
        return {
            "restrict_filenames": filepaths["restrict_characters"],
            "parent_folder": session["downloads"]["folder"],
            "folder_format": filepaths["folder_format"],
            "track_format": filepaths["track_format"],
            "embed_cover": artwork["embed"],
            "embed_cover_size": artwork["size"],
            "keep_hires_cover": artwork["keep_hires_cover"],
            "set_playlist_to_album": metadata["set_playlist_to_album"],
            "stay_temp": conversion["enabled"],
            "conversion": conversion,
            "concurrent_downloads": concurrency["enabled"],
            "max_connections": concurrency["max_connections"],
            "new_tracknumbers": metadata["new_playlist_tracknumbers"],
            "download_videos": session["tidal"]["download_videos"],
            "download_booklets": session["qobuz"]["download_booklets"],
            "download_youtube_videos": session["youtube"]["download_videos"],
            "youtube_video_downloads_folder": session["youtube"][
                "video_downloads_folder"
            ],
            "add_singles_to_folder": filepaths["add_singles_to_folder"],
            "max_artwork_width": int(artwork["max_width"]),
            "max_artwork_height": int(artwork["max_height"]),
            "exclude_tags": metadata["exclude"],
        }

    def repair(self, max_items=None):
        """Iterate through the failed_downloads database and retry them.

        :param max_items: The maximum number of items to download.
        """
        if max_items is None:
            max_items = float("inf")

        self.db = db.Downloads(None, dummy=True)
        if self.failed_db.is_dummy:
            secho(
                "Failed downloads database must be enabled in the config file "
                "to repair!",
                fg="red",
            )
            exit()

        for counter, (source, media_type, item_id) in enumerate(self.failed_db):
            if counter >= max_items:
                break

            self.handle_item(source, media_type, item_id)

        self.download()

    def download(self):
        """Download all the items in self."""
        try:
            arguments = self._get_download_args()
        except KeyError as e:
            self._config_updating_message()
            self.config.update()
            logger.debug("Config update error: %s", e)
            exit()
        except Exception as err:
            self._config_corrupted_message(err)
            exit()

        logger.debug("Arguments from config: %s", arguments)

        source_subdirs = self.config.session["downloads"]["source_subdirectories"]
        for item in self:
            # Item already checked in database in handle_urls
            if source_subdirs:
                arguments["parent_folder"] = self.__get_source_subdir(
                    item.client.source
                )

            if item is YoutubeVideo:
                item.download(**arguments)
                continue

            arguments["quality"] = self.config.session[item.client.source]["quality"]
            if isinstance(item, Artist):
                filters_ = tuple(
                    k for k, v in self.config.session["filters"].items() if v
                )
                arguments["filters"] = filters_
                logger.debug("Added filter argument for artist/label: %s", filters_)

            if not isinstance(item, Tracklist) or not item.loaded:
                logger.debug("Loading metadata")
                try:
                    item.load_meta(**arguments)
                except NonStreamable:
                    self.failed_db.add((item.client.source, item.type, item.id))
                    secho(f"{item!s} is not available, skipping.", fg="red")
                    continue

            try:
                item.download(**arguments)
                for item_id in item.downloaded_ids:
                    self.db.add([item_id])
            except NonStreamable as e:
                e.print(item)
                self.failed_db.add((item.client.source, item.type, item.id))
                continue
            except PartialFailure as e:
                # add successful downloads to database?
                for failed_item_info in e.failed_items:
                    self.failed_db.add(failed_item_info)
                continue
            except ItemExists as e:
                secho(f'"{e!s}" already exists. Skipping.', fg="yellow")
                continue

            if hasattr(item, "id"):
                self.db.add(str(item.id))
                for item_id in item.downloaded_ids:
                    self.db.add(str(item_id))

            if isinstance(item, Track):
                item.tag(exclude_tags=arguments["exclude_tags"])
                if arguments["conversion"]["enabled"]:
                    item.convert(**arguments["conversion"])

    def scrape(self, featured_list: str, max_items: int = 500):
        """Download all of the items in a Qobuz featured list.

        :param featured_list: The name of the list. See `rip discover --help`.
        :type featured_list: str
        """
        self.extend(self.search("qobuz", featured_list, "featured", limit=max_items))

    def get_client(self, source: str) -> Client:
        """Get a client given the source and log in.

        :param source:
        :type source: str
        :rtype: Client
        """
        client = self.clients[source]
        if not client.logged_in:
            try:
                self.login(client)
            except DeezloaderFallback:
                client = self.clients["deezloader"]

        return client

    def login(self, client):
        """Log into a client, if applicable.

        :param client:
        """
        creds = self.config.creds(client.source)
        if client.source == "deezer" and creds["arl"] == "":
            if self.config.session["deezer"]["deezloader_warnings"]:
                secho(
                    "Falling back to Deezloader (unstable). If you have a subscription, run ",
                    nl=False,
                    fg="yellow",
                )
                secho("rip config --deezer ", nl=False, bold=True)
                secho("to log in.", fg="yellow")
            raise DeezloaderFallback

        while True:
            try:
                client.login(**creds)
                break
            except AuthenticationError:
                secho("Invalid credentials, try again.", fg="yellow")
                self.prompt_creds(client.source)
                creds = self.config.creds(client.source)
            except MissingCredentials:
                logger.debug("Credentials are missing. Prompting..")
                get_tokens = threading.Thread(
                    target=client._get_app_id_and_secrets, daemon=True
                )
                get_tokens.start()

                self.prompt_creds(client.source)
                creds = self.config.creds(client.source)

                get_tokens.join()

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
        elif (
            client.source == "soundcloud"
            and not creds.get("client_id")
            and not creds.get("app_version")
        ):
            (
                self.config.file["soundcloud"]["client_id"],
                self.config.file["soundcloud"]["app_version"],
            ) = client.get_tokens()
            self.config.save()

        elif client.source == "tidal":
            self.config.file["tidal"].update(client.get_tokens())
            self.config.save()  # only for the expiry stamp

    def parse_urls(self, url: str) -> List[Tuple[str, str, str]]:
        """Return the type of the url and the id.

        Compatible with urls of the form:
            https://www.qobuz.com/us-en/type/name/id
            https://open.qobuz.com/type/id
            https://play.qobuz.com/type/id

            https://www.deezer.com/us/type/id
            https://tidal.com/browse/type/id

        :raises exceptions.ParsingError:
        """
        parsed: List[Tuple[str, str, str]] = []

        interpreter_urls = QOBUZ_INTERPRETER_URL_REGEX.findall(url)
        if interpreter_urls:
            secho(
                "Extracting IDs from Qobuz interpreter urls. Use urls "
                "that include the artist ID for faster preprocessing.",
                fg="yellow",
            )
            parsed.extend(
                ("qobuz", "artist", extract_interpreter_url(u))
                for u in interpreter_urls
            )
            url = QOBUZ_INTERPRETER_URL_REGEX.sub("", url)

        dynamic_urls = DEEZER_DYNAMIC_LINK_REGEX.findall(url)
        if dynamic_urls:
            secho(
                "Extracting IDs from Deezer dynamic link. Use urls "
                "of the form https://www.deezer.com/{country}/{type}/{id} for "
                "faster processing.",
                fg="yellow",
            )
            parsed.extend(
                ("deezer", *extract_deezer_dynamic_link(url)) for url in dynamic_urls
            )

        parsed.extend(URL_REGEX.findall(url))  # Qobuz, Tidal, Deezer
        soundcloud_urls = SOUNDCLOUD_URL_REGEX.findall(url)

        if soundcloud_urls:
            soundcloud_client = self.get_client("soundcloud")
            assert isinstance(soundcloud_client, SoundCloudClient)  # for typing

            # TODO: Make this async
            soundcloud_items = (
                soundcloud_client.resolve_url(u) for u in soundcloud_urls
            )

            parsed.extend(
                ("soundcloud", item["kind"], str(item["id"]))
                for item in soundcloud_items
            )

        logger.debug("Parsed urls: %s", parsed)

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
        user_regex = re.compile(r"https://www\.last\.fm/user/([^/]+)/playlists/\d+")
        lastfm_urls = LASTFM_URL_REGEX.findall(urls)
        try:
            lastfm_source = self.config.session["lastfm"]["source"]
            lastfm_fallback_source = self.config.session["lastfm"]["fallback_source"]
        except KeyError:
            self._config_updating_message()
            self.config.update()
            exit()
        except Exception as err:
            self._config_corrupted_message(err)
            exit()

        # Do not include tracks that have (re)mix, live, karaoke in their titles
        # within parentheses or brackets
        # This will match somthing like "Test (Person Remix]" though, so its not perfect
        banned_words_plain = re.compile(r"(?i)(?:(?:re)?mix|live|karaoke)")
        banned_words = re.compile(
            r"(?i)[\(\[][^\)\]]*?(?:(?:re)?mix|live|karaoke)[^\)\]]*[\]\)]"
        )

        def search_query(title, artist, playlist) -> bool:
            """Search for a query and add the first result to playlist.

            :param query:
            :type query: str
            :param playlist:
            :type playlist: Playlist
            :rtype: bool
            """

            def try_search(source) -> Optional[Track]:
                try:
                    query = QUERY_FORMAT[lastfm_source].format(
                        title=title, artist=artist
                    )
                    query_is_clean = banned_words_plain.search(query) is None

                    search_results = self.search(source, query, media_type="track")
                    track = next(search_results)

                    if query_is_clean:
                        while banned_words.search(track["title"]) is not None:
                            logger.debug("Track title banned for query=%s", query)
                            track = next(search_results)

                    # Because the track is searched as a single we need to set
                    # this manually
                    track.part_of_tracklist = True
                    return track
                except (NoResultsFound, StopIteration):
                    return None

            track = try_search(lastfm_source) or try_search(lastfm_fallback_source)
            if track is None:
                return False

            if self.config.session["metadata"]["set_playlist_to_album"]:
                # so that the playlist name (actually the album) isn't
                # amended to include version and work tags from individual tracks
                track.meta.version = track.meta.work = None

            playlist.append(track)
            return True

        from streamrip.utils import TQDM_BAR_FORMAT

        for purl in lastfm_urls:
            secho(f"Fetching playlist at {purl}", fg="blue")
            title, queries = self.get_lastfm_playlist(purl)

            pl = Playlist(client=self.get_client(lastfm_source), name=title)
            creator_match = user_regex.search(purl)
            if creator_match is not None:
                pl.creator = creator_match.group(1)

            tracks_not_found = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                futures = [
                    executor.submit(search_query, title, artist, pl)
                    for title, artist in queries
                ]
                # only for the progress bar
                for search_attempt in tqdm(
                    concurrent.futures.as_completed(futures),
                    unit="Tracks",
                    dynamic_ncols=True,
                    total=len(futures),
                    desc="Searching...",
                    bar_format=TQDM_BAR_FORMAT,
                ):
                    if not search_attempt.result():
                        tracks_not_found += 1

            pl.loaded = True

            if tracks_not_found > 0:
                secho(f"{tracks_not_found} tracks not found.", fg="yellow")

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
        check_db: bool = False,
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

        if isinstance(client, DeezloaderClient) and media_type == "featured":
            raise IneligibleError(
                "Must have premium Deezer account to access editorial lists."
            )

        results = client.search(query, media_type)

        if media_type == "featured":
            media_type = "album"

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

                    if i >= limit - 1:
                        return
        else:
            items = (
                results.get("data")
                or results.get("items")
                or results.get("collection")
                or results.get("albums", {}).get("data", False)
            )

            if not items:
                raise NoResultsFound(query)

            logger.debug("Number of results: %d", len(items))

            for i, item in enumerate(items):
                logger.debug(item)
                yield MEDIA_CLASS[media_type].from_api(item, client)  # type: ignore
                if i >= limit - 1:
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
        ret = fmt.format(**{k: media.get(k, default="Unknown") for k in fields})
        return ret

    def interactive_search(
        self,
        query: str,
        source: str = "qobuz",
        media_type: str = "album",
        limit: int = 50,
    ):
        """Show an interactive menu that contains search results.

        :param query:
        :type query: str
        :param source:
        :type source: str
        :param media_type:
        :type media_type: str
        """
        results = tuple(self.search(source, query, media_type, limit=limit))

        def title(res):
            index, item = res
            item_no = index + 1
            if isinstance(item, Album):
                return f"{item_no}. {item.album}"
            elif isinstance(item, Track):
                return f"{item_no}. {item.meta.title}"
            elif isinstance(item, Playlist):
                return f"{item_no}. {item.name}"
            elif isinstance(item, Artist):
                return f"{item_no}. {item.name}"
            else:
                raise NotImplementedError(item.type)

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
            # TODO: change to finditer
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
            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                last_page = int(remaining_tracks // 50) + int(
                    remaining_tracks % 50 != 0
                )

                futures = [
                    executor.submit(requests.get, f"{url}?page={page}")
                    for page in range(1, last_page + 1)
                ]

            for future in concurrent.futures.as_completed(futures):
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
            secho("Enter Qobuz email:", fg="green")
            self.config.file[source]["email"] = input()
            secho(
                "Enter Qobuz password (will not show on screen):",
                fg="green",
            )
            self.config.file[source]["password"] = md5(
                getpass(prompt="").encode("utf-8")
            ).hexdigest()

            self.config.save()
            secho(
                f'Credentials saved to config file at "{self.config._path}"',
                fg="green",
            )
        elif source == "deezer":
            secho(
                "If you're not sure how to find the ARL cookie, see the instructions at ",
                italic=True,
                nl=False,
                dim=True,
            )
            secho(
                "https://github.com/nathom/streamrip/wiki/Finding-your-Deezer-ARL-Cookie",
                underline=True,
                italic=True,
                fg="blue",
            )

            self.config.file["deezer"]["arl"] = input(style("ARL: ", fg="green"))
            self.config.save()
            secho(
                f'Credentials saved to config file at "{self.config._path}"',
                fg="green",
            )
        else:
            raise Exception

    def _config_updating_message(self):
        secho(
            "Updating config file... Some settings may be lost. Please run the "
            "command again.",
            fg="magenta",
        )

    def _config_corrupted_message(self, err: Exception):
        secho(
            "There was a problem with your config file. This happens "
            "sometimes after updates. Run ",
            nl=False,
            fg="red",
        )
        secho("rip config --reset ", fg="yellow", nl=False)
        secho("to reset it. You will need to log in again.", fg="red")
        secho(str(err), fg="red")
