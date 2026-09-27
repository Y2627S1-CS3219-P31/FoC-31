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


class NotificationDeliveryError(Exception):
    pass


class OtpRateLimitError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class CannotModifyAdminError(Exception):
    pass
