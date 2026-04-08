from qobuz.errors import (
    QobuzError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    InvalidAppError,
    NonStreamableError,
)


def test_qobuz_error_has_status_and_message():
    err = QobuzError(status=401, message="Unauthorized")
    assert err.status == 401
    assert err.message == "Unauthorized"
    assert "401" in str(err)


def test_authentication_error_is_qobuz_error():
    err = AuthenticationError(status=401, message="Bad token")
    assert isinstance(err, QobuzError)
    assert err.status == 401


def test_raise_for_status_maps_codes():
    from qobuz.errors import raise_for_status

    import pytest

    with pytest.raises(AuthenticationError):
        raise_for_status(401, {"status": "error", "code": 401, "message": "Auth required"})

    with pytest.raises(ForbiddenError):
        raise_for_status(403, {"status": "error", "code": 403, "message": "Forbidden"})

    with pytest.raises(NotFoundError):
        raise_for_status(404, {"status": "error", "code": 404, "message": "Not found"})

    with pytest.raises(RateLimitError):
        raise_for_status(429, {"status": "error", "code": 429, "message": "Too many"})

    with pytest.raises(InvalidAppError):
        raise_for_status(400, {"status": "error", "code": 400, "message": "Bad app"})

    # 200 should not raise
    raise_for_status(200, {"status": "success"})
    raise_for_status(201, {"status": "success"})
