# AI-INFLUENCED: Supplier category filter error added with Codex; see ai/usage-log.md.
# Base class for all supplier related error in the Order Service
class SupplierClientError(Exception):
    pass


class SupplierNotFoundError(SupplierClientError):
    pass


class SupplierInactiveError(SupplierClientError):
    pass


class SupplierCategoryFilterError(SupplierClientError):
    pass


class SupplierServiceUnavailableError(SupplierClientError):
    pass


class SupplierServiceContractError(SupplierClientError):
    pass


class UnexpectedSupplierResponseError(SupplierClientError):
    pass
