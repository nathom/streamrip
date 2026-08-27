"""Stored credentials that stop working should offer a fresh login.

`has_creds()` only checks that something is *stored*, not that it still works,
so an expired token passes that check and the failure surfaces from `login()`.
Before this was handled, that meant a traceback -- even though the prompter
that fixes it was already built.
"""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from streamrip.exceptions import AuthenticationError
from streamrip.rip.main import Main


def _main_with_expired_token():
    main = Main.__new__(Main)
    client = MagicMock()
    client.logged_in = False
    client.login = AsyncMock(
        side_effect=AuthenticationError("Tidal refresh token has expired.")
    )
    main.clients = {"tidal": client}
    main.config = MagicMock()

    prompter = MagicMock()
    prompter.has_creds.return_value = True
    prompter.prompt_and_login = AsyncMock(
        side_effect=lambda: setattr(client, "logged_in", True)
    )
    return main, client, prompter


def _patches(prompter, *, isatty: bool, confirm: bool):
    stack = ExitStack()
    stack.enter_context(
        patch("streamrip.rip.main.get_prompter", return_value=prompter)
    )
    stack.enter_context(patch("sys.stdin.isatty", return_value=isatty))
    stack.enter_context(
        patch("streamrip.rip.main.Confirm.ask", return_value=confirm)
    )
    return stack


@pytest.mark.asyncio
async def test_prompts_and_recovers_when_user_agrees():
    main, client, prompter = _main_with_expired_token()
    with _patches(prompter, isatty=True, confirm=True):
        result = await main.get_logged_in_client("tidal")
    prompter.prompt_and_login.assert_awaited_once()
    prompter.save.assert_called_once()
    assert result is client


@pytest.mark.asyncio
async def test_propagates_when_user_declines():
    main, _, prompter = _main_with_expired_token()
    with _patches(prompter, isatty=True, confirm=False):
        with pytest.raises(AuthenticationError, match="refresh token has expired"):
            await main.get_logged_in_client("tidal")
    prompter.prompt_and_login.assert_not_awaited()


@pytest.mark.asyncio
async def test_never_prompts_without_a_terminal():
    """rip runs from cron and from scripts, where a hidden y/n hangs forever."""
    main, _, prompter = _main_with_expired_token()
    with _patches(prompter, isatty=False, confirm=True):
        with pytest.raises(AuthenticationError, match="interactive terminal"):
            await main.get_logged_in_client("tidal")
    prompter.prompt_and_login.assert_not_awaited()
