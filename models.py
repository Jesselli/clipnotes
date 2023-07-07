from __future__ import annotations
from typing_extensions import Self
import logging
import inspect
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from enum import Enum, unique

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy import and_
from werkzeug.security import check_password_hash

db = SQLAlchemy()
Session = scoped_session(sessionmaker())


def url_without_query(url):
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"


@unique
class SourceProvider(Enum):
    YOUTUBE = 1
    POCKETCASTS = 2
    AUDIBLE = 3


@unique
class SnippetStatus(Enum):
    QUEUED = 1
    PROCESSING = 2
    DOWNLOADING = 3
    TRANSCRIBING = 4
    DONE = 5


class BaseModel:
    __allow_unmapped__ = True

    def add_to_db(self):
        Session.add(self)
        Session.commit()

    def delete_from_db(self):
        Session.delete(self)
        Session.commit()

    @classmethod
    def find_by_id(cls, id) -> Self:
        return Session.query(cls).get(id)

    def __getattribute__(self, __name: str) -> Any:
        returned = object.__getattribute__(self, __name)
        if inspect.isfunction(returned) or inspect.ismethod(returned):
            logging.debug(f"Calling {__name} on {self}")
        return returned


@dataclass
class Snippet(db.Model, BaseModel):
    start_time: int

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey("source.id"), nullable=False)
    start_time = db.Column(db.Integer, nullable=False)
    end_time = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum(SnippetStatus), default=SnippetStatus.QUEUED)
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())
    text = db.Column(db.Text)

    def __repr__(self):
        return f"<Snippet {self.id} - {self.text}>"

    @staticmethod
    def add(user_id: int, source_id: int, start_time: int, end_time: int):
        existing = (
            Session.query(Snippet)
            .filter_by(
                user_id=user_id,
                source_id=source_id,
                start_time=start_time,
                end_time=end_time,
            )
            .first()
        )
        if existing:
            return existing

        snippet = Snippet(
            user_id=user_id,
            source_id=source_id,
            start_time=start_time,
            end_time=end_time,
        )
        snippet.add_to_db()
        return snippet

    def update_status(self, status: SnippetStatus):
        self.status = status
        Session.commit()

    def get_source_url(self):
        source = Source.find_by_id(self.source_id)
        return source.url

    def update_text(self, text):
        self.text = text
        Session.commit()

    @classmethod
    def get_snippets_since(cls, source_id, since):
        filter = and_(Snippet.source_id == source_id, Snippet.created_at > since)
        return Session.query(Snippet).filter(filter).all()

    @staticmethod
    def find_by_source_id_and_time(source_id, start_time, end_time):
        filter = and_(
            Snippet.source_id == source_id,
            Snippet.start_time == start_time,
            Snippet.end_time == end_time,
        )
        return Session.query(Snippet).filter(filter).first()

    @staticmethod
    def get_user_queue(user_id):
        filter = and_(
            Snippet.user_id == user_id,
            Snippet.status != SnippetStatus.DONE,
        )
        snippet_queue = (
            Session.query(Snippet).filter(filter).order_by(Snippet.created_at).all()
        )
        for snippet in snippet_queue:
            snippet.url = snippet.get_source_url()
        return snippet_queue

    @staticmethod
    def get_next_in_queue():
        # TODO Make MAX_CONCURRENT_JOBS configurable
        MAX_CONCURRENT_JOBS = 1
        filter = and_(
            Snippet.status != SnippetStatus.DONE,
            Snippet.status != SnippetStatus.QUEUED,
        )
        num_in_progress = Session.query(Snippet).filter(filter).count()
        if num_in_progress >= MAX_CONCURRENT_JOBS:
            return None

        return (
            Session.query(Snippet)
            .filter_by(status=SnippetStatus.QUEUED)
            .order_by(Snippet.created_at)
            .first()
        )


@dataclass
class Source(db.Model, BaseModel):
    provider: SourceProvider

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), nullable=False, unique=True)
    title = db.Column(db.String(255))
    snippets = db.relationship("Snippet", backref="source")
    thumb_url = db.Column(db.String(255))
    provider = db.Column(db.Enum(SourceProvider))

    def __repr__(self):
        return f"<Source {self.id} - {self.title}>"

    @staticmethod
    def add(url, provider: SourceProvider = None, title: str = None):
        url = url_without_query(url)
        existing = Session.query(Source).filter_by(url=url).first()
        if existing:
            return existing

        source = Source(url=url)
        source.provider = provider
        source.title = title
        parsed_url = urlparse(url)
        if provider is None:
            if parsed_url.hostname in ["www.youtube.com", "youtu.be"]:
                source.provider = SourceProvider.YOUTUBE
            elif parsed_url.hostname in ["pca.st"]:
                source.provider = SourceProvider.POCKETCASTS
        source.add_to_db()
        return source

    @classmethod
    def get_user_sources_snippets(cls, user_id):
        filter = and_(
            Snippet.user_id == user_id,
            Snippet.status == SnippetStatus.DONE,
        )
        sources = (
            Session.query(Source)
            .join(Snippet)
            .filter(filter)
            .order_by(Snippet.created_at.desc())
            .all()
        )
        for source in sources:
            source.snippets.sort(key=lambda x: x.start_time, reverse=False)
        return sources

    def update_title(self, title):
        self.title = title
        Session.commit()

    def update_thumb_url(self, thumb_url):
        self.thumb_url = thumb_url
        Session.commit()

    @staticmethod
    def find_snippet(user_id, url, start_time, end_time):
        url = url_without_query(url)
        filter = and_(
            Snippet.user_id == user_id,
            Snippet.source_id == Source.id,
            Snippet.start_time == start_time,
            Snippet.end_time == end_time,
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


@dataclass
class User(db.Model, UserMixin, BaseModel):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    snippets = db.relationship("Snippet", backref="user")
    devices = db.relationship("Device", backref="user")

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
