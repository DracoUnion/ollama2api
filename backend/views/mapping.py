"""映射管理视图"""

import uuid
from datetime import datetime

import requests
from flask import Blueprint, request, Response

from views.common import success
from models import Session, Mapping, Node, NodeModel
from views.exceptions import (
    BadRequestError, NotFoundError, ConflictError,
    BadGatewayError
)
from views.auth import require_auth
from views.reqs import (
    MappingCreateRequest, MappingUpdateRequest,
    MappingListCreateRequest, MappingListUpdateRequest
)

mapping_bp = Blueprint("mapping", __name__, url_prefix="/api/mapping")

# SSE 客户端列表
sse_clients = []


def generate_mapping_id() -> str:
    """生成映射 ID"""
    return f"mp_{uuid.uuid4().hex[:8]}"


def generate_list_id() -> str:
    """生成列表项 ID"""
    return f"ml_{uuid.uuid4().hex[:8]}"




# ==================== SSE 同步端点 ====================



# ==================== 映射 CRUD ====================

@mapping_bp.route("", methods=["POST"])
@require_auth
def create_mapping():
    """
    创建映射

    请求体:
    - src_model: 源模型名（虚拟模型名，必填）
    - dst_model: 目标模型名（实际模型名，必填）
    """
    data = request.get_json()
    if not data:
        raise BadRequestError("请求体必须是 JSON")

    req = MappingCreateRequest(**data)

    db = Session()

    # 检查 src_model 是否已存在
    existing = db.query(Mapping).filter(Mapping.src_model == req.src_model).first()
    if existing:
        raise ConflictError(f"源模型 '{req.src_model}' 已存在映射")

    # 创建映射
    mapping = Mapping(
        id=generate_mapping_id(),
        src_model=req.src_model,
        dst_model=req.dst_model,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )

    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    result = mapping.to_dict()

    return success(result)


@mapping_bp.route("", methods=["GET"])
@require_auth
def list_mappings():
    """
    查询映射列表

    查询参数:
    - page: 页码（默认 1）
    - size: 每页条数（默认 20，最大 100）
    - keyword: 按 src_model 模糊搜索
    """
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 20, type=int)
    page = max(1, page)
    size = min(max(1, size), 100)

    keyword = request.args.get("keyword")

    db = Session()

    query = db.query(Mapping)

    if keyword:
        query = query.filter(Mapping.src_model.ilike(f"%{keyword}%"))

    total = query.count()

    mappings = query.order_by(Mapping.created_at.desc()).offset((page - 1) * size).limit(size).all()

    items = [m.to_dict() for m in mappings]

    return success({
        "total": total,
        "page": page,
        "size": size,
        "items": items
    })


@mapping_bp.route("/<mapping_id>", methods=["GET"])
@require_auth
def get_mapping(mapping_id):
    """
    获取映射详情

    路径参数:
    - mapping_id: 映射 ID
    """
    db = Session()

    mapping = db.query(Mapping).filter(Mapping.id == mapping_id).first()
    if not mapping:
        raise NotFoundError("映射不存在")

    return success(mapping.to_dict())



@mapping_bp.route("/<mapping_id>", methods=["DELETE"])
@require_auth
def delete_mapping(mapping_id):
    """
    删除映射

    路径参数:
    - mapping_id: 映射 ID
    """
    db = Session()

    mapping = db.query(Mapping).filter(Mapping.id == mapping_id).first()
    if not mapping:
        raise NotFoundError("映射不存在")

    db.delete(mapping)
    db.commit()

    return success(None)

