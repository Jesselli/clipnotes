import os
import logging
from threading import Thread
import click

import jinja_partials
from flask import Flask
from flask_cors import CORS
from flask_login import LoginManager
from sqlalchemy import create_engine

from models import Session, User, db
from routes import api, main
from services import source_processors, audible

app = Flask(__name__)
CORS(app)


login_manager = LoginManager()
login_manager.login_view = "main.login"

# TODO Configurable logging level
log_format = "%(asctime)s %(levelname)s - %(message)s"
logging.basicConfig(
    filename="instance/clipnotes.log",
    format=log_format,
    level=logging.DEBUG,
)


def config_app():
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db_path = os.path.join(app.instance_path, "clipnotes.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"


def start_threads():
    queue_thread = Thread(target=source_processors.process_queue)
    queue_thread.daemon = True
    queue_thread.start()

    audible_thread = Thread(target=audible.sync_with_audible)
    audible_thread.daemon = True
    audible_thread.start()


@app.cli.command("create-db")
def create_db():
    config_app()
    db.init_app(app)
    db.create_all()


@app.cli.command("drop-db")
def drop_db():
    config_app()
    db.init_app(app)
    db.drop_all()


@app.cli.command("audible-auth")
@click.argument("email")
@click.argument("password")
def authenticate_audible(email: str, password: str):
    config_app()
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    engine = create_engine(
        f"{db_uri}?check_same_thread=False",
    )
    Session.configure(bind=engine)
    db.init_app(app)
    audible.save_audible_auth_to_file(email, password)


@login_manager.user_loader
def load_user(user):
    return User.get_by_id(int(user))


def create_app():
    login_manager.init_app(app)

    config_app()
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    engine = create_engine(
        f"{db_uri}?check_same_thread=False",
    )
    Session.configure(bind=engine)
    app.register_blueprint(main)
    app.register_blueprint(api)
    db.init_app(app)
    jinja_partials.register_extensions(app)

    start_threads()
    return app


if __name__ == "__main__":
    app = create_app()
    app.config["SECRET_KEY"] = "test"
    app.run("0.0.0.0", debug=True)
