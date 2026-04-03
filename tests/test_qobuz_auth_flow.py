import pytest
from util import arun

from streamrip.client.qobuz import QobuzClient
from streamrip.config import Config
from streamrip.exceptions import AuthenticationError
from streamrip.rip.main import Main
from streamrip.rip.prompter import QobuzPrompter
from streamrip.rip.qobuz_token_capture import (
    QobuzTokenCaptureError,
    capture_qobuz_auth_token,
)


class _FakeSession:
    def __init__(self):
        self.headers = {}

    async def close(self):
        return None


def test_qobuz_login_uses_user_auth_token_params(monkeypatch):
    config = Config.defaults()
    c = config.session.qobuz
    c.use_auth_token = True
    c.email_or_userid = "123456"
    c.password_or_token = "jwt-token"
    c.app_id = "123456789"
    c.secrets = ["secret"]

    client = QobuzClient(config)
    captured = {}

    async def fake_get_session(*, verify_ssl):
        return _FakeSession()

    async def fake_api_request(epoint, params):
        captured["epoint"] = epoint
        captured["params"] = params
        return (
            200,
            {
                "user": {"credential": {"parameters": {"can_stream": True}}},
                "user_auth_token": "returned-token",
            },
        )

    async def fake_get_valid_secret(_):
        return "working-secret"

    monkeypatch.setattr(client, "get_session", fake_get_session)
    monkeypatch.setattr(client, "_api_request", fake_api_request)
    monkeypatch.setattr(client, "_get_valid_secret", fake_get_valid_secret)

    arun(client.login())

    assert captured["epoint"] == "user/login"
    assert captured["params"]["user_id"] == "123456"
    assert captured["params"]["user_auth_token"] == "jwt-token"
    assert "email" not in captured["params"]
    assert "password" not in captured["params"]
    assert client.session.headers["X-User-Auth-Token"] == "returned-token"


def test_qobuz_login_401_message_is_token_specific_and_redacted(monkeypatch):
    config = Config.defaults()
    c = config.session.qobuz
    c.use_auth_token = True
    c.email_or_userid = "123456"
    c.password_or_token = "sensitive-token"
    c.app_id = "123456789"
    c.secrets = ["secret"]

    client = QobuzClient(config)

    async def fake_get_session(*, verify_ssl):
        return _FakeSession()

    async def fake_api_request(_epoint, _params):
        return 401, {}

    monkeypatch.setattr(client, "get_session", fake_get_session)
    monkeypatch.setattr(client, "_api_request", fake_api_request)

    with pytest.raises(AuthenticationError) as exc:
        arun(client.login())

    assert "token may have expired" in str(exc.value)
    assert "sensitive-token" not in str(exc.value)

    redacted = QobuzClient._redact_auth_payload(
        {
            "user_auth_token": "secret-value",
            "password": "legacy-password",
            "app_id": "123456789",
        }
    )
    assert redacted["user_auth_token"] == "***REDACTED***"
    assert redacted["password"] == "***REDACTED***"
    assert redacted["app_id"] == "123456789"


def test_main_reprompts_qobuz_on_authentication_error(monkeypatch):
    class FakeClient:
        source = "qobuz"
        logged_in = False

        async def login(self):
            raise AuthenticationError("stale token")

    class FakePrompter:
        def __init__(self, _config, client):
            self.client = client
            self.prompted = False
            self.saved = False

        def has_creds(self):
            return True

        async def prompt_and_login(self):
            self.prompted = True
            self.client.logged_in = True

        def save(self):
            self.saved = True

    config = Config.defaults()
    config.session.database.downloads_enabled = False
    config.session.database.failed_downloads_enabled = False
    main = Main(config)
    fake_client = FakeClient()
    main.clients["qobuz"] = fake_client
    state = {}

    def fake_get_prompter(client, conf):
        p = FakePrompter(conf, client)
        state["prompter"] = p
        return p

    monkeypatch.setattr("streamrip.rip.main.get_prompter", fake_get_prompter)

    result = arun(main.get_logged_in_client("qobuz"))
    assert result is fake_client
    assert fake_client.logged_in is True
    assert state["prompter"].prompted is True
    assert state["prompter"].saved is True


def test_qobuz_prompter_auto_capture_sets_session_token(monkeypatch):
    config = Config.defaults()
    client = QobuzClient(config)
    prompter = QobuzPrompter(config, client)

    async def fake_capture(timeout_s=300):
        return ("987654", "captured-token")

    monkeypatch.setattr("streamrip.rip.prompter.capture_qobuz_auth_token", fake_capture)

    def fail_prompt(*_args, **_kwargs):
        raise AssertionError("Manual prompt should not run on auto-capture success")

    monkeypatch.setattr("streamrip.rip.prompter.Prompt.ask", fail_prompt)
    monkeypatch.setattr("streamrip.rip.prompter.Confirm.ask", lambda *a, **k: False)

    arun(prompter._prompt_creds_and_set_session_config())
    c = config.session.qobuz
    assert c.use_auth_token is True
    assert c.email_or_userid == "987654"
    assert c.password_or_token == "captured-token"


def test_qobuz_prompter_falls_back_to_manual_prompt(monkeypatch):
    config = Config.defaults()
    client = QobuzClient(config)
    prompter = QobuzPrompter(config, client)

    async def raise_capture_error(timeout_s=300):
        raise QobuzTokenCaptureError("capture failed")

    monkeypatch.setattr(
        "streamrip.rip.prompter.capture_qobuz_auth_token", raise_capture_error
    )
    monkeypatch.setattr("streamrip.rip.prompter.Confirm.ask", lambda *a, **k: False)

    answers = iter(["123123", "manual-token"])
    monkeypatch.setattr(
        "streamrip.rip.prompter.Prompt.ask", lambda *a, **k: next(answers)
    )

    arun(prompter._prompt_creds_and_set_session_config())
    c = config.session.qobuz
    assert c.use_auth_token is True
    assert c.email_or_userid == "123123"
    assert c.password_or_token == "manual-token"


def test_qobuz_prompter_retries_with_auto_capture_after_auth_error(monkeypatch):
    config = Config.defaults()
    c = config.session.qobuz
    c.use_auth_token = True
    c.email_or_userid = "old-user"
    c.password_or_token = "stale-token"

    client = QobuzClient(config)
    prompter = QobuzPrompter(config, client)
    attempts = {"count": 0}

    async def fake_login():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise AuthenticationError("expired token")
        client.logged_in = True

    monkeypatch.setattr(client, "login", fake_login)
    async def fake_capture(timeout_s=300):
        return ("new-user", "new-token")

    monkeypatch.setattr("streamrip.rip.prompter.capture_qobuz_auth_token", fake_capture)

    def fail_prompt(*_args, **_kwargs):
        raise AssertionError("Manual prompts should not run in auto-capture retry")

    monkeypatch.setattr("streamrip.rip.prompter.Prompt.ask", fail_prompt)
    monkeypatch.setattr("streamrip.rip.prompter.Confirm.ask", lambda *a, **k: False)

    arun(prompter.prompt_and_login())
    assert attempts["count"] == 2
    assert config.session.qobuz.email_or_userid == "new-user"
    assert config.session.qobuz.password_or_token == "new-token"


def test_capture_qobuz_auth_token_windows_uses_threaded_helper(monkeypatch):
    monkeypatch.setattr("streamrip.rip.qobuz_token_capture.platform.system", lambda: "Windows")

    captured = {}

    def fake_windows_capture(timeout_s):
        captured["timeout_s"] = timeout_s
        return ("win-user", "win-token")

    async def fake_to_thread(func, timeout_s):
        captured["func"] = func
        return func(timeout_s)

    monkeypatch.setattr(
        "streamrip.rip.qobuz_token_capture._capture_qobuz_auth_token_windows",
        fake_windows_capture,
    )
    monkeypatch.setattr("streamrip.rip.qobuz_token_capture.asyncio.to_thread", fake_to_thread)

    result = arun(capture_qobuz_auth_token(timeout_s=42))
    assert result == ("win-user", "win-token")
    assert captured["timeout_s"] == 42
