import pytest

from streamrip.metadata import Covers


@pytest.fixture()
def covers_all():
    c = Covers()
    c.set_cover("original", "ourl", None)
    c.set_cover("large", "lurl", None)
    c.set_cover("small", "surl", None)
    c.set_cover("thumbnail", "turl", None)

    return c


@pytest.fixture()
def covers_none():
    return Covers()


@pytest.fixture()
def covers_one():
    c = Covers()
    c.set_cover("small", "surl", None)
    return c


@pytest.fixture()
def covers_some():
    c = Covers()
    c.set_cover("large", "lurl", None)
    c.set_cover("small", "surl", None)
    return c


def test_covers_all(covers_all):
    assert covers_all._covers == [
        ("original", "ourl", None),
        ("large", "lurl", None),
        ("small", "surl", None),
        ("thumbnail", "turl", None),
    ]
    assert covers_all.largest() == ("original", "ourl", None)
    assert covers_all.get_size("original") == ("original", "ourl", None)
    assert covers_all.get_size("thumbnail") == ("thumbnail", "turl", None)


def test_covers_none(covers_none):
    assert covers_none.empty()
    with pytest.raises(Exception):
        covers_none.largest()
    with pytest.raises(Exception):
        covers_none.get_size("original")


def test_covers_one(covers_one):
    assert not covers_one.empty()
    assert covers_one.largest() == ("small", "surl", None)
    assert covers_one.get_size("original") == ("small", "surl", None)
    with pytest.raises(Exception):
        covers_one.get_size("thumbnail")


def test_covers_some(covers_some):
    assert not covers_some.empty()
    assert covers_some.largest() == ("large", "lurl", None)
    assert covers_some.get_size("original") == ("large", "lurl", None)
    assert covers_some.get_size("small") == ("small", "surl", None)
    with pytest.raises(Exception):
        covers_some.get_size("thumbnail")
