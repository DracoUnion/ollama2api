"""映射管理视图"""

from flask import Blueprint, request

from views.common import success
from models import Session, ModelMapping
from views.exceptions import BadRequestError, NotFoundError, ConflictError
from views.auth import require_auth
from views.reqs import MappingCreateRequest, MappingUpdateRequest

mapping_bp = Blueprint("mapping", __name__, url_prefix="/api/mapping")


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
    existing = db.query(ModelMapping).filter(ModelMapping.virtual_name == req.src_model).first()
    if existing:
        raise ConflictError(f"源模型 '{req.src_model}' 已存在映射")

    # 创建映射
    mapping = ModelMapping(
        virtual_name=req.src_model,
        actual_model_name=req.dst_model
    )

    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    return success(mapping.to_dict())


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

    query = db.query(ModelMapping)

    if keyword:
        query = query.filter(ModelMapping.virtual_name.ilike(f"%{keyword}%"))

    total = query.count()

    mappings = query.order_by(ModelMapping.virtual_name).offset((page - 1) * size).limit(size).all()

    items = [m.to_dict() for m in mappings]

    return success({
        "total": total,
        "page": page,
        "size": size,
        "items": items
    })


@mapping_bp.route("/<path:src_model>", methods=["GET"])
@require_auth
def get_mapping(src_model):
    """
    获取映射详情

    路径参数:
    - src_model: 源模型名（虚拟模型名）
    """
    db = Session()

    mapping = db.query(ModelMapping).filter(ModelMapping.virtual_name == src_model).first()
    if not mapping:
        raise NotFoundError("映射不存在")

    return success(mapping.to_dict())


@mapping_bp.route("/<path:src_model>", methods=["PUT"])
@require_auth
def update_mapping(src_model):
    """
    更新映射

    路径参数:
    - src_model: 源模型名（虚拟模型名）

    请求体:
    - dst_model: 目标模型名（实际模型名，必填）
    """
    data = request.get_json()
    if not data:
        raise BadRequestError("请求体必须是 JSON")

    req = MappingUpdateRequest(**data)

    db = Session()

    mapping = db.query(ModelMapping).filter(ModelMapping.virtual_name == src_model).first()
    if not mapping:
        raise NotFoundError("映射不存在")

    # 更新字段
    if req.dst_model is not None:
        mapping.actual_model_name = req.dst_model

    db.commit()
    db.refresh(mapping)

    return success(mapping.to_dict())


@mapping_bp.route("/<path:src_model>", methods=["DELETE"])
@require_auth
def delete_mapping(src_model):
    """
    删除映射

    路径参数:
    - src_model: 源模型名（虚拟模型名）
    """
    db = Session()

    mapping = db.query(ModelMapping).filter(ModelMapping.virtual_name == src_model).first()
    if not mapping:
        raise NotFoundError("映射不存在")

    db.delete(mapping)
    db.commit()

    return success(None)
