import jinja_partials
from flask import Flask

from models import db
from routes import test

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///snippets.sqlite3"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


if __name__ == "__main__":
    db.init_app(app)
    app.register_blueprint(test)
    jinja_partials.register_extensions(app)
    app.run(debug=True)
