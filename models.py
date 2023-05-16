import uuid

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

    # TODO Be consistent -- we should probably just use normal methods instead of classmethods
    @classmethod
    def update_text_in_db(cls, snippet_id, text):
        Session.query(Snippet).filter_by(id=snippet_id).update({"text": text})
        Session.commit()

    @classmethod
    def delete_from_db(cls, snippet_id):
        Session.query(Snippet).filter_by(id=snippet_id).delete()
        Session.commit()

    # TODO Be consistent -- add_to_db or _save_to_db?
    def add_to_db(self):
        Session.add(self)
        Session.commit()


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

    @classmethod
    def get_sources_and_snippets(cls, user_id):
        sources = (
            Session.query(Source)
            .join(Snippet)
            .filter(Snippet.user_id == user_id)
            .order_by(Snippet.created_at.desc())
            .all()
        )
        for source in sources:
            source.snippets.sort(key=lambda x: x.time, reverse=False)
        return sources

    def delete_from_db(self):
        Session.delete(self)
        Session.commit()

    def add_to_db(self):
        Session.add(self)
        Session.commit()


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

    def add_to_db(self):
        Session.add(self)
        Session.commit()

    @classmethod
    def get_user_sync_record(cls, source_id, user_id):
        sync_record = (
            Session.query(SyncRecord)
            .filter_by(user_id=user_id, source_id=source_id)
            .order_by(SyncRecord.synced_at.desc())
            .first()
        )
        return sync_record

@dataclass
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    snippets = db.relationship("Snippet", backref="user")
    devices = db.relationship("Device", backref="user")

    def __repr__(self):
        return f"<User {self.id} - {self.name}>"

    @classmethod
    def create(cls, email, password):
        user = User(email=email, password=password)
        Session.add(user)
        Session.commit()
        return user

    @classmethod
    def get_by_email(cls, email):
        return Session.query(User).filter_by(email=email).first()

    @classmethod
    def get_by_id(cls, user_id):
        return Session.query(User).get(user_id)


class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_name = db.Column(db.String(80), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    device_key = db.Column(db.String(80), default=uuid.uuid4().hex)

    @classmethod
    def find_by_name(cls, device_name):
        return Session.query(Device).filter_by(device_name=device_name).first()

    @classmethod
    def find_devices_for_user(cls, user_id):
        return Session.query(Device).filter_by(user_id=user_id).all()

    @classmethod
    def find_by_key(cls, device_key):
        return Session.query(Device).filter_by(device_key=device_key).first()

    # TODO Move these out to a parent class for all models?
    def save_to_db(self):
        Session.add(self)
        Session.commit()

    def delete_from_db(self):
        Session.delete(self)
        Session.commit()
