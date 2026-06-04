"""统一异常处理器"""

from flask import jsonify
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from .exceptions import AppError


def register_error_handlers(app):
    """注册全局异常处理器"""

    @app.errorhandler(AppError)
    def handle_app_error(e):
        """处理自定义业务异常"""
        return jsonify({
            "code": e.code,
            "data": e.data,
            "msg": e.msg
        })

    @app.errorhandler(Exception)
    def handle_generic_error(e):
        """处理未捕获的异常"""
        app.logger.error(f"Unhandled error: {str(e)}", exc_info=True)
        return jsonify({
            "code": 500,
            "data": None,
            "msg": f"服务器内部错误：{e}"
        })
