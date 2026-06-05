"""OpenAI 兼容 API 视图"""

import random
import time
import uuid
from datetime import datetime

import requests as http_requests
from flask import Blueprint, request, Response, jsonify

import config
from views.common import success, error
from models import Session, ModelMapping, Node, NodeModel, RequestLog
from views.exceptions import UnauthorizedError, NotFoundError, BadGatewayError

openai_bp = Blueprint("openai", __name__, url_prefix="/v1")


# ==================== 异常处理器 ====================

@openai_bp.errorhandler(Exception)
def handle_openai_error(e):
    """OpenAI 兼容格式的异常处理"""
    from views.exceptions import AppError

    if isinstance(e, AppError):
        status_code = e.code
        message = e.msg
    else:
        status_code = 500
        message = str(e)

    return jsonify({
        "error": {
            "message": message,
            "type": "invalid_request_error" if status_code < 500 else "server_error",
            "param": None,
            "code": None
        }
    }), status_code


def check_api_key():
    """检查 API Key"""
    api_key = request.headers.get("Authorization", "").replace("Bearer ", "")
    if config.API_KEY and api_key != config.API_KEY:
        raise UnauthorizedError("Invalid API Key")


def resolve_model(db, model_name):
    """解析模型名，查询映射表获取实际模型名"""
    mapping = db.query(ModelMapping).filter(ModelMapping.virtual_name == model_name).first()
    if mapping:
        return mapping.actual_model_name
    return model_name


def select_node(db, model_name):
    """选择可用节点"""
    nodes = db.query(Node).join(NodeModel).filter(
        Node.enabled == True,
        Node.healthy == True,
        NodeModel.model_name == model_name,
    ).all()
    if not nodes:
        raise NotFoundError("没有可用的健康节点")
    # 简化版：选择第一个健康节点
    return random.choice(nodes)


def generate_log_id():
    """生成日志 ID"""
    return f"log_{uuid.uuid4().hex[:8]}"


def record_log(db, **kwargs):
    """记录请求日志"""
    log = RequestLog(
        id=generate_log_id(),
        timestamp=datetime.now(),
        **kwargs
    )
    db.add(log)
    db.commit()


# ==================== 模型列表 ====================

@openai_bp.route("/models", methods=["GET"])
def list_models():
    """
    列出所有可用模型

    返回所有节点上可用的模型列表（去重）。
    """
    check_api_key()

    db = Session()

    # 获取所有启用节点的模型
    models = db.query(NodeModel.model_name).join(Node).filter(
        Node.enabled == True
    ).distinct().all()

    now = int(time.time())

    return jsonify({
        "object": "list",
        "data": [
            {
                "id": m.model_name,
                "object": "model",
                "created": now,
                "owned_by": "ollama"
            }
            for m in models
        ]
    })


# ==================== 文本补全 ====================

@openai_bp.route("/completions", methods=["POST"])
def create_completion():
    """
    创建文本补全

    请求体:
    - model: 模型名称（必填）
    - prompt: 提示词（必填）
    - max_tokens: 最大生成 token 数（可选）
    - temperature: 温度（可选）
    - stream: 是否流式返回（默认 false）
    """
    check_api_key()

    data = request.get_json()
    if not data:
        return error(400, "请求体必须是 JSON")

    model = data.get("model")
    prompt = data.get("prompt", "")
    stream = data.get("stream", False)

    if not model:
        return error(400, "model 不能为空")

    db = Session()

    # 解析实际模型名
    actual_model = resolve_model(db, model)

    # 选择节点
    node = select_node(db, actual_model)

    start_time = time.time()

    try:
        # 转发请求到 Ollama /api/generate
        ollama_response = http_requests.post(
            f"{node.url}/api/generate",
            json={
                "model": actual_model,
                "prompt": prompt,
                "stream": stream,
                **{k: v for k, v in data.items() if k not in ("model", "prompt", "stream")}
            },
            timeout=(config.REQUEST_CONN_TIMEOUT, config.REQUEST_READ_TIMEOUT),
            stream=stream
        )
        ollama_response.raise_for_status()

        duration_ms = int((time.time() - start_time) * 1000)

        # 流式返回
        if stream:
            client_ip = request.remote_addr or ""

            def generate():
                full_response = ""
                for line in ollama_response.iter_lines():
                    if line:
                        chunk = line.decode("utf-8")
                        full_response += chunk
                        # 转换为 OpenAI 格式的 SSE
                        yield f"data: {chunk}\n\n"
                yield "data: [DONE]\n\n"

                # 记录日志
                with Session() as log_db:
                    record_log(
                        log_db,
                        client_ip=client_ip,
                        virtual_model=model,
                        actual_backend=node.url,
                        actual_model=actual_model,
                        status_code=200,
                        duration_ms=duration_ms,
                        stream=True,
                        request_body=str(data)[:1000],
                        response_preview=full_response[:500]
                    )

            return Response(
                generate(),
                content_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no"
                }
            )

        # 同步返回
        result = ollama_response.json()

        # 转换为 OpenAI 格式
        usage = result.get("usage", {})
        openai_result = {
            "id": f"cmpl-{uuid.uuid4().hex[:8]}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "text": result.get("response", ""),
                    "index": 0,
                    "finish_reason": "stop" if result.get("done") else "length"
                }
            ],
            "usage": {
                "prompt_tokens": usage.get("prompt_eval_count", 0),
                "completion_tokens": usage.get("eval_count", 0),
                "total_tokens": usage.get("prompt_eval_count", 0) + usage.get("eval_count", 0)
            }
        }

        # 记录日志
        record_log(
            db,
            client_ip=request.remote_addr or "",
            virtual_model=model,
            actual_backend=node.url,
            actual_model=actual_model,
            status_code=200,
            duration_ms=duration_ms,
            prompt_tokens=openai_result["usage"]["prompt_tokens"],
            completion_tokens=openai_result["usage"]["completion_tokens"],
            stream=False,
            request_body=str(data)[:1000],
            response_preview=result.get("response", "")[:500]
        )

        return jsonify(openai_result)

    except http_requests.exceptions.RequestException as e:
        duration_ms = int((time.time() - start_time) * 1000)

        # 记录错误日志
        record_log(
            db,
            client_ip=request.remote_addr or "",
            virtual_model=model,
            actual_backend=node.url,
            actual_model=actual_model,
            status_code=502,
            duration_ms=duration_ms,
            stream=stream,
            error_message=str(e),
            request_body=str(data)[:1000]
        )

        raise BadGatewayError(f"后端服务错误: {str(e)}")


# ==================== 对话补全 ====================

@openai_bp.route("/chat/completions", methods=["POST"])
def create_chat_completion():
    """
    创建对话补全

    请求体:
    - model: 模型名称（必填）
    - messages: 消息列表（必填）
    - max_tokens: 最大生成 token 数（可选）
    - temperature: 温度（可选）
    - stream: 是否流式返回（默认 false）
    """
    check_api_key()

    data = request.get_json()
    if not data:
        return error(400, "请求体必须是 JSON")

    model = data.get("model")
    messages = data.get("messages", [])
    stream = data.get("stream", False)

    if not model:
        return error(400, "model 不能为空")
    if not messages:
        return error(400, "messages 不能为空")

    db = Session()

    # 解析实际模型名
    actual_model = resolve_model(db, model)

    # 选择节点
    node = select_node(db, actual_model)

    start_time = time.time()

    try:
        # 转发请求到 Ollama /api/chat
        ollama_response = http_requests.post(
            f"{node.url}/api/chat",
            json={
                "model": actual_model,
                "messages": messages,
                "stream": stream,
                **{k: v for k, v in data.items() if k not in ("model", "messages", "stream")}
            },
            timeout=(config.REQUEST_CONN_TIMEOUT, config.REQUEST_READ_TIMEOUT),
            stream=stream
        )
        ollama_response.raise_for_status()

        duration_ms = int((time.time() - start_time) * 1000)

        # 流式返回
        if stream:
            client_ip = request.remote_addr or ""

            def generate():
                full_response = ""
                for line in ollama_response.iter_lines():
                    if line:
                        chunk = line.decode("utf-8")
                        full_response += chunk
                        yield f"data: {chunk}\n\n"
                yield "data: [DONE]\n\n"

                # 记录日志
                with Session() as log_db:
                    record_log(
                        log_db,
                        client_ip=client_ip,
                        virtual_model=model,
                        actual_backend=node.url,
                        actual_model=actual_model,
                        status_code=200,
                        duration_ms=duration_ms,
                        stream=True,
                        request_body=str(data)[:1000],
                        response_preview=full_response[:500]
                    )

            return Response(
                generate(),
                content_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no"
                }
            )

        # 同步返回
        result = ollama_response.json()

        # 转换为 OpenAI 格式
        message = result.get("message", {})
        usage = result.get("usage", {})
        openai_result = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": message.get("role", "assistant"),
                        "content": message.get("content", "")
                    },
                    "finish_reason": "stop" if result.get("done") else "length"
                }
            ],
            "usage": {
                "prompt_tokens": usage.get("prompt_eval_count", 0),
                "completion_tokens": usage.get("eval_count", 0),
                "total_tokens": usage.get("prompt_eval_count", 0) + usage.get("eval_count", 0)
            }
        }

        # 记录日志
        record_log(
            db,
            client_ip=request.remote_addr or "",
            virtual_model=model,
            actual_backend=node.url,
            actual_model=actual_model,
            status_code=200,
            duration_ms=duration_ms,
            prompt_tokens=openai_result["usage"]["prompt_tokens"],
            completion_tokens=openai_result["usage"]["completion_tokens"],
            stream=False,
            request_body=str(data)[:1000],
            response_preview=message.get("content", "")[:500]
        )

        return jsonify(openai_result)

    except http_requests.exceptions.RequestException as e:
        duration_ms = int((time.time() - start_time) * 1000)

        # 记录错误日志
        record_log(
            db,
            client_ip=request.remote_addr or "",
            virtual_model=model,
            actual_backend=node.url,
            actual_model=actual_model,
            status_code=502,
            duration_ms=duration_ms,
            stream=stream,
            error_message=str(e),
            request_body=str(data)[:1000]
        )

        raise BadGatewayError(f"后端服务错误: {str(e)}")
