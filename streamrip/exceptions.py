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
        print(self.print_msg(item))

    def print_msg(self, item) -> str:
        base_msg = click.style(f"Unable to stream {item!s}.", fg="yellow")
        if self.message:
            base_msg += click.style(" Message: ", fg="yellow") + click.style(
                self.message, fg="red"
            )

        return base_msg


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
