import json

from streamrip.metadata import *

with open("tests/qobuz_album_resp.json") as f:
    qobuz_album_resp = json.load(f)

with open("tests/qobuz_track_resp.json") as f:
    qobuz_track_resp = json.load(f)


def test_album_metadata_qobuz():
    m = AlbumMetadata.from_qobuz(qobuz_album_resp)
    info = m.info
    assert info.id == "19512572"
    assert info.quality == 3
    assert info.container == "FLAC"
    assert info.label == "Rhino - Warner Records"
    assert info.explicit == False
    assert info.sampling_rate == 96
    assert info.bit_depth == 24
    assert info.booklets == None

    assert m.album == "Rumours"
    assert m.albumartist == "Fleetwood Mac"
    assert m.year == "1977"
    assert "Pop" in m.genre
    assert "Rock" in m.genre
    assert not m.covers.empty()

    assert m.albumcomposer == "Various Composers"
    assert m.comment == None
    assert m.compilation == None
    assert (
        m.copyright
        == "© 1977 Warner Records Inc. ℗ 1977 Warner Records Inc. Marketed by Rhino Entertainment Company, A Warner Music Group Company."
    )
    assert m.date == "1977-02-04"
    assert m.description == None
    assert m.disctotal == 1
    assert m.encoder == None
    assert m.grouping == None
    assert m.lyrics == None
    assert m.purchase_date == None
    assert m.tracktotal == 11


def test_track_metadata_qobuz():
    a = AlbumMetadata.from_qobuz(qobuz_track_resp["album"])
    t = TrackMetadata.from_qobuz(a, qobuz_track_resp)
    info = t.info
    assert info.id == "216020864"
    assert info.quality == 3
    assert info.bit_depth == 24
    assert info.sampling_rate == 96
    assert info.work is None

    assert t.title == "Water Tower"
    assert t.album == a
    assert t.artist == "The Mountain Goats"
    assert t.tracknumber == 9
    assert t.discnumber == 1
    assert t.composer == "John Darnielle"
