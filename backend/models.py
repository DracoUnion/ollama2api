from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, UniqueConstraint, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

Base = declarative_base()


class Node(Base):
    """后端 Ollama 节点"""
    __tablename__ = "nodes"

    id = Column(String(64), primary_key=True, comment="节点ID，如 ep_xxx")
    url = Column(String(512), nullable=False, unique=True, comment="节点 URL")
    enabled = Column(Boolean, nullable=False, default=True, comment="是否启用")
    healthy = Column(Boolean, nullable=False, default=False, comment="是否健康")
    last_health_check = Column(DateTime, nullable=True, comment="最后健康检查时间")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")

    models = relationship("NodeModel", back_populates="node", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Node(id='{self.id}', url='{self.url}', healthy={self.healthy})>"

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "enabled": self.enabled,
            "healthy": self.healthy,
            "models": [m.model_name for m in self.models],
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class NodeModel(Base):
    """节点与模型的多对多关系"""
    __tablename__ = "node_models"

    node_id = Column(String(64), ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True, comment="节点ID")
    model_name = Column(String(255), primary_key=True, comment="模型名称")

    node = relationship("Node", back_populates="models")

    def __repr__(self):
        return f"<NodeModel(node_id='{self.node_id}', model_name='{self.model_name}')>"


class ModelMapping(Base):
    """虚拟模型名到实际模型名的映射"""
    __tablename__ = "model_mappings"

    virtual_name = Column(String(255), primary_key=True, comment="虚拟模型名")
    actual_model_name = Column(String(255), nullable=False, default="", comment="实际模型名")

    def __repr__(self):
        return f"<ModelMapping(virtual='{self.virtual_name}', actual='{self.actual_model_name}')>"

    def to_dict(self):
        return {
            "virtual_name": self.virtual_name,
            "actual_model_name": self.actual_model_name,
        }


class RequestLog(Base):
    """请求日志"""
    __tablename__ = "request_logs"

    id = Column(String(64), primary_key=True, comment="日志ID")
    timestamp = Column(DateTime, nullable=False, default=datetime.now, comment="请求时间")
    client_ip = Column(String(45), nullable=False, default="", comment="客户端IP")
    virtual_model = Column(String(255), nullable=False, default="", comment="虚拟模型名")
    actual_backend = Column(String(512), nullable=False, default="", comment="实际后端URL")
    actual_model = Column(String(255), nullable=False, default="", comment="实际模型名")
    status_code = Column(Integer, nullable=False, default=0, comment="HTTP状态码")
    duration_ms = Column(Integer, nullable=False, default=0, comment="请求耗时(ms)")
    prompt_tokens = Column(Integer, nullable=False, default=0, comment="提示词token数")
    completion_tokens = Column(Integer, nullable=False, default=0, comment="补全token数")
    stream = Column(Boolean, nullable=False, default=False, comment="是否流式")
    error_message = Column(Text, nullable=True, comment="错误信息")
    request_body = Column(Text, nullable=True, comment="请求体")
    response_preview = Column(Text, nullable=True, comment="响应预览")

    def __repr__(self):
        return f"<RequestLog(id='{self.id}', model='{self.virtual_model}', status={self.status_code})>"

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "client_ip": self.client_ip,
            "virtual_model": self.virtual_model,
            "actual_backend": self.actual_backend,
            "actual_model": self.actual_model,
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "stream": self.stream,
            "error_message": self.error_message,
        }


from config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
