class APIError(Exception):
    def __init__(self, msg: str, code: int = -1, status_code: int = 400, details=None):
        super().__init__(msg)
        self.msg = msg
        self.code = code
        self.status_code = status_code
        self.details = details

