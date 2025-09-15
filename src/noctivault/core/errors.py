class MissingLocalMockError(KeyError):
    pass


class DuplicatePathError(ValueError):
    pass


class TypeCastError(ValueError):
    pass


class InvalidEncHeaderError(ValueError):
    pass


class DecryptError(ValueError):
    pass


class MissingKeyMaterialError(FileNotFoundError):
    pass


class MissingDependencyError(RuntimeError):
    pass


class CombinedConfigNotAllowedError(ValueError):
    pass


# Remote provider error classes
class MissingRemoteSecretError(KeyError):
    pass


class AuthorizationError(PermissionError):
    pass


class RemoteArgumentError(ValueError):
    pass


class RemoteUnavailableError(TimeoutError):
    pass


class RemoteDecodeError(ValueError):
    pass
