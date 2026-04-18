from streamrip.rip.cli import is_update_available


def test_update_available_when_latest_is_higher():
    assert is_update_available("2.2.0", "2.2.1")


def test_update_not_available_when_versions_equal():
    assert not is_update_available("2.2.0", "2.2.0")


def test_update_not_available_when_current_is_higher():
    assert not is_update_available("2.3.0", "2.2.1")


def test_update_not_available_for_newer_dev_build_than_stable():
    assert not is_update_available("2.3.0.dev1", "2.2.0")


def test_update_available_from_rc_to_stable():
    assert is_update_available("2.2.0rc1", "2.2.0")
