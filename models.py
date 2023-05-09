from dataclasses import dataclass

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy.orm import sessionmaker, scoped_session

db = SQLAlchemy()
Session = scoped_session(sessionmaker())


@dataclass
class Snippet(db.Model):
    id: int
    user_id: int
    source_id: int
    time: int
    duration: int
    created_at: str
    text: str

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey("source.id"), nullable=False)
    time = db.Column(db.Integer, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    text = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"<Snippet {self.id} - {self.text}>"


@dataclass
class Source(db.Model):
    id: int
    url: str
    title: str
    thumb_url: str
    provider: str
    snippets: list

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), nullable=False, unique=True)
    title = db.Column(db.String(255))
    snippets = db.relationship("Snippet", backref="source")
    thumb_url = db.Column(db.String(255))
    provider = db.Column(db.String(255))

    def __repr__(self):
        return f"<Source {self.id} - {self.title}>"

    @staticmethod
    def get_sources_and_snippets(user_id):
        sources = (
            Session
            .query(Source)
            .join(Snippet)
            .filter(Snippet.user_id == user_id)
            .order_by(Snippet.created_at.desc())
            .all()
        )
        for source in sources:
            source.snippets.sort(key=lambda x: x.time, reverse=False)
        return sources


@dataclass
class SyncRecord(db.Model):
    id: int
    user_id: int
    source_id: int
    synced_at: str

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey("source.id"), nullable=False)
    synced_at = db.Column(db.DateTime, default=db.func.now())


@dataclass
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    snippets = db.relationship("Snippet", backref="user")

    def __repr__(self):
        return f"<User {self.id} - {self.name}>"

    @staticmethod
    def create(email, password):
        user = User(email=email, password=password)
        Session.add(user)
        Session.commit()
        return user
    
    @staticmethod
    def get_by_email(email):
        return Session.query(User).filter_by(email=email).first()
    
    @staticmethod
    def get_by_id(user_id):
        return Session.query(User).get(user_id)
