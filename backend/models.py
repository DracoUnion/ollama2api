from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class BeDsn(Base):
    __tablename__ = "be_dsn"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    host = Column(String(255), nullable=False, default="", comment="主机地址")
    link = Column(String(255), nullable=False, default="", comment="链接")
    domain = Column(String(255), nullable=False, default="", comment="域名")
    title = Column(String(255), nullable=False, default="", comment="标题")
    ip = Column(String(45), nullable=False, default="", comment="IP地址")
    port = Column(Integer, nullable=False, default=0, comment="端口号")
    country = Column(String(50), nullable=False, default="", comment="国家")
    created_at = Column(
        DateTime, nullable=False, default=datetime.now, comment="创建时间"
    )
    updated_at = Column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    def __repr__(self):
        return f"<BeDsn(id={self.id}, host='{self.host}', domain='{self.domain}')>"

    def to_dict(self):
        return {
            "id": self.id,
            "host": self.host,
            "link": self.link,
            "domain": self.domain,
            "title": self.title,
            "ip": self.ip,
            "port": self.port,
            "country": self.country,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


from .config import DATABASE_URL

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
