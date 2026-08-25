class EstimateMaestroError(Exception):
    pass


class EffortAlreadyExists(EstimateMaestroError):
    def __init__(self, effort: str):
        super().__init__(f"an effort already exists with this identifier: {effort}")


class UnknownSlice(EstimateMaestroError):
    def __init__(self, work_slice: str):
        super().__init__(f"unknown slice: {work_slice}")


class UnknownEffort(EstimateMaestroError):
    def __init__(self, effort: str):
        super().__init__(f"unknown effort: {effort}")


class AlreadyClockedIn(EstimateMaestroError):
    pass


class NotClockedIn(EstimateMaestroError):
    pass


class MalformedArgument(EstimateMaestroError):
    def __init__(self, argument: str, value: str):
        super().__init__(f"{argument} is not a valid ISO 8601 timestamp: {value!r}")


class InvalidConfiguration(EstimateMaestroError):
    pass
