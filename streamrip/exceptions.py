"""Streamrip specific exceptions."""
from typing import List

from click import echo, style


class AuthenticationError(Exception):
    """AuthenticationError."""


class MissingCredentials(Exception):
    """MissingCredentials."""


class IneligibleError(Exception):
    """IneligibleError.

    Raised when the account is not eligible to stream a track.
    """


class InvalidAppIdError(Exception):
    """InvalidAppIdError."""


class InvalidAppSecretError(Exception):
    """InvalidAppSecretError."""


class InvalidQuality(Exception):
    """InvalidQuality."""


class NonStreamable(Exception):
    """Item is not streamable.

    A versatile error that can have many causes.
    """

    def __init__(self, message=None):
        """Create a NonStreamable exception.

        :param message:
        """
        self.message = message
        super().__init__(self.message)

    def print(self, item):
        """Print a readable version of the exception.

        :param item:
        """
        echo(self.print_msg(item))

    def print_msg(self, item) -> str:
        """Return a generic readable message.

        :param item:
        :type item: Media
        :rtype: str
        """
        base_msg = [style(f"Unable to stream {item!s}.", fg="yellow")]
        if self.message:
            base_msg.extend(
                (
                    style("Message:", fg="yellow"),
                    style(self.message, fg="red"),
                )
            )

        return " ".join(base_msg)


class InvalidContainerError(Exception):
    """InvalidContainerError."""


class InvalidSourceError(Exception):
    """InvalidSourceError."""


class ParsingError(Exception):
    """ParsingError."""


class TooLargeCoverArt(Exception):
    """TooLargeCoverArt."""


class BadEncoderOption(Exception):
    """BadEncoderOption."""


class ConversionError(Exception):
    """ConversionError."""


class NoResultsFound(Exception):
    """NoResultsFound."""


class ItemExists(Exception):
    """ItemExists."""


class PartialFailure(Exception):
    """Raise if part of a tracklist fails to download."""

    def __init__(self, failed_items: List):
        """Create a PartialFailure exception.

        :param failed_items:
        :type failed_items: List
        """
        self.failed_items = failed_items
        super().__init__()
