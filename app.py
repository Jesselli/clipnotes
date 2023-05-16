from threading import Thread
import jinja_partials
from flask import Flask
from flask_cors import CORS
from flask_login import LoginManager
from sqlalchemy import create_engine

from models import db, Session, User
from routes import blueprint, api_blueprint
from config import Config
from services import source_processors

app = Flask(__name__)
CORS(app)


@app.cli.command("create_db")
def create_db():
    app.config.from_object(Config)
    db.init_app(app)
    db.create_all()


if __name__ == "__main__":
    queue_thread = Thread(target=source_processors.process_queue)
    queue_thread.daemon = True
    queue_thread.start()

    login_manager = LoginManager()
    login_manager.login_view = "test.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user):
        return User.get_by_id(int(user))

    engine = create_engine(f"{Config.SQLALCHEMY_DATABASE_URI}?check_same_thread=False")
    Session.configure(bind=engine)
    app.config.from_object(Config)
    app.register_blueprint(blueprint)
    app.register_blueprint(api_blueprint)
    db.init_app(app)
    jinja_partials.register_extensions(app)
    app.run(host="0.0.0.0", port=5001, debug=True)
