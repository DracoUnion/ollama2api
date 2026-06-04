import csv
import io
from datetime import datetime
from urllib.parse import urlparse

import requests
from flask import Blueprint, request, Response

from views.common import success, generate_node_id, call_ollama_tags
from models import Node, NodeModel, Session
from views.exceptions import (
    BadRequestError, NotFoundError, ConflictError,
    BadGatewayError, ServiceUnavailableError
)
from views.auth import require_auth
from views.reqs import NodeCreateRequest, NodeUpdateRequest, NodePullRequest

nodes_bp = Blueprint("nodes", __name__, url_prefix="/api/nodes")


# ==================== 视图函数 ====================

@nodes_bp.route("", methods=["GET"])
@require_auth
def list_nodes():
    """
    获取所有节点

    查询参数:
    - page: 页码（默认 1）
    - size: 每页条数（默认 20，最大 100）
    - enabled: 按启用状态筛选（true/false）
    - healthy: 按健康状态筛选（true/false）
    - keyword: 按 URL 模糊搜索
    """
    # 解析分页参数
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 20, type=int)
    page = max(1, page)
    size = min(max(1, size), 100)

    # 解析筛选参数
    enabled = request.args.get("enabled")
    healthy = request.args.get("healthy")
    keyword = request.args.get("keyword")

    db = Session()

    # 构建查询
    query = db.query(Node)

    # 筛选条件
    if enabled is not None:
        enabled_bool = enabled.lower() in ("true", "1")
        query = query.filter(Node.enabled == enabled_bool)

    if healthy is not None:
        healthy_bool = healthy.lower() in ("true", "1")
        query = query.filter(Node.healthy == healthy_bool)

    if keyword:
        query = query.filter(Node.url.ilike(f"%{keyword}%"))

    # 统计总数
    total = query.count()

    # 分页查询
    nodes = query.order_by(Node.created_at.desc()).offset((page - 1) * size).limit(size).all()

    # 构建响应
    items = [node.to_dict() for node in nodes]

    return success({
        "total": total,
        "page": page,
        "size": size,
        "items": items
    })


@nodes_bp.route("", methods=["POST"])
@require_auth
def create_node():
    """
    添加节点

    请求体:
    - url: 节点 URL（必填）
    - enabled: 是否启用（默认 true）
    """
    data = request.get_json()
    if not data:
        raise BadRequestError("请求体必须是 JSON")

    req = NodeCreateRequest(**data)

    db = Session()

    # 检查 URL 是否已存在
    existing = db.query(Node).filter(Node.url == req.url).first()
    if existing:
        raise ConflictError("URL 已存在")

    # 创建节点
    node = Node(
        id=generate_node_id(),
        url=req.url,
        enabled=req.enabled,
        healthy=False,
        created_at=datetime.now()
    )

    db.add(node)
    db.commit()
    db.refresh(node)

    return success(node.to_dict())


@nodes_bp.route("/<node_id>", methods=["PUT"])
@require_auth
def update_node(node_id):
    """
    更新节点

    请求体（所有字段可选）:
    - url: 节点 URL
    - enabled: 是否启用
    """
    data = request.get_json()
    if not data:
        raise BadRequestError("请求体必须是 JSON")

    req = NodeUpdateRequest(**data)

    db = Session()

    # 查询节点
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise NotFoundError("节点不存在")

    # 更新字段
    if req.url is not None:
        # 检查 URL 是否与其他节点冲突
        existing = db.query(Node).filter(Node.url == req.url, Node.id != node_id).first()
        if existing:
            raise ConflictError("URL 已被其他节点使用")
        node.url = req.url

    if req.enabled is not None:
        node.enabled = req.enabled

    db.commit()
    db.refresh(node)

    return success(node.to_dict())


@nodes_bp.route("/<node_id>", methods=["DELETE"])
@require_auth
def delete_node(node_id):
    """删除节点"""
    db = Session()

    # 查询节点
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise NotFoundError("节点不存在")

    # 删除节点（级联删除 node_models）
    db.delete(node)
    db.commit()

    return success(None)


@nodes_bp.route("/<node_id>/refresh", methods=["POST"])
@require_auth
def refresh_node_models(node_id):
    """
    刷新节点模型列表

    调用 Ollama 的 /api/tags 获取该节点当前可用模型，更新到 node_models 表。
    """
    db = Session()

    # 查询节点
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise NotFoundError("节点不存在")

    # 调用 Ollama /api/tags
    model_names = call_ollama_tags(node.url)

    # 删除旧的模型关联
    db.query(NodeModel).filter(NodeModel.node_id == node_id).delete()

    # 插入新的模型关联
    for model_name in model_names:
        node_model = NodeModel(node_id=node_id, model_name=model_name)
        db.add(node_model)

    # 更新节点健康状态和检查时间
    node.healthy = True
    node.last_health_check = datetime.now()

    db.commit()

    return success({"models": model_names})


@nodes_bp.route("/<node_id>/test", methods=["GET"])
@require_auth
def test_node(node_id):
    """
    测试节点连通性

    调用 Ollama 的 /api/tags 测试节点是否可达。
    """
    db = Session()

    # 查询节点
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise NotFoundError("节点不存在")

    # 调用 Ollama /api/tags
    model_names = call_ollama_tags(node.url, timeout=5)

    return success({"models": model_names})


@nodes_bp.route("/<node_id>/pull", methods=["POST"])
@require_auth
def pull_model(node_id):
    """
    拉取模型

    请求体:
    - model_name: 模型名称（必填）
    - stream: 是否流式返回（默认 false）
    """
    data = request.get_json()
    if not data:
        raise BadRequestError("请求体必须是 JSON")

    req = NodePullRequest(**data)

    db = Session()

    # 查询节点
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise NotFoundError("节点不存在")

    # 调用 Ollama /api/pull
    try:
        ollama_response = requests.post(
            f"{node.url}/api/pull",
            json={"name": req.model_name, "stream": req.stream},
            timeout=300,
            stream=req.stream
        )
        ollama_response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise ServiceUnavailableError("无法连接节点")
    except requests.exceptions.Timeout:
        raise ServiceUnavailableError("节点连接超时")
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                error_msg = error_data.get("error", str(e))
            except Exception:
                pass
        raise BadGatewayError(f"Ollama 错误: {error_msg}")

    # 流式返回
    if req.stream:
        def generate():
            for line in ollama_response.iter_lines():
                if line:
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        yield f"{line}\n\n"
                    else:
                        yield f"data: {line}\n\n"
            yield "data: [DONE]\n\n"

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
    return success({
        "model_name": req.model_name,
        "status": result.get("status", "success")
    })


@nodes_bp.route("/import", methods=["POST"])
@require_auth
def import_nodes():
    """
    CSV 批量导入节点

    表单字段:
    - file: CSV 文件（必填）
    - column: URL 列的名称（必填）
    - auto_refresh: 导入后是否自动刷新模型列表（默认 false）
    - enabled: 是否启用（默认 true）
    """
    # 检查文件
    if "file" not in request.files:
        raise BadRequestError("Missing file")

    file = request.files["file"]
    if not file.filename:
        raise BadRequestError("文件名为空")

    # 获取参数
    column = request.form.get("column")
    if not column:
        raise BadRequestError("Missing column")

    auto_refresh = request.form.get("auto_refresh", "false").lower() in ("true", "1")
    enabled = request.form.get("enabled", "true").lower() in ("true", "1")

    # 读取 CSV
    content = file.read().decode("utf-8")
    csv_reader = csv.DictReader(io.StringIO(content))

    # 检查列名是否存在
    if column not in csv_reader.fieldnames:
        raise BadRequestError(f"CSV 中不存在列 '{column}'")

    db = Session()

    # 统计数据
    total = 0
    created = 0
    skipped = 0
    errors = []

    # 遍历每一行
    for row_num, row in enumerate(csv_reader, start=2):
        total += 1
        url = row.get(column, "").strip()

        # URL 为空则跳过
        if not url:
            skipped += 1
            errors.append({"row": row_num, "reason": "URL 为空"})
            continue

        # URL 格式校验
        try:
            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                skipped += 1
                errors.append({"row": row_num, "reason": "URL 格式无效"})
                continue
        except Exception:
            skipped += 1
            errors.append({"row": row_num, "reason": "URL 格式无效"})
            continue

        # 检查 URL 是否已存在
        existing = db.query(Node).filter(Node.url == url).first()
        if existing:
            skipped += 1
            errors.append({"row": row_num, "reason": "URL already exists"})
            continue

        # 创建节点
        node_id = generate_node_id()
        node = Node(
            id=node_id,
            url=url,
            enabled=enabled,
            healthy=False,
            created_at=datetime.now()
        )
        db.add(node)
        created += 1

        # 自动刷新模型列表
        if auto_refresh:
            try:
                model_names = call_ollama_tags(url)
                for model_name in model_names:
                    node_model = NodeModel(node_id=node_id, model_name=model_name)
                    db.add(node_model)
                node.healthy = True
                node.last_health_check = datetime.now()
            except Exception:
                pass  # 刷新失败不影响导入

    # 提交事务
    db.commit()

    return success({
        "total": total,
        "created": created,
        "skipped": skipped,
        "errors": errors
    })
