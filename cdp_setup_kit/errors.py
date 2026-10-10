class KitError(Exception):
    def __init__(self, exit_code: int, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.hint = hint


class RealActionForbidden(KitError):
    def __init__(self) -> None:
        super().__init__(6, "refused: test mode")
