from threading import Thread
import jinja_partials
from flask import Flask
from flask_cors import CORS
from sqlalchemy import create_engine

from models import db, Session
from routes import blueprint
from config import Config
from services import source_processors

app = Flask(__name__)
CORS(app)

if __name__ == "__main__":
    queue_thread = Thread(target=source_processors.process_queue)
    queue_thread.daemon = True
    queue_thread.start()

    engine = create_engine(f"{Config.SQLALCHEMY_DATABASE_URI}?check_same_thread=False")
    Session.configure(bind=engine)
    app.config.from_object(Config)
    app.register_blueprint(blueprint)
    db.init_app(app)
    jinja_partials.register_extensions(app)
    app.run(host="0.0.0.0", port=5001)
