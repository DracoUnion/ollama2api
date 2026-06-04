"""请求模型定义"""

from urllib.parse import urlparse

from pydantic import BaseModel, Field, validator
from typing import Optional


class NodeCreateRequest(BaseModel):
    """创建节点请求"""
    url: str = Field(..., description="节点 URL")
    enabled: bool = Field(True, description="是否启用")

    @validator("url")
    def validate_url(cls, v):
        if not v or not v.strip():
            raise ValueError("URL 不能为空")
        try:
            result = urlparse(v.strip())
            if not all([result.scheme, result.netloc]):
                raise ValueError("URL 格式无效")
            if result.scheme not in ("http", "https"):
                raise ValueError("URL scheme 必须是 http 或 https")
        except ValueError:
            raise
        except Exception:
            raise ValueError("URL 格式无效")
        return v.strip()


class NodeUpdateRequest(BaseModel):
    """更新节点请求"""
    url: Optional[str] = Field(None, description="节点 URL")
    enabled: Optional[bool] = Field(None, description="是否启用")

    @validator("url")
    def validate_url(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError("URL 不能为空")
            try:
                result = urlparse(v.strip())
                if not all([result.scheme, result.netloc]):
                    raise ValueError("URL 格式无效")
                if result.scheme not in ("http", "https"):
                    raise ValueError("URL scheme 必须是 http 或 https")
            except ValueError:
                raise
            except Exception:
                raise ValueError("URL 格式无效")
            return v.strip()
        return v


class NodePullRequest(BaseModel):
    """拉取模型请求"""
    model_name: str = Field(..., description="模型名称")
    stream: bool = Field(False, description="是否流式返回")

    @validator("model_name")
    def validate_model_name(cls, v):
        if not v or not v.strip():
            raise ValueError("model_name 不能为空")
        return v.strip()
