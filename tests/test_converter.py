from util import arun

from streamrip import converter
from streamrip.config import Config
from streamrip.media.track import Track


class DummyConverter:
    lossless = False
    instances = []

    @classmethod
    def get_quality_arg(cls, rate):
        return f"-b:a {rate}k"

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.final_fn = "/tmp/output.opus"
        self.instances.append(self)

    async def convert(self):
        pass


class DummyLosslessConverter(DummyConverter):
    lossless = True
    instances = []

    @classmethod
    def get_quality_arg(cls, rate):
        raise AssertionError("lossless converters should not use lossy_bitrate")


def test_lossy_bitrate_config_is_passed_to_converter(monkeypatch):
    monkeypatch.setattr("streamrip.media.track.converter.get", lambda _: DummyConverter)
    DummyConverter.instances = []

    config = Config.defaults()
    config.session.conversion.codec = "OPUS"
    config.session.conversion.lossy_bitrate = 160
    track = Track(None, None, config, "", None, None, download_path="/tmp/source.flac")

    arun(track._convert())

    engine = DummyConverter.instances[0]
    assert engine.kwargs["ffmpeg_arg"] == "-b:a 160k"
    assert track.download_path == "/tmp/output.opus"


def test_lossy_bitrate_config_is_not_passed_to_lossless_converter(monkeypatch):
    monkeypatch.setattr(
        "streamrip.media.track.converter.get", lambda _: DummyLosslessConverter
    )
    DummyLosslessConverter.instances = []

    config = Config.defaults()
    config.session.conversion.codec = "ALAC"
    config.session.conversion.lossy_bitrate = 160
    track = Track(None, None, config, "", None, None, download_path="/tmp/source.flac")

    arun(track._convert())

    engine = DummyLosslessConverter.instances[0]
    assert engine.kwargs["ffmpeg_arg"] is None


def test_lossy_codec_quality_args_use_configured_bitrate():
    assert converter.OPUS.get_quality_arg(160) == "-b:a 160k"
    assert converter.AAC.get_quality_arg(192) == "-b:a 192k"
    assert converter.LAME.get_quality_arg(160) == "-b:a 160k"
    assert converter.Vorbis.get_quality_arg(160) == "-qscale:a 5"
