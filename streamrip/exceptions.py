from typing import List
import click


class AuthenticationError(Exception):
    pass


class MissingCredentials(Exception):
    pass


class IneligibleError(Exception):
    pass


class InvalidAppIdError(Exception):
    pass


class InvalidAppSecretError(Exception):
    pass


class InvalidQuality(Exception):
    pass


class NonStreamable(Exception):
    def __init__(self, message=None):
        self.message = message
        super().__init__(self.message)

    def print(self, item):
        if self.message:
            click.secho(f"Unable to stream {item!s}. Message: ", nl=False, fg="yellow")
            click.secho(self.message, fg="red")
        else:
            click.secho(f"Unable to stream {item!s}.", fg="yellow")


class InvalidContainerError(Exception):
    pass


class InvalidSourceError(Exception):
    pass


class ParsingError(Exception):
    pass


class TooLargeCoverArt(Exception):
    pass


class BadEncoderOption(Exception):
    pass


class ConversionError(Exception):
    pass


class NoResultsFound(Exception):
    pass


class ItemExists(Exception):
    pass


class PartialFailure(Exception):
    def __init__(self, failed_items: List):
        self.failed_items = failed_items
        super().__init__()
