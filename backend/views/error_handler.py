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

    @app.errorhandler(ValidationError)
    def handle_validation_error(e):
        """处理 Pydantic 参数校验异常"""
        return jsonify({
            "code": 400,
            "data": None,
            "msg": f"参数校验失败: {str(e)}"
        })

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(e):
        """处理数据库完整性约束异常"""
        return jsonify({
            "code": 409,
            "data": None,
            "msg": "数据冲突，可能重复添加"
        })

    @app.errorhandler(404)
    def handle_404(e):
        """处理 404 异常"""
        return jsonify({
            "code": 404,
            "data": None,
            "msg": "接口不存在"
        })

    @app.errorhandler(405)
    def handle_405(e):
        """处理 405 异常"""
        return jsonify({
            "code": 405,
            "data": None,
            "msg": "请求方法不允许"
        })

    @app.errorhandler(Exception)
    def handle_generic_error(e):
        """处理未捕获的异常"""
        app.logger.error(f"Unhandled error: {str(e)}", exc_info=True)
        return jsonify({
            "code": 500,
            "data": None,
            "msg": "服务器内部错误"
        })
