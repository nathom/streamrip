import hashlib
import os

import pytest

from streamrip.config import Config


@pytest.fixture()
def config():
    c = Config.defaults()
    c.session.qobuz.email_or_userid = os.environ["QOBUZ_EMAIL"]
    c.session.qobuz.password_or_token = hashlib.md5(
        os.environ["QOBUZ_PASSWORD"].encode("utf-8"),
    ).hexdigest()
    return c
