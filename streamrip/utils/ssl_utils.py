"""Utility functions for SSL handling."""

import logging
import ssl
import sys

logger = logging.getLogger("streamrip")

try:
    import certifi

    HAS_CERTIFI = True
except ImportError:
    logger.debug("certifi not found, falling back to system certificates")
    HAS_CERTIFI = False


def create_ssl_context(verify=True):
    """Create an SSL context with the appropriate verification settings.

    Args:
        verify: Whether to verify SSL certificates

    Returns:
        An SSL context object with the specified verification settings
    """
    if not verify:
        # Disable verification entirely when requested
        logger.warning("SSL certificate verification disabled (less secure)")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    # Use certifi for certificate verification if available
    if HAS_CERTIFI:
        return ssl.create_default_context(cafile=certifi.where())
    else:
        return ssl.create_default_context()


def get_aiohttp_connector_kwargs(verify_ssl=True):
    """Get keyword arguments for aiohttp.TCPConnector with SSL settings.

    Args:
        verify_ssl: Whether to verify SSL certificates

    Returns:
        Dictionary of kwargs to pass to aiohttp.TCPConnector
    """
    if not verify_ssl:
        return {"verify_ssl": False}

    if HAS_CERTIFI:
        ssl_context = create_ssl_context(verify=True)
        return {"ssl": ssl_context}
    else:
        return {"verify_ssl": True}


def print_ssl_error_help():
    """Print helpful error message when SSL verification fails."""
    print("\nError: Cannot verify SSL certificate.")
    print("Options:")
    print("  1. Run again with the --no-ssl-verify flag (less secure)")
    print(
        '     Example: rip --no-ssl-verify url "https://tidal.com/browse/playlist/..."'
    )
    print()
    print("  2. Install certifi for better certificate handling:")
    print("     pip install certifi")
    print()
    print("  3. Update your certificates:")
    print("     pip install --upgrade certifi")
    sys.exit(1)
