from flask import Flask
import config
from views.error_handler import register_error_handlers
from views.nodes import nodes_bp

app = Flask(__name__)
app.config.from_object(config)

# 注册异常处理器
register_error_handlers(app)

# 注册蓝图
app.register_blueprint(nodes_bp)


@app.route("/")
def hello():
    return "Hello World"


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
