import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy import and_
from werkzeug.security import check_password_hash

from services import time_str

db = SQLAlchemy()
Session = scoped_session(sessionmaker())


def url_without_query(url):
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"


class BaseModel:
    __allow_unmapped__ = True

    def add_to_db(self):
        Session.add(self)
        Session.commit()

    def delete_from_db(self):
        Session.delete(self)
        Session.commit()

    @classmethod
    def find_by_id(cls, id):
        return Session.query(cls).get(id)


@dataclass
class Snippet(db.Model, BaseModel):
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
    time = db.Column(db.Integer, nullable=False, default=0)
    duration = db.Column(db.Integer, nullable=False, default=60)
    created_at = db.Column(db.DateTime, default=db.func.now())
    text = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"<Snippet {self.id} - {self.text}>"

    @classmethod
    def get_snippets_since(cls, source_id, since):
        filter = and_(Snippet.source_id == source_id, Snippet.created_at > since)
        return Session.query(Snippet).filter(filter).all()

    def update_text_in_db(self, text):
        self.text = text
        Session.commit()


@dataclass
class Source(db.Model, BaseModel):
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

    def __init__(self, url, title, thumb_url, provider):
        url = url_without_query(url)
        self.url = url
        self.title = title
        self.thumb_url = thumb_url
        self.provider = provider

    def __repr__(self):
        return f"<Source {self.id} - {self.title}>"

    @classmethod
    def get_user_sources_snippets(cls, user_id):
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

    @classmethod
    def find_snippet(cls, url, time, duration):
        url = url_without_query(url)
        filter = and_(
            Snippet.source_id == Source.id,
            Snippet.time == time,
            Snippet.duration == duration,
        )
        return Session.query(Source).filter_by(url=url).filter(filter).first()

    @staticmethod
    def find_by_url(url):
        url = url_without_query(url)
        return Session.query(Source).filter_by(url=url).first()


@dataclass
class SyncRecord(db.Model, BaseModel):
    id: int
    user_id: int
    source_id: int
    synced_at: str

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey("source.id"), nullable=False)
    synced_at = db.Column(db.DateTime, default=db.func.now())

    @classmethod
    def get_user_sync_record(cls, source_id, user_id):
        sync_record = (
            Session.query(SyncRecord)
            .filter_by(user_id=user_id, source_id=source_id)
            .order_by(SyncRecord.synced_at.desc())
            .first()
        )
        return sync_record

    @classmethod
    def find_by_user_source(cls, user_id, source_id):
        return (
            Session.query(SyncRecord)
            .filter_by(user_id=user_id, source_id=source_id)
            .first()
        )

    def update_sync_time(self, time=db.func.now()):
        self.synced_at = time
        Session.commit()


class ExternalSyncRecord(db.Model, BaseModel):
    id: int
    user_id: int
    service: str
    synced_at: str

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    service = db.Column(db.String(255), nullable=False)
    synced_at = db.Column(db.DateTime, default=db.func.now())

    def update_sync_time(self, time=db.func.now()):
        self.synced_at = time
        Session.commit()

    @classmethod
    def find_by_user_service(cls, user_id, service):
        record = (
            Session.query(ExternalSyncRecord)
            .filter_by(user_id=user_id, service=service)
            .first()
        )
        return record

    @staticmethod
    def get_readwise_sync_record(user_id):
        return ExternalSyncRecord.find_by_user_service(user_id, "readwise")

    @staticmethod
    def add_readwise_sync_record(user_id):
        sync_record = ExternalSyncRecord(user_id=user_id, service="readwise")
        sync_record.add_to_db()

    @staticmethod
    def update_readwise_sync_record(user_id):
        sync_record = ExternalSyncRecord.find_by_user_service(user_id, "readwise")
        sync_record.update_sync_time()


@dataclass
class User(db.Model, UserMixin, BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    snippets = db.relationship("Snippet", backref="user")
    devices = db.relationship("Device", backref="user")

    def __repr__(self):
        return f"<User {self.id} - {self.name}>"

    @classmethod
    def get_all(cls):
        return Session.query(User).all()

    @classmethod
    def create(cls, email, password):
        user = User(email=email, password=password)
        Session.add(user)
        Session.commit()
        return user

    @classmethod
    def find_by_email(cls, email):
        return Session.query(User).filter_by(email=email).first()

    @classmethod
    def get_by_id(cls, user_id):
        return Session.query(User).get(user_id)


class UserSettings(db.Model, BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    value = db.Column(db.String(80), nullable=False)

    @staticmethod
    def create(user_id, setting_name, value):
        setting = UserSettings(user_id=user_id, name=setting_name, value=value)
        setting.add_to_db()

    @staticmethod
    def find_by_user_id(user_id):
        return Session.query(UserSettings).filter_by(user_id=user_id).all()

    @staticmethod
    def find(user_id, setting_name):
        return (
            Session.query(UserSettings)
            .filter_by(user_id=user_id, name=setting_name)
            .first()
        )

    @staticmethod
    def find_all(user_id, setting_name):
        return (
            Session.query(UserSettings)
            .filter_by(user_id=user_id, name=setting_name)
            .all()
        )

    @staticmethod
    def delete(user_id, setting_name):
        Session.query(UserSettings).filter_by(
            user_id=user_id, name=setting_name
        ).delete()
        Session.commit()

    def update_value(self, value):
        self.value = value
        Session.commit()


class Device(db.Model, BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    device_name = db.Column(db.String(80), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    device_key = db.Column(db.String(80), nullable=False)
    last_four = db.Column(db.String(4), nullable=False)

    @staticmethod
    def find_by_name(user_id, device_name):
        return (
            Session.query(Device)
            .filter_by(user_id=user_id, device_name=device_name)
            .first()
        )

    @classmethod
    def find_devices_for_user(cls, user_id):
        return Session.query(Device).filter_by(user_id=user_id).all()

    @staticmethod
    def find_by_key(device_key):
        # TODO With a ton of devices, this will not be efficient
        devices = Session.query(Device).all()
        for device in devices:
            if check_password_hash(device.device_key, device_key):
                return device
        return None


class SnippetQueue(db.Model, BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    time = db.Column(db.Integer, nullable=False, default=0)
    duration = db.Column(db.Integer, nullable=False, default=60)
    status = db.Column(db.String(255), default="queued")
    created_at = db.Column(db.DateTime, default=db.func.now())

    @staticmethod
    def add(user_id, url, time, duration):
        logging.debug(f"Adding snippet to queue: {url}")

        if (time is None) and (url_time := time_str.get_time_from_url(url)):
            time = url_time

        snippet = SnippetQueue(
            user_id=user_id,
            url=url,
            time=time,
            duration=duration,
        )
        snippet.add_to_db()

    @staticmethod
    def get_next_item():
        return (
            Session.query(SnippetQueue)
            .filter_by(status="queued")
            .order_by(SnippetQueue.created_at)
            .first()
        )

    def update_status(self, status):
        self.status = status
        Session.commit()
