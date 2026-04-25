import aiohttp
from yarl import URL

from .ssl_utils import get_aiohttp_connector_kwargs

try:
    from aiohttp_socks import ProxyConnector
except ImportError:  # pragma: no cover - optional dependency at runtime
    ProxyConnector = None


HTTP_PROXY_SCHEMES = frozenset(("http", "https"))
SOCKS_PROXY_SCHEMES = frozenset(("socks4", "socks5"))
SUPPORTED_PROXY_SCHEMES = HTTP_PROXY_SCHEMES | SOCKS_PROXY_SCHEMES


def get_aiohttp_session_kwargs(
    verify_ssl: bool = True,
    proxy: str | None = None,
) -> dict:
    """Build aiohttp session kwargs for SSL and proxy configuration."""
    connector_kwargs = get_aiohttp_connector_kwargs(verify_ssl=verify_ssl)
    proxy = proxy.strip() if proxy is not None else None
    if not proxy:
        return {"connector": aiohttp.TCPConnector(**connector_kwargs)}

    scheme = URL(proxy).scheme.lower()
    if scheme in HTTP_PROXY_SCHEMES:
        return {
            "connector": aiohttp.TCPConnector(**connector_kwargs),
            "proxy": proxy,
        }

    if scheme in SOCKS_PROXY_SCHEMES:
        if ProxyConnector is None:
            raise RuntimeError(
                "SOCKS proxy support requires the optional aiohttp_socks package.",
            )
        return {"connector": ProxyConnector.from_url(proxy, **connector_kwargs)}

    supported = ", ".join(sorted(SUPPORTED_PROXY_SCHEMES))
    raise ValueError(
        f"Unsupported proxy scheme '{scheme}'. Supported schemes: {supported}",
    )
