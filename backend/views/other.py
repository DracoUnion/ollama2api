"""日志与仪表盘视图"""

from datetime import datetime, timedelta

from flask import Blueprint, request
from sqlalchemy import func

from views.common import success
from models import Session, RequestLog, Node, ModelMapping
from views.exceptions import BadRequestError
from views.auth import require_auth

other_bp = Blueprint("other", __name__)


# ==================== 日志管理 ====================

@other_bp.route("/api/logs", methods=["GET"])
@require_auth
def list_logs():
    """
    查询日志

    查询参数:
    - page: 页码（默认 1）
    - size: 每页条数（默认 20，最大 100）
    - model: 按虚拟模型名筛选
    - node_id: 按节点 ID 筛选
    - status: 按状态码筛选
    - start_time: 开始时间（ISO 格式）
    - end_time: 结束时间（ISO 格式）
    """
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 20, type=int)
    page = max(1, page)
    size = min(max(1, size), 100)

    model = request.args.get("model")
    node_id = request.args.get("node_id")
    status = request.args.get("status", type=int)
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")

    db = Session()

    query = db.query(RequestLog)

    # 筛选条件
    if model:
        query = query.filter(RequestLog.virtual_model.ilike(f"%{model}%"))
    if node_id:
        query = query.filter(RequestLog.actual_backend.ilike(f"%{node_id}%"))
    if status is not None:
        query = query.filter(RequestLog.status_code == status)
    if start_time:
        try:
            start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            query = query.filter(RequestLog.timestamp >= start)
        except ValueError:
            raise BadRequestError("start_time 格式无效")
    if end_time:
        try:
            end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            query = query.filter(RequestLog.timestamp <= end)
        except ValueError:
            raise BadRequestError("end_time 格式无效")

    # 统计总数
    total = query.count()

    # 统计 token 总数和平均耗时
    stats = query.with_entities(
        func.sum(RequestLog.prompt_tokens + RequestLog.completion_tokens).label("total_tokens"),
        func.avg(RequestLog.duration_ms).label("avg_duration")
    ).first()

    total_tokens = int(stats.total_tokens) if stats.total_tokens else 0
    avg_duration = round(float(stats.avg_duration), 2) if stats.avg_duration else 0

    # 分页查询
    logs = query.order_by(RequestLog.timestamp.desc()).offset((page - 1) * size).limit(size).all()

    items = [log.to_dict() for log in logs]

    return success({
        "total": total,
        "page": page,
        "size": size,
        "total_tokens": total_tokens,
        "avg_duration": avg_duration,
        "items": items
    })



# ==================== 统计摘要 ====================

@other_bp.route("/api/stats", methods=["GET"])
@require_auth
def stats_summary():
    """
    查询统计摘要

    查询参数:
    - start_time: 开始时间（可选，ISO 格式）
    - end_time: 结束时间（可选，ISO 格式）
    """
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")

    db = Session()

    query = db.query(RequestLog)

    # 时间范围筛选
    if start_time:
        try:
            start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            query = query.filter(RequestLog.timestamp >= start)
        except ValueError:
            raise BadRequestError("start_time 格式无效")
    if end_time:
        try:
            end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            query = query.filter(RequestLog.timestamp <= end)
        except ValueError:
            raise BadRequestError("end_time 格式无效")

    # 总请求数
    total_requests = query.count()

    # 成功请求数（2xx）
    success_requests = query.filter(
        RequestLog.status_code >= 200,
        RequestLog.status_code < 300
    ).count()

    # 失败请求数
    failed_requests = total_requests - success_requests

    # Token 总数和平均耗时
    stats = query.with_entities(
        func.sum(RequestLog.prompt_tokens + RequestLog.completion_tokens).label("total_tokens"),
        func.avg(RequestLog.duration_ms).label("avg_duration")
    ).first()

    total_tokens = int(stats.total_tokens) if stats.total_tokens else 0
    avg_duration = round(float(stats.avg_duration), 2) if stats.avg_duration else 0

    # 热门模型 Top 10
    top_models_query = db.query(
        RequestLog.virtual_model.label("model"),
        func.count().label("count")
    )

    # 应用相同的时间筛选
    if start_time:
        start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        top_models_query = top_models_query.filter(RequestLog.timestamp >= start)
    if end_time:
        end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        top_models_query = top_models_query.filter(RequestLog.timestamp <= end)

    top_models = top_models_query.group_by(
        RequestLog.virtual_model
    ).order_by(
        func.count().desc()
    ).limit(10).all()

    return success({
        "total_requests": total_requests,
        "success_requests": success_requests,
        "failed_requests": failed_requests,
        "total_tokens": total_tokens,
        "avg_duration": avg_duration,
        "top_models": [
            {"model": m.model, "count": m.count}
            for m in top_models
        ]
    })


