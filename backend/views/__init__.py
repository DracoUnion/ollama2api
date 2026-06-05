"""视图模块"""

from .exceptions import (
    AppError,
    BadRequestError,
    UnauthorizedError,
    NotFoundError,
    ConflictError,
    ServerError,
    BadGatewayError,
    ServiceUnavailableError
)
from .error_handler import register_error_handlers
from .auth import check_auth, require_auth
from .common import success, error, generate_node_id, call_ollama_tags
from .reqs import (
    NodeCreateRequest, NodeUpdateRequest, NodePullRequest,
    MappingCreateRequest, MappingUpdateRequest,
    MappingListCreateRequest, MappingListUpdateRequest
)
from .nodes import nodes_bp
from .mapping import mapping_bp

__all__ = [
    "AppError",
    "BadRequestError",
    "UnauthorizedError",
    "NotFoundError",
    "ConflictError",
    "ServerError",
    "BadGatewayError",
    "ServiceUnavailableError",
    "register_error_handlers",
    "check_auth",
    "require_auth",
    "success",
    "error",
    "generate_node_id",
    "call_ollama_tags",
    "NodeCreateRequest",
    "NodeUpdateRequest",
    "NodePullRequest",
    "MappingCreateRequest",
    "MappingUpdateRequest",
    "MappingListCreateRequest",
    "MappingListUpdateRequest",
    "nodes_bp",
    "mapping_bp"
]
