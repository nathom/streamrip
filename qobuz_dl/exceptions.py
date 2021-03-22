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
