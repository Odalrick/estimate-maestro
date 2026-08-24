class EstimateMaestroError(Exception):
    pass


class EffortAlreadyExists(EstimateMaestroError):
    pass


class UnknownSlice(EstimateMaestroError):
    pass
