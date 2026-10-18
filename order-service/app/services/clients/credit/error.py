# Base class for all credit related exceptions
class CreditClientError(Exception):
    pass

# The service is unreachable, times out, or retry later
class CreditServiceUnavailableError(CreditClientError):
    pass

# The user has insufficient credits to reserved the requested
# amount
class InsufficientCreditsError(CreditClientError):
    pass

# The credit account cannot be found
class CreditAccountNotFoundError(CreditClientError):
    pass

# Another reservation request conflicts with the current one
class ReservationConflictError(CreditClientError):
    pass

# User does not own the reservation it is requesting for
class ReservationForbiddenError(CreditClientError):
    pass

# Reservation cannot be found
class ReservationNotFoundError(CreditClientError):
    pass
