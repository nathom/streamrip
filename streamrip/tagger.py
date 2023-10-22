import os
from dataclasses import dataclass
from enum import Enum
from typing import Generator

import aiofiles
import mutagen.id3 as id3
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover

from .metadata import Covers, TrackMetadata

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
    "covr",
    "trkn",
    "disk",
    None,
    None,
    None,
)

MP3_KEYS = (
    id3.TIT2,
    id3.TPE1,
    id3.TALB,
    id3.TPE2,
    id3.TCOM,
    id3.TYER,
    id3.COMM,
    id3.TT1,
    id3.TT1,
    id3.GP1,
    id3.TCON,
    id3.USLT,
    id3.TEN,
    id3.TCOP,
    id3.TCMP,
    None,
    id3.TRCK,
    id3.TPOS,
    None,
    None,
    None,
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
    "cover",
    "tracknumber",
    "discnumber",
    "tracktotal",
    "disctotal",
    "date",
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

    def get_tag_pairs(self, meta) -> Generator:
        if self == Container.FLAC:
            return self._tag_flac(meta)
        elif self == Container.MP3:
            return self._tag_mp3(meta)
        elif self == Container.AAC:
            return self._tag_aac(meta)
        # unreachable
        yield

    def _tag_flac(self, meta):
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

                yield (v, str(tag))

    def _tag_mp3(self, meta):
        for k, v in MP3_KEY.items():
            if k == "tracknumber":
                text = f"{meta.tracknumber}/{meta.tracktotal}"
            elif k == "discnumber":
                text = f"{meta.discnumber}/{meta.disctotal}"
            else:
                text = self._attr_from_meta(meta, k)

            if text is not None and v is not None:
                yield (v.__name__, v(encoding=3, text=text))

    def _tag_aac(self, meta):
        for k, v in MP4_KEY.items():
            if k == "tracknumber":
                text = [(meta.tracknumber, meta.tracktotal)]
            elif k == "discnumber":
                text = [(meta.discnumber, meta.disctotal)]
            else:
                text = self._attr_from_meta(meta, k)

            if v is not None and text is not None:
                yield (v, text)

    def _attr_from_meta(self, meta: TrackMetadata, attr: str) -> str:
        # TODO: verify this works
        in_trackmetadata = {
            "title",
            "album",
            "artist",
            "tracknumber",
            "discnumber",
            "composer",
        }
        if attr in in_trackmetadata:
            return str(getattr(meta, attr))
        else:
            return str(getattr(meta.album, attr))

    def tag_audio(self, audio, tags):
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
    ext = path.split(".")[-1].upper()
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
    container.tag_audio(audio, tags)
    if cover_path is not None:
        await container.embed_cover(audio, cover_path)
    container.save_audio(audio, path)
