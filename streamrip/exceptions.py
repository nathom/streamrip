class AuthenticationError(Exception):
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
    pass


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
