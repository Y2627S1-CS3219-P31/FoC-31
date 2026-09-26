class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AccountNotVerifiedError(Exception):
    pass


class AccountSuspendedError(Exception):
    pass


class InvalidOtpError(Exception):
    pass


class AccountNotFoundError(Exception):
    pass


class AccountEmailAlreadyVerifiedError(Exception):
    pass