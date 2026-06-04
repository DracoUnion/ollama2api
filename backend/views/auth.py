"""认证模块"""

from functools import wraps

from flask import request

from .exceptions import UnauthorizedError


def check_auth():
    """检查管理接口认证"""
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise UnauthorizedError()
    # TODO: 验证 session 有效性
    return True


def require_auth(f):
    """认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        check_auth()
        return f(*args, **kwargs)

    return decorated
