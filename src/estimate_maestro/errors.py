class EstimateMaestroError(Exception):
    pass


class EffortAlreadyExists(EstimateMaestroError):
    pass


class UnknownSlice(EstimateMaestroError):
    pass


class AlreadyClockedIn(EstimateMaestroError):
    pass


class NotClockedIn(EstimateMaestroError):
    pass
