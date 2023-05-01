import jinja_partials
from flask import Flask

from models import db
from routes import test
from config import Config

app = Flask(__name__)

if __name__ == "__main__":
    app.config.from_object(Config)
    app.register_blueprint(test)
    db.init_app(app)
    jinja_partials.register_extensions(app)
    app.run(debug=True)
