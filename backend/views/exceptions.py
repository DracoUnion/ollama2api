"""自定义异常类"""


class AppError(Exception):
    """应用基础异常"""

    def __init__(self, code: int, msg: str, data=None):
        self.code = code
        self.msg = msg
        self.data = data
        super().__init__(msg)


class BadRequestError(AppError):
    """400 请求参数错误"""

    def __init__(self, msg="请求参数错误", data=None):
        super().__init__(400, msg, data)


class UnauthorizedError(AppError):
    """401 未授权"""

    def __init__(self, msg="未登录或 Session 过期", data=None):
        super().__init__(401, msg, data)


class NotFoundError(AppError):
    """404 资源不存在"""

    def __init__(self, msg="资源不存在", data=None):
        super().__init__(404, msg, data)


class ConflictError(AppError):
    """409 资源冲突"""

    def __init__(self, msg="资源冲突", data=None):
        super().__init__(409, msg, data)


class ServerError(AppError):
    """500 服务器内部错误"""

    def __init__(self, msg="服务器内部错误", data=None):
        super().__init__(500, msg, data)


class BadGatewayError(AppError):
    """502 外部服务错误"""

    def __init__(self, msg="外部服务错误", data=None):
        super().__init__(502, msg, data)


class ServiceUnavailableError(AppError):
    """503 服务不可用"""

    def __init__(self, msg="服务不可用", data=None):
        super().__init__(503, msg, data)
