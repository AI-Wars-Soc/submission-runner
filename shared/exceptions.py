class MissingFunctionError(AttributeError):
    pass


class FailsafeError(RuntimeError):
    pass


class ExceptionTraceback:
    def __init__(self, e_tb: str):
        self.e_trace = e_tb
