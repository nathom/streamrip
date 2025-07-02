"""Streamrip specific exceptions."""

from click import echo, style


class StreamripError(Exception):
    """Base exception for all custom streamrip errors."""

    def __init__(self, message=None, item=None):
        self.item = item  # Optional: to associate an error with a specific media item
        super().__init__(message)

    def get_display_message(self) -> str:
        """
        Returns a user-friendly message for this error.
        Can be overridden by subclasses for more specific messages.
        """
        base_msg = self.args[0] if self.args and self.args[0] else self.__class__.__name__
        if self.item:
            return f"Error processing {self.item!s}: {base_msg}"
        return base_msg


# --- General Application Errors ---
class ConfigError(StreamripError):
    """For errors related to configuration."""


class OutdatedConfigError(ConfigError):
    """Raised when the config file version is outdated."""
    # This class is defined in config.py and should be imported if needed elsewhere,
    # or defined there and then imported here. For now, placeholder.
    pass


class InvalidURLError(StreamripError):
    """For when a provided URL cannot be parsed or is not supported."""


class OperationFailedError(StreamripError):
    """Generic error for when an operation fails without a more specific cause."""


# --- Client/API Related Errors ---
class ClientError(StreamripError):
    """Base exception for errors originating in API clients."""


class AuthenticationError(ClientError):
    """For login or authentication failures."""


class MissingCredentialsError(AuthenticationError):
    """Credentials not provided."""


class InvalidCredentialsError(AuthenticationError):
    """Provided credentials are invalid."""


class APIError(ClientError):
    """For errors returned by the streaming service's API."""


class APILimitError(APIError):
    """API rate limit exceeded."""


class ResourceNotFoundError(APIError):
    """Requested resource (track, album, etc.) not found on the API."""


class ServiceUnavailableError(APIError):
    """The service's API is temporarily unavailable."""


class InvalidAPIResponseError(APIError):
    """The API response is not in the expected format."""


class SpecificServiceAPIError(APIError):
    """Base exception for errors specific to a service (e.g., QobuzAPIError)."""


class QobuzAPIError(SpecificServiceAPIError):
    """For errors specific to the Qobuz API."""


class InvalidAppIdError(QobuzAPIError):
    """Invalid Qobuz App ID."""


class IneligibleError(QobuzAPIError):
    """Account is not eligible for the requested operation (e.g., streaming)."""


class NonStreamableError(QobuzAPIError):
    """Item is not streamable. Can have many causes, typically Qobuz related."""

    def __init__(self, message=None, item=None):
        super().__init__(message=message, item=item)

    # Consider moving display logic to the UI layer in the future.
    def print(self, item_media): # item_media is likely a Media object
        """Print a readable version of the exception related to a media item."""
        echo(self.print_msg(item_media))

    def print_msg(self, item_media) -> str:
        """Return a generic readable message for a media item."""
        message_to_display = self.args[0] if self.args and self.args[0] else "Not streamable"

        # Construct the item string representation safely
        item_str = "Unknown Item"
        try:
            item_str = str(item_media)
        except Exception:
            # If str(item_media) fails, use a fallback.
            pass

        base_msg_parts = [style(f"Unable to stream {item_str}.", fg="yellow")]
        if message_to_display:
            base_msg_parts.extend(
                (
                    style(" Message:", fg="yellow"),
                    style(str(message_to_display), fg="red"),
                ),
            )
        return " ".join(base_msg_parts)


class InvalidAppSecretError(QobuzAPIError):
    """Invalid Qobuz App Secret."""


class TidalAPIError(SpecificServiceAPIError):
    """For errors specific to the Tidal API."""


class DeezerAPIError(SpecificServiceAPIError):
    """For errors specific to the Deezer API."""


class SoundcloudAPIError(SpecificServiceAPIError):
    """For errors specific to the SoundCloud API."""


class NetworkError(ClientError):
    """For network connectivity issues (e.g., DNS failure, connection refused)."""


class DownloadError(ClientError):
    """For specific errors that occur during file download."""


class DownloadDirectoryError(DownloadError):
    """Problem with the download directory (e.g., no write permission)."""


# --- Media Processing Errors ---
class MediaProcessingError(StreamripError):
    """Error during media file processing (e.g., conversion, tagging)."""


class ConversionError(MediaProcessingError):
    """Error during audio format conversion."""


class TaggingError(MediaProcessingError):
    """Error while writing metadata to the file."""

# Note: OutdatedConfigError is actually defined in config.py.
# It should be imported there if streamrip.exceptions is to be the central place for exceptions.
# For now, the definition in config.py takes precedence if both exist.
# This file provides a comprehensive hierarchy.
# Ensure that existing `raise` statements are updated to use these new exceptions.
# Example: raise AuthenticationError("Specific message") instead of Exception("...")
# The original NonStreamableError had a self.message attribute.
# The base Exception class stores the first arg to __init__ in self.args[0].
# The print_msg method was adapted.
# Make sure to adjust the import in config.py if OutdatedConfigError is primarily defined here.
# from .exceptions import OutdatedConfigError (in config.py)
# Or, remove OutdatedConfigError from here and import it from config.py.
# For this step, we assume this file is the source of truth for the hierarchy.
# The class `OutdatedConfigError` from `streamrip.config` will be used, so we can remove the placeholder here.

del OutdatedConfigError # Remove the placeholder as it's defined in config.py

# Import it for completeness if this module needs to know about it, though typically not necessary
# from ..config import OutdatedConfigError (This would cause circular import if config.py imports from here)
# It's generally better that config.py's OutdatedConfigError inherits from ConfigError defined here.
# This will be handled in the step where config.py is refactored.
# For now, just ensuring the hierarchy is defined.
# The `del` statement above removes the local definition of OutdatedConfigError.
# We will adjust `streamrip.config.OutdatedConfigError` to inherit from `ConfigError` in a later step.
