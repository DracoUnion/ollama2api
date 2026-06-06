# 数据库配置
DATABASE_URL = "sqlite:///be_dsn.db"

# 服务监听配置
HOST = "0.0.0.0"
PORT = 5000

# Flask 全局配置
DEBUG = True
API_KEY = ""
ADMIN_PASSWORD = '123456'
JSON_AS_ASCII = False  # 支持中文 JSON 响应
REQUEST_CONN_TIMEOUT = 3
REQUEST_READ_TIMEOUT = 600