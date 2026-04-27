class RouterError(Exception):
    """Base router error."""


class NotFoundError(RouterError):
    """Requested object does not exist."""


class ConflictError(RouterError):
    """Requested object already exists or conflicts with state."""


class PermissionDeniedError(RouterError):
    """Operation violates routing visibility or policy."""


class InvalidRequestError(RouterError):
    """Request shape or value is invalid."""
