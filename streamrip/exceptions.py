"""Streamrip specific exceptions."""

from click import echo, style


class AuthenticationError(Exception):
    """AuthenticationError."""


class MissingCredentialsError(Exception):
    """MissingCredentials."""


class IneligibleError(Exception):
    """IneligibleError.

    Raised when the account is not eligible to stream a track.
    """


class InvalidAppIdError(Exception):
    """InvalidAppIdError."""


class InvalidAppSecretError(Exception):
    """InvalidAppSecretError."""


class NonStreamableError(Exception):
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
                ),
            )

        return " ".join(base_msg)


class ConversionError(Exception):
    """ConversionError."""
