"""Wrapper classes over FFMPEG."""

import asyncio
import logging
import os
import shutil
from tempfile import gettempdir
from typing import Final, Optional

from .exceptions import ConversionError

logger = logging.getLogger("streamrip")

SAMPLING_RATES = {44100, 48000, 88200, 96000, 176400, 192000}


class Converter:
    """Base class for audio codecs."""

    codec_name: str
    codec_lib: str
    container: str
    lossless: bool = False
    default_ffmpeg_arg: str = ""

    def __init__(
        self,
        filename: str,
        ffmpeg_arg: Optional[str] = None,
        sampling_rate: Optional[int] = None,
        bit_depth: Optional[int] = None,
        copy_art: bool = True,
        remove_source: bool = False,
        show_progress: bool = False,
    ):
        """Create a Converter object.

        :param filename:
        :type filename: str
        :param ffmpeg_arg: The codec ffmpeg argument (defaults to an "optimal value")
        :type ffmpeg_arg: Optional[str]
        :param sampling_rate: This value is ignored if a lossy codec is detected
        :type sampling_rate: Optional[int]
        :param bit_depth: This value is ignored if a lossy codec is detected
        :type bit_depth: Optional[int]
        :param copy_art: Embed the cover art (if found) into the encoded file
        :type copy_art: bool
        :param remove_source: Remove the source file after conversion.
        :type remove_source: bool
        """
        if shutil.which("ffmpeg") is None:
            raise Exception(
                "Could not find FFMPEG executable. Install it to convert audio files.",
            )

        self.filename = filename
        self.final_fn = f"{os.path.splitext(filename)[0]}.{self.container}"
        self.tempfile = os.path.join(gettempdir(), os.path.basename(self.final_fn))
        self.remove_source = remove_source
        self.sampling_rate = sampling_rate
        self.bit_depth = bit_depth
        self.copy_art = copy_art
        self.show_progress = show_progress

        if ffmpeg_arg is None:
            logger.debug("No arguments provided. Codec defaults will be used")
            self.ffmpeg_arg = self.default_ffmpeg_arg
        else:
            self.ffmpeg_arg = ffmpeg_arg
            self._is_command_valid()

        logger.debug("FFmpeg codec extra argument: %s", self.ffmpeg_arg)

    async def convert(self, custom_fn: Optional[str] = None):
        """Convert the file.

        :param custom_fn: Custom output filename (defaults to the original
        name with a replaced container)
        :type custom_fn: Optional[str]
        """
        if custom_fn:
            self.final_fn = custom_fn

        self.command = self._gen_command()
        logger.debug("Generated conversion command: %s", self.command)

        process = await asyncio.create_subprocess_exec(
            *self.command,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await process.communicate()
        if process.returncode == 0 and os.path.isfile(self.tempfile):
            if self.remove_source:
                os.remove(self.filename)
                logger.debug("Source removed: %s", self.filename)

            shutil.move(self.tempfile, self.final_fn)
            logger.debug("Moved: %s -> %s", self.tempfile, self.final_fn)
        else:
            raise ConversionError(f"FFmpeg output:\n{out, err}")

    def _gen_command(self):
        command = [
            "ffmpeg",
            "-i",
            self.filename,
        ]

        if logger.getEffectiveLevel() != logging.DEBUG:
            command.extend(("-loglevel", "panic"))

        command.extend(("-c:a", self.codec_lib))

        if self.show_progress:
            command.append("-stats")

        if self.copy_art:
            command.extend(["-c:v", "copy"])

        if self.ffmpeg_arg:
            command.extend(self.ffmpeg_arg.split())

        if self.lossless:
            aformat = []

            if isinstance(self.sampling_rate, int):
                sample_rates = "|".join(
                    str(rate) for rate in SAMPLING_RATES if rate <= self.sampling_rate
                )
                aformat.append(f"sample_rates={sample_rates}")
            elif self.sampling_rate is not None:
                raise TypeError(
                    f"Sampling rate must be int, not {type(self.sampling_rate)}"
                )

            if isinstance(self.bit_depth, int):
                bit_depths = ["s16p", "s16"]

                if self.bit_depth in (24, 32):
                    bit_depths.extend(["s32p", "s32"])
                elif self.bit_depth != 16:
                    raise ValueError("Bit depth must be 16, 24, or 32")

                sample_fmts = "|".join(bit_depths)
                aformat.append(f"sample_fmts={sample_fmts}")
            elif self.bit_depth is not None:
                raise TypeError(f"Bit depth must be int, not {type(self.bit_depth)}")

            if aformat:
                aformat_params = ":".join(aformat)
                command.extend(["-af", f"aformat={aformat_params}"])

        # automatically overwrite
        command.extend(["-y", self.tempfile])

        logger.debug(command)

        return command

    def _is_command_valid(self):
        # TODO: add error handling for lossy codecs
        if self.ffmpeg_arg is not None and self.lossless:
            logger.debug(
                "Lossless codecs don't support extra arguments; "
                "the extra argument will be ignored",
            )
            self.ffmpeg_arg = self.default_ffmpeg_arg
            return


class FLAC(Converter):
    """Class for FLAC converter."""

    codec_name = "flac"
    codec_lib = "flac"
    container = "flac"
    lossless = True


class LAME(Converter):
    """Class for libmp3lame converter.

    Default ffmpeg_arg: `-q:a 0`.

    See available options:
    https://trac.ffmpeg.org/wiki/Encode/MP3
    """

    _bitrate_map: Final[dict[int, str]] = {
        320: "-b:a 320k",
        245: "-q:a 0",
        225: "-q:a 1",
        190: "-q:a 2",
        175: "-q:a 3",
        165: "-q:a 4",
        130: "-q:a 5",
        115: "-q:a 6",
        100: "-q:a 7",
        85: "-q:a 8",
        65: "-q:a 9",
    }

    codec_name = "lame"
    codec_lib = "libmp3lame"
    container = "mp3"
    default_ffmpeg_arg = "-q:a 0"  # V0

    def get_quality_arg(self, rate):
        return self._bitrate_map[rate]


class ALAC(Converter):
    """Class for ALAC converter."""

    codec_name = "alac"
    codec_lib = "alac"
    container = "m4a"
    lossless = True


class Vorbis(Converter):
    """Class for libvorbis converter.

    Default ffmpeg_arg: `-q:a 6`.

    See available options:
    https://trac.ffmpeg.org/wiki/TheoraVorbisEncodingGuide
    """

    codec_name = "vorbis"
    codec_lib = "libvorbis"
    container = "ogg"
    default_ffmpeg_arg = "-q:a 6"  # 160, aka the "high" quality profile from Spotify

    def get_quality_arg(self, rate: int) -> str:
        arg = "qscale:a %d"
        if rate <= 128:
            return arg % (rate / 16 - 4)
        if rate <= 256:
            return arg % (rate / 32)

        return arg % (rate / 64 + 4)


class OPUS(Converter):
    """Class for libopus.

    Default ffmpeg_arg: `-b:a 128 -vbr on`.

    See more:
    http://ffmpeg.org/ffmpeg-codecs.html#libopus-1
    """

    codec_name = "opus"
    codec_lib = "libopus"
    container = "opus"
    default_ffmpeg_arg = "-b:a 128k"  # Transparent

    def get_quality_arg(self, _: int) -> str:
        return ""


class AAC(Converter):
    """Class for libfdk_aac converter.

    Default ffmpeg_arg: `-b:a 256k`.

    See available options:
    https://trac.ffmpeg.org/wiki/Encode/AAC
    """

    codec_name = "aac"
    codec_lib = "libfdk_aac"
    container = "m4a"
    default_ffmpeg_arg = "-b:a 256k"

    def get_quality_arg(self, _: int) -> str:
        return ""


def get(codec: str) -> type[Converter]:
    converter_classes = {
        "FLAC": FLAC,
        "ALAC": ALAC,
        "MP3": LAME,
        "OPUS": OPUS,
        "OGG": Vorbis,
        "VORBIS": Vorbis,
        "AAC": AAC,
        "M4A": AAC,
    }
    return converter_classes[codec.upper()]
