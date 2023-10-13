from dataclasses import dataclass
from enum import Enum
from typing import Generator

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover

from .metadata import TrackMetadata


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
            tag = getattr(meta, k)
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
                text = getattr(self, k)

            if text is not None and v is not None:
                yield (v.__name__, v(encoding=3, text=text))

    def _tag_aac(self, meta):
        for k, v in MP4_KEY.items():
            if k == "tracknumber":
                text = [(meta.tracknumber, meta.tracktotal)]
            elif k == "discnumber":
                text = [(meta.discnumber, meta.disctotal)]
            else:
                text = getattr(self, k)

            if v is not None and text is not None:
                yield (v, text)


@dataclass(slots=True)
class Tagger:
    meta: TrackMetadata

    def tag(self, path: str, embed_cover: bool, covers: Cover):
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
        tags = container.get_tag_pairs(self.meta)
        for k, v in tags:
            audio[k] = v

        c = 
