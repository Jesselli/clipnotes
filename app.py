import os
from threading import Thread

import jinja_partials
from flask import Flask
from flask_cors import CORS
from flask_login import LoginManager
from sqlalchemy import create_engine

from models import Session, User, db
from routes import api, main
from services import source_processors

app = Flask(__name__)
CORS(app)


def config_app():
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db_path = os.path.join(app.instance_path, "snippets.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"


@app.cli.command("create-db")
def create_db():
    config_app()
    db.init_app(app)
    db.create_all()


def create_app():
    queue_thread = Thread(target=source_processors.process_queue)
    queue_thread.daemon = True
    queue_thread.start()

    login_manager = LoginManager()
    login_manager.login_view = "main.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user):
        return User.get_by_id(int(user))

    config_app()
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    engine = create_engine(f"{db_uri}?check_same_thread=False")
    Session.configure(bind=engine)
    app.register_blueprint(main)
    app.register_blueprint(api)
    db.init_app(app)
    jinja_partials.register_extensions(app)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run("0.0.0.0", debug=True)
