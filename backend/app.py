from flask import Flask
from . import config

app = Flask(__name__)
app.config.from_object(config)


@app.route("/")
def hello():
    return "Hello World"


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
