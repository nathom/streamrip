import asyncio
import dataclasses
import logging
import re
import sys
from dataclasses import dataclass
from typing import ClassVar

from ..client import Client
from ..config import Config, QobuzDiscographyFilterConfig
from ..console import console
from ..utils import menu
from ..db import Database
from ..exceptions import NonStreamableError
from ..metadata.artist import ArtistMetadata
from ..metadata.search_results import AlbumSummary
from .album import Album, PendingAlbum
from .media import Media, Pending

logger = logging.getLogger("streamrip")

# Resolve only N albums at a time to avoid
# initial latency of resolving ALL albums and tracks
# before any downloads
RESOLVE_CHUNK_SIZE = 10


@dataclass(slots=True)
class Artist(Media):
    """Represents a list of albums. Used by Artist and Label classes."""

    name: str
    albums: list[PendingAlbum]
    client: Client
    config: Config
    summaries: list[AlbumSummary] = dataclasses.field(default_factory=list)

    # Set to False by `rip url --no-confirm` for unattended runs.
    confirm_selection: ClassVar[bool] = True
    # "type" groups albums, then EPs, then singles, each oldest first.
    # "date" is a single chronological run. Set by `rip url --sort`.
    sort_by: ClassVar[str] = "type"

    async def preprocess(self):
        pass

    async def download(self):
        if not self._select_albums():
            return
        filter_conf = self.config.session.qobuz_filters
        if filter_conf.repeats:
            console.log(
                "Resolving [purple]ALL[/purple] artist albums to detect repeats. This may take a while."
            )
            await self._resolve_then_download(filter_conf)
        else:
            await self._download_async(filter_conf)

    def _select_albums(self) -> bool:
        """Let the user pick from the discography before anything downloads.

        Artist search is unreliable on both Qobuz and Tidal, so an artist url
        can easily be the wrong person entirely, and even the right one brings
        a lot nobody asked for. Uses the same menu as `rip search`, so it looks
        and behaves the same way. Returns False if nothing was chosen.
        """
        if not (
            self.confirm_selection
            and self.summaries
            and len(self.albums) > 1
            and sys.stdin.isatty()
        ):
            return True

        # Sources return the discography in their own order, which is not
        # useful for picking through 80-odd releases.
        sort_by = self.sort_by
        if sort_by not in ("type", "date"):
            # A missing key is covered by the dataclass default; this is a
            # value that is present but not one we understand. Say so rather
            # than silently picking an order the user did not ask for.
            logger.warning(
                "Unknown cli.artist_album_sort %r, using 'type'. "
                "Valid values are 'type' and 'date'.",
                sort_by,
            )
            sort_by = "type"

        # Unknown type ranks with albums, so a source that does not report one
        # (Qobuz) just sorts chronologically rather than pretending.
        rank = {"album": 0, "": 0, "ep": 1, "single": 2}

        def sort_key(i: int):
            s = self.summaries[i]
            date = s.date_released or ""
            # Dates arrive as ISO strings, which sort correctly as text, but
            # can also be a bare year or the literal "Unknown". Anything
            # unparseable goes last rather than landing in the middle.
            date_key = date if date[:4].isdigit() else "9999"
            # Title and quality break ties, so two editions of the same
            # release always sit together. The id is a last resort that never
            # ties, because sources do list the same release twice with every
            # visible field identical -- without it those two could swap
            # places between runs.
            tail = (date_key, s.name.lower(), s.quality, str(s.id))
            return (rank.get(s.release_type, 0), *tail) if sort_by == "type" else tail

        order = sorted(range(len(self.summaries)), key=sort_key)

        # The artist is the same on every row here, so show what actually
        # distinguishes releases: year, size, quality and kind.
        entries = []
        for n, i in enumerate(order, 1):
            s = self.summaries[i]
            year = (s.date_released or "")[:4] or "----"
            quality = f"  {s.quality}" if s.quality else ""
            kind = f"  ({s.release_type})" if s.release_type in ("ep", "single") else ""
            entries.append(
                f"{n}. {year}  {s.name[:48]}{kind}  [{s.num_tracks} trk]{quality}"
            )

        chosen = menu.multi_select(
            entries,
            title=(
                f"{self.name} - {len(self.summaries)} releases\n"
                "SPACE - select, ENTER - download, ESC - exit"
            ),
            previews=[self.summaries[i].preview() for i in order],
        )

        if not chosen:
            menu.announce_nothing_chosen()
            return False

        keep = {self.summaries[order[i]].id for i in chosen}
        self.albums = [a for a in self.albums if str(a.id) in keep]
        console.print(f"[green]Downloading {len(self.albums)} release(s).\n")
        return True

    async def postprocess(self):
        pass

    async def _resolve_then_download(self, filters: QobuzDiscographyFilterConfig):
        """Resolve all artist albums, then download.

        This is used if the repeat filter is turned on, since we need the titles
        of all albums to remove repeated items.
        """
        resolved_or_none: list[Album | None] = await asyncio.gather(
            *[album.resolve() for album in self.albums]
        )
        resolved = [a for a in resolved_or_none if a is not None]
        filtered_albums = self._apply_filters(resolved, filters)
        batches = self.batch([a.rip() for a in filtered_albums], RESOLVE_CHUNK_SIZE)
        for batch in batches:
            await asyncio.gather(*batch)

    async def _download_async(self, filters: QobuzDiscographyFilterConfig):
        async def _rip(item: PendingAlbum):
            album = await item.resolve()
            # Skip if album doesn't pass the filter
            if (
                album is None
                or (filters.extras and not self._extras(album))
                or (filters.features and not self._features(album))
                or (filters.non_studio_albums and not self._non_studio_albums(album))
                or (filters.non_remaster and not self._non_remaster(album))
            ):
                return
            await album.rip()

        batches = self.batch(
            [_rip(album) for album in self.albums],
            RESOLVE_CHUNK_SIZE,
        )
        for batch in batches:
            await asyncio.gather(*batch)

    def _apply_filters(
        self, albums: list[Album], filt: QobuzDiscographyFilterConfig
    ) -> list[Album]:
        _albums = albums
        if filt.repeats:
            _albums = self._filter_repeats(_albums)
        if filt.extras:
            _albums = filter(self._extras, _albums)
        if filt.features:
            _albums = filter(self._features, _albums)
        if filt.non_studio_albums:
            _albums = filter(self._non_studio_albums, _albums)
        if filt.non_remaster:
            _albums = filter(self._non_remaster, _albums)
        return list(_albums)

    # Will not fail on any nonempty string
    _essence_re = re.compile(r"([^\(\[]+)(?:\s*[\(\[][^\)][\)\]])*")

    @classmethod
    def _filter_repeats(cls, albums: list[Album]) -> list[Album]:
        """When there are different versions of an album on the artist,
        choose the one with the best quality.

        It determines that two albums are identical if they have the same title
        ignoring contents in brackets or parentheses.
        """
        groups: dict[str, list[Album]] = {}
        for a in albums:
            match = cls._essence_re.match(a.meta.album)
            assert match is not None
            title = match.group(1).strip().lower()
            items = groups.get(title, [])
            items.append(a)
            groups[title] = items

        unique_albums: list[Album] = []
        for group in groups.values():
            # Move explicit versions to the beginning
            group = sorted(
                group,
                key=lambda album: album.meta.info.explicit,
                reverse=True,
            )
            group = sorted(
                group,
                key=lambda album: album.meta.info.sampling_rate or 0,
                reverse=True,
            )
            group = sorted(
                group,
                key=lambda album: album.meta.info.bit_depth or 0,
                reverse=True,
            )
            # group guaranteed to be nonempty
            unique_albums.append(group[0])

        return unique_albums

    _extra_re = re.compile(
        r"(?i)(anniversary|deluxe|live|collector|demo|expanded|remix)"
    )

    # ----- Filter predicates -----
    def _non_studio_albums(self, a: Album) -> bool:
        """Filter out non studio albums."""
        return a.meta.albumartist != "Various Artists" and self._extras(a)

    def _features(self, a: Album) -> bool:
        """Filter out features."""
        return a.meta.albumartist == self.name

    def _extras(self, a: Album) -> bool:
        """Filter out extras.

        See `_extra_re` for criteria.
        """
        return self._extra_re.search(a.meta.album) is None

    _remaster_re = re.compile(r"(?i)(re)?master(ed)?")

    def _non_remaster(self, a: Album) -> bool:
        """Filter out albums that are not remasters."""
        return self._remaster_re.search(a.meta.album) is not None

    def _non_albums(self, a: Album) -> bool:
        """Filter out singles."""
        return len(a.tracks) > 1

    @staticmethod
    def batch(iterable, n=1):
        total = len(iterable)
        for ndx in range(0, total, n):
            yield iterable[ndx : min(ndx + n, total)]


@dataclass(slots=True)
class PendingArtist(Pending):
    id: str
    client: Client
    config: Config
    db: Database

    async def resolve(self) -> Artist | None:
        try:
            resp = await self.client.get_metadata(self.id, "artist")
        except NonStreamableError as e:
            logger.error(
                f"Artist {self.id} not available to stream on {self.client.source} ({e})",
            )
            return None

        try:
            meta = ArtistMetadata.from_resp(resp, self.client.source)
        except Exception as e:
            logger.error(
                f"Error building artist metadata: {e}",
            )
            return None

        albums = [
            PendingAlbum(album_id, self.client, self.config, self.db)
            for album_id in meta.album_ids()
        ]
        return Artist(meta.name, albums, self.client, self.config, meta.albums)
