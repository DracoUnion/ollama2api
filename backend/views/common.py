"""公共工具函数"""

import uuid

import requests
from flask import jsonify

from .exceptions import ServiceUnavailableError


def success(data=None, msg=""):
    """统一成功响应"""
    return jsonify({"code": 0, "data": data, "msg": msg})


def error(code: int, msg: str, data=None):
    """统一错误响应"""
    return jsonify({"code": code, "data": data, "msg": msg})


def generate_node_id() -> str:
    """生成节点 ID"""
    return f"ep_{uuid.uuid4().hex[:8]}"


def call_ollama_tags(url: str, timeout: int = 10):
    """调用 Ollama /api/tags 获取模型列表"""
    response = requests.get(f"{url}/api/tags", timeout=timeout)
    response.raise_for_status()
    data = response.json()
    models = data.get("models", [])
    return [m.get("name", "") for m in models if m.get("name")]
