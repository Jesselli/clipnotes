from threading import Thread

import jinja_partials
from flask import Flask
from flask_cors import CORS
from flask_login import LoginManager
from sqlalchemy import create_engine

from config import Config
from models import Session, User, db
from routes import api, main
from services import source_processors

app = Flask(__name__)
CORS(app)


@app.cli.command("create_db")
def create_db():
    app.config.from_object(Config)
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

    engine = create_engine(f"{Config.SQLALCHEMY_DATABASE_URI}?check_same_thread=False")
    Session.configure(bind=engine)
    app.config.from_object(Config)
    app.register_blueprint(main)
    app.register_blueprint(api)
    db.init_app(app)
    jinja_partials.register_extensions(app)
    return app


# TODO: Remove this eventually
if __name__ == "__main__":
    app = create_app()
    app.run("0.0.0.0", debug=True)
