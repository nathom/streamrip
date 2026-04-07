"""Bridge between web UI config (SQLite) and streamrip Config (TOML dataclass)."""

import logging
import os

logger = logging.getLogger("streamrip")


def build_streamrip_config(db):
    """Build a streamrip Config object from web UI database values.

    This is the single source of truth for constructing a Config
    that the existing streamrip pipeline (Main, clients) can use.
    """
    from streamrip.config import Config

    # Start from defaults
    config_path = os.environ.get(
        "STREAMRIP_CONFIG_PATH",
        os.path.expanduser("~/.config/streamrip/config.toml"),
    )
    if os.path.exists(config_path):
        config = Config(config_path)
    else:
        config = Config.defaults()

    # Qobuz credentials
    qobuz_token = db.get_config("qobuz_token")
    qobuz_user_id = db.get_config("qobuz_user_id")
    if qobuz_token:
        config.session.qobuz.use_auth_token = True
        config.session.qobuz.email_or_userid = qobuz_user_id or ""
        config.session.qobuz.password_or_token = qobuz_token

    qobuz_quality = db.get_config("qobuz_quality")
    if qobuz_quality:
        config.session.qobuz.quality = int(qobuz_quality)

    # Tidal credentials
    tidal_token = db.get_config("tidal_access_token")
    if tidal_token:
        config.session.tidal.access_token = tidal_token

    tidal_quality = db.get_config("tidal_quality")
    if tidal_quality:
        config.session.tidal.quality = int(tidal_quality)

    # Downloads
    downloads_path = db.get_config("downloads_path")
    if downloads_path:
        config.session.downloads.folder = downloads_path
    elif not config.session.downloads.folder:
        # Fallback to /music (Docker mount) or ~/Music
        config.session.downloads.folder = os.environ.get(
            "STREAMRIP_DOWNLOADS_PATH", "/music"
        )

    max_connections = db.get_config("max_connections")
    if max_connections:
        config.session.downloads.max_connections = int(max_connections)

    # File paths
    folder_format = db.get_config("folder_format")
    if folder_format:
        config.session.filepaths.folder_format = folder_format

    track_format = db.get_config("track_format")
    if track_format:
        config.session.filepaths.track_format = track_format

    # Conversion
    conversion_enabled = db.get_config("conversion_enabled")
    if conversion_enabled:
        config.session.conversion.enabled = conversion_enabled.lower() in ("true", "1")

    conversion_codec = db.get_config("conversion_codec")
    if conversion_codec:
        config.session.conversion.codec = conversion_codec

    # Database paths — ensure they're set
    db_dir = os.path.dirname(
        os.environ.get("STREAMRIP_DB_PATH", "data/streamrip.db")
    ) or "data"
    os.makedirs(db_dir, exist_ok=True)

    if not config.session.database.downloads_path:
        config.session.database.downloads_path = os.path.join(db_dir, "downloads.db")
    if not config.session.database.failed_downloads_path:
        config.session.database.failed_downloads_path = os.path.join(db_dir, "failed.db")

    # SSL
    config.session.downloads.verify_ssl = True

    return config
