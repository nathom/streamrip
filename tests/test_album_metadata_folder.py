
from streamrip.metadata.album import AlbumInfo, AlbumMetadata
from streamrip.metadata.covers import Covers


def _make_album(
    quality: int = 4,
    container: str = "FLAC",
    bit_depth: int | None = 24,
    sampling_rate: int | None = 192000,
    albumartist: str = "Artist",
    album: str = "Album",
    year: str = "2024",
) -> AlbumMetadata:
    info = AlbumInfo(
        id="test-id",
        quality=quality,
        container=container,
        bit_depth=bit_depth,
        sampling_rate=sampling_rate,
    )
    covers = Covers()
    return AlbumMetadata(
        info=info,
        album=album,
        albumartist=albumartist,
        year=year,
        genre=[],
        covers=covers,
        tracktotal=10,
    )


FORMATTER = "{albumartist} - {year} - {title} [{container}]"


class TestFormatFolderPath:
    def test_no_effective_quality_uses_album_info(self):
        meta = _make_album(quality=4, container="FLAC")
        result = meta.format_folder_path(FORMATTER)
        assert "FLAC" in result
        assert "Artist" in result
        assert "2024" in result

    def test_effective_quality_equal_to_album_quality_no_override(self):
        meta = _make_album(quality=2, container="FLAC", bit_depth=16, sampling_rate=44100)
        result = meta.format_folder_path(FORMATTER, effective_quality=2)
        assert "FLAC" in result

    def test_effective_quality_lower_overrides_container(self):
        # Album is FLAC 24-bit but user configured MP3 (quality 1)
        meta = _make_album(quality=4, container="FLAC", bit_depth=24, sampling_rate=192000)
        result = meta.format_folder_path(FORMATTER, effective_quality=1)
        assert "MP3" in result
        assert "FLAC" not in result

    def test_effective_quality_2_gives_flac_16(self):
        meta = _make_album(quality=4, container="FLAC", bit_depth=24, sampling_rate=192000)
        full_formatter = "{albumartist} - {year} - {title} [{container}] [{bit_depth}B-{sampling_rate}kHz]"
        result = meta.format_folder_path(full_formatter, effective_quality=2)
        assert "FLAC" in result
        assert "16" in result
        assert "44100" in result

    def test_effective_quality_3_gives_flac_24_96(self):
        meta = _make_album(quality=4, container="FLAC", bit_depth=24, sampling_rate=192000)
        full_formatter = "{albumartist} - {year} - {title} [{container}] [{bit_depth}B-{sampling_rate}kHz]"
        result = meta.format_folder_path(full_formatter, effective_quality=3)
        assert "FLAC" in result
        assert "24" in result
        assert "96" in result

    def test_slash_in_albumartist_sanitized(self):
        meta = _make_album(albumartist="AC/DC")
        result = meta.format_folder_path(FORMATTER)
        # slash must not survive into folder template output
        assert "AC/DC" not in result
        assert "AC-DC" in result

    def test_slash_in_album_title_sanitized(self):
        meta = _make_album(album="Yes/No")
        result = meta.format_folder_path(FORMATTER)
        assert "Yes/No" not in result
        assert "Yes-No" in result

    def test_albumcomposer_none_fallback(self):
        meta = _make_album()
        formatter = "{albumartist} - {albumcomposer}"
        result = meta.format_folder_path(formatter)
        assert "Unknown" in result

    def test_mp3_container_no_unknown_tokens(self):
        # Quality 0/1 → MP3, bit_depth=None, sampling_rate=None
        meta = _make_album(quality=2, container="FLAC", bit_depth=16, sampling_rate=44100)
        result = meta.format_folder_path(FORMATTER, effective_quality=1)
        assert "Unknown" not in result
        assert "MP3" in result
