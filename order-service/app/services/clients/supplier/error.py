# Base class for all supplier related error in the Order Service
class SupplierClientError(Exception):
    pass

class SupplierNotFoundError(SupplierClientError):
    pass

class SupplierInactiveError(SupplierClientError):
    pass

class SupplierServiceUnavailableError(SupplierClientError):
    pass

class SupplierServiceContractError(SupplierClientError):
    pass

class UnexpectedSupplierResponseError(SupplierClientError):
    pass