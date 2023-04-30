import re
import os
from urllib.parse import urlparse, parse_qs

import pytube
import requests
import speech_recognition as sr
import jinja_partials
from flask import Flask, request, render_template
from pydub import AudioSegment
from flask_sqlalchemy import SQLAlchemy
from bs4 import BeautifulSoup

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///snippets.sqlite3"
db = SQLAlchemy(app)
r = sr.Recognizer()


class Snippet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    source_id = db.Column(db.Integer, db.ForeignKey("source.id"), nullable=False)
    time = db.Column(db.Integer, nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    text = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"<Snippet {self.id} - {self.text}>"


class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), nullable=False, unique=True)
    title = db.Column(db.String(255))
    snippets = db.relationship("Snippet", backref="source")
    thumb_url = db.Column(db.String(255))
    provider = db.Column(db.String(255))

    def __repr__(self):
        return f"<Source {self.id} - {self.title}>"


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(255))
    last_name = db.Column(db.String(255))
    email = db.Column(db.String(255), unique=True)
    snippets = db.relationship("Snippet", backref="user")

    def __repr__(self):
        return f"<User {self.id} - {self.name}>"


def delete_oldest_file(size_threshold=100 * 1000 * 1000, dir="./tmp"):
    directory_size = sum(os.path.getsize(os.path.join(dir, f)) for f in os.listdir(dir))

    if directory_size < size_threshold:
        return

    files = os.listdir(dir)
    oldest_file = min(files, key=os.path.getctime)
    os.remove(os.path.join(dir, oldest_file))


def download_file(url, directory="./tmp", filename=None):
    delete_oldest_file()

    r = requests.get(url)
    parsed_url = urlparse(url)

    if not filename:
        filename = parsed_url.path.split("/")[-1]
    else:
        filename = filename + "." + parsed_url.path.split(".")[-1]

    filepath = os.path.join(directory, filename)
    with open(filepath, "wb") as f:
        f.write(r.content)
    return filepath


def get_seconds_from_time(time):
    """
    time: str
        format: 1m30s or 90s or 90
    """
    if "m" in time:
        minutes, seconds = time.split("m")
    else:
        minutes = 0
        seconds = time
    seconds = seconds.replace("s", "")
    return int(minutes) * 60 + int(seconds)


def create_wav_clip(filepath, seconds_location, duration):
    extension = filepath.split(".")[-1]
    podcast = AudioSegment.from_file(filepath, format=extension)
    start_ms = (seconds_location - (duration // 2)) * 1000
    if start_ms < 0:
        start_ms = 0

    end_ms = (seconds_location + (duration // 2)) * 1000
    if end_ms > len(podcast):
        end_ms = len(podcast)

    clip = podcast[start_ms:end_ms]
    clip_wav = os.path.splitext(filepath)[0] + ".wav"
    clip.export(clip_wav, format="wav")
    return clip_wav


# TODO: Consider switching to just using whisper instead of speech_recognition
def whisper_recognize(clip):
    with sr.AudioFile(clip) as source:
        audio = r.record(source)
        text_whisper = r.recognize_whisper(audio)
    return text_whisper


def get_time_from_url(url):
    parsed_url = urlparse(url)
    params = parse_qs(parsed_url.query)
    if "t" in params:
        time = params["t"][0]
        return time

    fragment = parsed_url.fragment
    regex = "t=(\d+[sm]?\d+[s]?)"
    time = re.search(regex, fragment)
    if time:
        time = time.group(1)
        return time

    return 0


def process_youtube_link(url):
    yt = pytube.YouTube(url, use_oauth=True, allow_oauth_cache=True)
    audio_stream = yt.streams.filter(only_audio=True).first()
    audio_stream.download(output_path="./tmp", filename=audio_stream.default_filename)
    audio_filepath = os.path.join("./tmp", audio_stream.default_filename)
    title = yt.title

    time = get_time_from_url(url)
    source = add_db_source(
        url, title=title, thumbnail=yt.thumbnail_url, provider="youtube"
    )
    return source, audio_filepath, time


def process_pocketcast_link(url):
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    download_link = soup.find("a", {"class": "download-button"})["href"]
    audio_filepath = download_file(download_link)

    title = soup.find("meta", {"property": "og:title"})["content"]
    thumb_url = soup.find("meta", {"property": "og:image"})["content"]

    time = get_time_from_url(url)
    source = add_db_source(url, title, thumb_url, "pocketcast")
    return source, audio_filepath, time


def add_db_source(url, title=None, thumbnail=None, provider=None):
    parsed_url = urlparse(url)
    url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"

    existing_source = Source.query.filter_by(url=url).first()
    if existing_source:
        source = existing_source
    else:
        source = Source(url=url, title=title, thumb_url=thumbnail, provider=provider)
        db.session.add(source)
        db.session.commit()
    return source


def add_snippet(audio_filepath, time, duration, source, user_id):
    seconds = get_seconds_from_time(time)
    clip_wav = create_wav_clip(audio_filepath, seconds, duration)
    text = whisper_recognize(clip_wav)
    snippet = Snippet(
        source_id=source.id, user_id=user_id, time=seconds, duration=duration, text=text
    )
    db.session.add(snippet)
    db.session.commit()

    return text


def create_snippet(url, user_id, time, duration):
    title = None
    thumbnail_path = None
    parsed_url = urlparse(url)
    if parsed_url.hostname in ["www.youtube.com", "youtu.be"]:
        source, audio_filepath, time = process_youtube_link(url)
    elif parsed_url.hostname in ["pca.st"]:
        source, audio_filepath, time = process_pocketcast_link(url)
    else:
        audio_filepath = download_file(url)
        source = add_db_source(url, title=title, thumbnail=thumbnail_path)

    add_snippet(audio_filepath, time, duration, source, user_id)
    return render_template("partials/snippet_list.html", sources=get_sources(1))


def get_sources(user_id):
    sources = (
        db.session()
        .query(Source)
        .join(Snippet)
        .order_by(Snippet.created_at.desc())
        .all()
    )
    for source in sources:
        source.snippets.sort(key=lambda x: x.time, reverse=False)
    return sources


def get_snippets(user_id):
    sources = get_sources(user_id)
    return render_template("index.html", sources=sources)


@app.route("/")
def index():
    # TODO Add support for multiple users
    user_id = 1
    sources = get_sources(user_id)
    return render_template("index.html", sources=sources)


@app.route("/source/<int:source_id>/markdown", methods=["GET"])
def source_to_markdown(source_id):
    source = Source.query.get(source_id)
    snippets = Snippet.query.filter_by(source_id=source_id).all()
    md = f"# {source.title}\n\n"
    md += f"![thumbnail]({source.thumb_url})\n\n"
    md += f"[{source.title}]({source.url})\n\n"
    for snippet in snippets:
        md += f"{snippet.text.lstrip()} [{snippet.time}]({source.url}?t={snippet.time})\n\n"
    return md


@app.route("/source/<int:source_id>", methods=["DELETE"])
def delete_source(source_id):
    snippets = Snippet.query.filter_by(source_id=source_id).all()
    for snippet in snippets:
        db.session.delete(snippet)
    source = Source.query.get(source_id)
    db.session.delete(source)
    db.session.commit()
    return "<div/>"


@app.route("/snippets", methods=["GET", "POST"])
def snippets():
    if request.method == "POST":
        if request.form:
            url = request.form.get("url")
            duration = request.form.get("duration", 60, type=int)
            time = request.form.get("time", 0)
            user_id = 1
            return create_snippet(url, user_id, time, duration)
        else:
            url = request.args.get("url")
            time = request.args.get("time")
            duration = request.args.get("duration", 60, type=int)
            user_id = 1
            return create_snippet(url, user_id, time, duration)


@app.route("/snippet/<int:snippet_id>", methods=["GET", "PUT", "DELETE"])
def test(snippet_id):
    if request.method == "PUT":
        text = request.form.get("text")
        Snippet.query.filter_by(id=snippet_id).update({"text": text})
        db.session.commit()
        return text
    elif request.method == "DELETE":
        Snippet.query.filter_by(id=snippet_id).delete()
        db.session.commit()
        return "<div/>"


if __name__ == "__main__":
    jinja_partials.register_extensions(app)
    app.run(debug=True)
