import json
from typing import Any, Dict

import pytest
from pytest_mock.plugin import MockerFixture
from requests import Session

from streamrip.clients import QobuzClient
from streamrip.exceptions import MissingCredentials


class TestQobuzClient:
    @pytest.fixture
    def login_json_response(self) -> Dict[str, Any]:
        return {
            "user": {
                "credential": {
                    "parameters": {
                        "lossy_streaming": True,
                        "lossless_streaming": True,
                        "hires_streaming": True,
                        "hires_purchases_streaming": True,
                        "mobile_streaming": True,
                        "offline_streaming": True,
                        "hfp_purchase": False,
                        "included_format_group_ids": [1, 2, 3, 4],
                        "color_scheme": {"logo": "#B8D729"},
                        "label": "Qobuz Studio",
                        "short_label": "Studio",
                        "source": "subscription",
                    },
                },
            },
            "user_auth_token": "fake_token",
        }

    @pytest.fixture
    def qobuz_client(self) -> QobuzClient:
        client = QobuzClient()
        return client

    def test_login_without_arguments_should_throw(self, qobuz_client: QobuzClient):
        with pytest.raises(KeyError) as exc_info:
            qobuz_client.login()

        assert exc_info.value.args[0] == "email"

    def test_login_blank_email_should_throw(self, qobuz_client: QobuzClient):
        with pytest.raises(MissingCredentials) as exc_info1:
            qobuz_client.login(email=None, pwd="foo")

        with pytest.raises(MissingCredentials) as exc_info2:
            qobuz_client.login(email="foo", pwd=None)

    def test_a_successful_login_session(
        self,
        qobuz_client: QobuzClient,
        mocker: MockerFixture,
        login_json_response: json,
    ):
        mocked_get = mocker.patch.object(Session, "get")
        get_call = mocked_get.return_value
        get_call.json.return_value = login_json_response
        get_call.status_code = 200
        get_call.text = json.dumps(login_json_response)

        qobuz_client.login(email="foo", pwd="bar")

        assert qobuz_client.uat == "fake_token"
        assert qobuz_client.label == "Studio"
        assert qobuz_client.logged_in == True
        mocked_get.assert_called_with(
            "https://www.qobuz.com/api.json/0.2/user/login",
            params={"email": "foo", "password": "bar", "app_id": "814460817"},
        )
