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
