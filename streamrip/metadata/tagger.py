import logging
import os
from enum import Enum

import aiofiles
from mutagen import id3
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC,  # type: ignore
    ID3,
    ID3NoHeaderError,
)
from mutagen.mp4 import MP4, MP4Cover

from .track import TrackMetadata

logger = logging.getLogger("streamrip")

FLAC_MAX_BLOCKSIZE = 16777215  # 16.7 MB

MP4_KEYS = (
    "\xa9nam",
    "\xa9ART",
    "\xa9alb",
    r"aART",
    "\xa9day",
    "\xa9day",
    "\xa9cmt",
    "desc",
    "purd",
    "\xa9grp",
    "\xa9gen",
    "\xa9lyr",
    "\xa9too",
    "cprt",
    "cpil",
    "trkn",
    "disk",
    None,
    None,
    None,
    "----:com.apple.iTunes:ISRC",
)

MP3_KEYS = (
    id3.TIT2,  # type: ignore
    id3.TPE1,  # type: ignore
    id3.TALB,  # type: ignore
    id3.TPE2,  # type: ignore
    id3.TCOM,  # type: ignore
    id3.TYER,  # type: ignore
    id3.COMM,  # type: ignore
    id3.TT1,  # type: ignore
    id3.TT1,  # type: ignore
    id3.GP1,  # type: ignore
    id3.TCON,  # type: ignore
    id3.USLT,  # type: ignore
    id3.TEN,  # type: ignore
    id3.TCOP,  # type: ignore
    id3.TCMP,  # type: ignore
    id3.TRCK,  # type: ignore
    id3.TPOS,  # type: ignore
    None,
    None,
    None,
    id3.TSRC,
)

METADATA_TYPES = (
    "title",
    "artist",
    "album",
    "albumartist",
    "composer",
    "year",
    "comment",
    "description",
    "purchase_date",
    "grouping",
    "genre",
    "lyrics",
    "encoder",
    "copyright",
    "compilation",
    "tracknumber",
    "discnumber",
    "tracktotal",
    "disctotal",
    "date",
    "isrc",
)


FLAC_KEY = {v: v.upper() for v in METADATA_TYPES}
MP4_KEY = dict(zip(METADATA_TYPES, MP4_KEYS))
MP3_KEY = dict(zip(METADATA_TYPES, MP3_KEYS))


class Container(Enum):
    FLAC = 1
    AAC = 2
    MP3 = 3

    def get_mutagen_class(self, path: str):
        if self == Container.FLAC:
            return FLAC(path)
        elif self == Container.AAC:
            return MP4(path)
        elif self == Container.MP3:
            try:
                return ID3(path)
            except ID3NoHeaderError:
                return ID3()
        # unreachable
        return {}

    def get_tag_pairs(self, meta) -> list[tuple]:
        if self == Container.FLAC:
            return self._tag_flac(meta)
        elif self == Container.MP3:
            return self._tag_mp3(meta)
        elif self == Container.AAC:
            return self._tag_mp4(meta)
        # unreachable
        return []

    def _tag_flac(self, meta: TrackMetadata) -> list[tuple]:
        out = []
        for k, v in FLAC_KEY.items():
            tag = self._attr_from_meta(meta, k)
            if tag:
                if k in {
                    "tracknumber",
                    "discnumber",
                    "tracktotal",
                    "disctotal",
                }:
                    tag = f"{int(tag):02}"

                out.append((v, str(tag)))
        return out

    def _tag_mp3(self, meta: TrackMetadata):
        out = []
        for k, v in MP3_KEY.items():
            if k == "tracknumber":
                text = f"{meta.tracknumber}/{meta.album.tracktotal}"
            elif k == "discnumber":
                text = f"{meta.discnumber}/{meta.album.disctotal}"
            else:
                text = self._attr_from_meta(meta, k)

            if text is not None and v is not None:
                out.append((v.__name__, v(encoding=3, text=text)))
        return out

    def _tag_mp4(self, meta: TrackMetadata):
        out = []
        for k, v in MP4_KEY.items():
            if k == "tracknumber":
                text = [(meta.tracknumber, meta.album.tracktotal)]
            elif k == "discnumber":
                text = [(meta.discnumber, meta.album.disctotal)]
            elif k == "isrc" and meta.isrc is not None:
                # because ISRC is an mp4 freeform value (not supported natively)
                # we have to pass in the actual bytes to mutagen
                # See mutagen.MP4Tags.__render_freeform
                text = meta.isrc.encode("utf-8")
            else:
                text = self._attr_from_meta(meta, k)

            if v is not None and text is not None:
                out.append((v, text))
        return out

    def _attr_from_meta(self, meta: TrackMetadata, attr: str) -> str | None:
        # TODO: verify this works
        in_trackmetadata = {
            "title",
            "album",
            "artist",
            "tracknumber",
            "discnumber",
            "composer",
            "isrc",
            "lyrics",
        }
        if attr in in_trackmetadata:
            if attr == "album":
                return meta.album.album
            val = getattr(meta, attr)
            if val is None:
                return None
            return str(val)
        else:
            if attr == "genre":
                return meta.album.get_genres()
            elif attr == "copyright":
                return meta.album.get_copyright()
            val = getattr(meta.album, attr)
            if val is None:
                return None
            return str(val)

    def tag_audio(self, audio, tags: list[tuple]):
        for k, v in tags:
            audio[k] = v

    async def embed_cover(self, audio, cover_path):
        if self == Container.FLAC:
            size = os.path.getsize(cover_path)
            if size > FLAC_MAX_BLOCKSIZE:
                raise Exception("Cover art too big for FLAC")
            cover = Picture()
            cover.type = 3
            cover.mime = "image/jpeg"
            async with aiofiles.open(cover_path, "rb") as img:
                cover.data = await img.read()
            audio.add_picture(cover)
        elif self == Container.MP3:
            cover = APIC()
            cover.type = 3
            cover.mime = "image/jpeg"
            async with aiofiles.open(cover_path, "rb") as img:
                cover.data = await img.read()
            audio.add(cover)
        elif self == Container.AAC:
            async with aiofiles.open(cover_path, "rb") as img:
                cover = MP4Cover(await img.read(), imageformat=MP4Cover.FORMAT_JPEG)
            audio["covr"] = [cover]

    def save_audio(self, audio, path):
        if self == Container.FLAC:
            audio.save()
        elif self == Container.AAC:
            audio.save()
        elif self == Container.MP3:
            audio.save(path, "v2_version=3")


async def tag_file(path: str, meta: TrackMetadata, cover_path: str | None):
    ext = path.split(".")[-1].lower()
    if ext == "flac":
        container = Container.FLAC
    elif ext == "m4a":
        container = Container.AAC
    elif ext == "mp3":
        container = Container.MP3
    else:
        raise Exception(f"Invalid extension {ext}")

    audio = container.get_mutagen_class(path)
    tags = container.get_tag_pairs(meta)
    logger.debug("Tagging with %s", tags)
    container.tag_audio(audio, tags)
    if cover_path is not None:
        await container.embed_cover(audio, cover_path)
    container.save_audio(audio, path)
