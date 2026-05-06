class NotFoundException(Exception):
    pass


class DppAlreadyExistsException(Exception):
    pass


class DppRevisionConflictException(Exception):
    pass


class DppReferenceResolutionException(Exception):
    def __init__(self, unresolved_reference: str) -> None:
        super().__init__(f"Could not resolve hard reference: {unresolved_reference}")
        self.unresolved_reference = unresolved_reference


class DppCycleDetectedException(Exception):
    def __init__(self, cycle_path: list[str]) -> None:
        super().__init__(f"Hard-dependency cycle detected: {' -> '.join(cycle_path)}")
        self.cycle_path = cycle_path


class SchemaValidationException(ValueError):
    def __init__(self, validation_errors: list[str]) -> None:
        super().__init__("; ".join(validation_errors))
        self.validation_errors = validation_errors
