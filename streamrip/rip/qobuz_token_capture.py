import asyncio
import logging
import platform
import time

logger = logging.getLogger("streamrip")

QOBUZ_LOGIN_PAGE = "https://play.qobuz.com/login"
QOBUZ_LOGIN_API = "https://www.qobuz.com/api.json/0.2/user/login"


class QobuzTokenCaptureError(Exception):
    """Raised when automatic Qobuz token capture fails."""


async def _capture_qobuz_auth_token_async(timeout_s: int = 300) -> tuple[str, str]:
    """Capture user id and auth token from Qobuz web login traffic.

    Returns:
        Tuple of (user_id, user_auth_token)
    """
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # pragma: no cover - import path only
        raise QobuzTokenCaptureError(
            "Automatic browser capture requires Playwright. "
            "Install it and run `playwright install chromium`, or use manual token input."
        ) from exc

    result: dict[str, str] = {}

    async def handle_response(response):
        if response.url != QOBUZ_LOGIN_API:
            return

        try:
            post_data = response.request.post_data or ""
            if post_data and "extra=partner" not in post_data:
                return
            if response.status != 200:
                return
            payload = await response.json()
        except Exception:
            return

        if not isinstance(payload, dict):
            return

        user = payload.get("user", {})
        user_id = user.get("id")
        token = payload.get("user_auth_token")
        if user_id is None or not token:
            return

        result["user_id"] = str(user_id)
        result["token"] = str(token)

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            page.on("response", handle_response)
            await page.goto(QOBUZ_LOGIN_PAGE, wait_until="domcontentloaded")

            logger.info(
                "Waiting for Qobuz login response in browser (timeout: %ss).",
                timeout_s,
            )
            deadline = time.monotonic() + timeout_s
            while "token" not in result and time.monotonic() < deadline:
                await page.wait_for_timeout(250)

            await context.close()
            await browser.close()
    except Exception as exc:
        raise QobuzTokenCaptureError(
            f"Automatic browser capture failed: {exc}"
        ) from exc

    if "token" not in result or "user_id" not in result:
        raise QobuzTokenCaptureError(
            "Could not detect a successful Qobuz user/login response. "
            "Please complete login in the opened browser or use manual token input."
        )

    return result["user_id"], result["token"]


def _capture_qobuz_auth_token_windows(timeout_s: int) -> tuple[str, str]:
    """Run Playwright capture in an isolated Proactor loop on Windows."""
    if not hasattr(asyncio, "ProactorEventLoop"):
        raise QobuzTokenCaptureError(
            "Windows Proactor event loop is unavailable; use manual token input."
        )

    loop = asyncio.ProactorEventLoop()  # type: ignore[attr-defined]
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_capture_qobuz_auth_token_async(timeout_s))
    finally:
        loop.close()
        asyncio.set_event_loop(None)


async def capture_qobuz_auth_token(timeout_s: int = 300) -> tuple[str, str]:
    """Capture user id and auth token from Qobuz web login traffic."""
    if platform.system() == "Windows":
        return await asyncio.to_thread(_capture_qobuz_auth_token_windows, timeout_s)
    return await _capture_qobuz_auth_token_async(timeout_s)
