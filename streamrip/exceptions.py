"""Streamrip specific exceptions."""


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


class ConversionError(Exception):
    """ConversionError."""
