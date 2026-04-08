from conftest import SAMPLE_ALBUM, SAMPLE_TRACK, SAMPLE_PLAYLIST, SAMPLE_GENRE, SAMPLE_FAVORITE_IDS
from qobuz.types import Album, Track, Playlist, Genre, FavoriteIds, ImageSet, ArtistSummary, Label


class TestAlbumParsing:
    def test_from_dict_parses_capture_data(self):
        album = Album.from_dict(SAMPLE_ALBUM)
        assert album.id == "p0d55tt7gv3lc"
        assert album.title == "Virgin Lake"
        assert album.maximum_bit_depth == 24
        assert album.maximum_sampling_rate == 44.1
        assert album.tracks_count == 14
        assert album.streamable is True
        assert album.hires is True
        assert album.image.large.endswith("600.jpg")
        assert album.artist.name == "Philine Sonny"
        assert album.label.name == "Nettwerk Music Group"
        assert album.genre.id == 113

    def test_version_can_be_none(self):
        album = Album.from_dict(SAMPLE_ALBUM)
        assert album.version is None


class TestTrackParsing:
    def test_from_dict_parses_capture_data(self):
        track = Track.from_dict(SAMPLE_TRACK)
        assert track.id == 33967376
        assert track.title == "Blitzkrieg Bop"
        assert track.duration == 133
        assert track.track_number == 1
        assert track.disc_number == 1
        assert track.performer.name == "Ramones"
        assert track.audio_info.maximum_bit_depth == 24


class TestPlaylistParsing:
    def test_from_dict_parses_capture_data(self):
        pl = Playlist.from_dict(SAMPLE_PLAYLIST)
        assert pl.id == 61997651
        assert pl.name == "New Private Playlist"
        assert pl.is_public is False
        assert pl.owner.name == "arthursoares"
        assert pl.tracks_count == 0


class TestGenreParsing:
    def test_from_dict_parses_capture_data(self):
        genre = Genre.from_dict(SAMPLE_GENRE)
        assert genre.id == 112
        assert genre.name == "Pop/Rock"
        assert genre.slug == "pop-rock"
        assert genre.path == [112]


class TestFavoriteIds:
    def test_from_dict_parses_capture_data(self):
        fav = FavoriteIds.from_dict(SAMPLE_FAVORITE_IDS)
        assert len(fav.albums) == 2
        assert len(fav.tracks) == 2
        assert len(fav.artists) == 2
        assert "xetru34w7hkdv" in fav.albums
