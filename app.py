# import re
# from urllib.parse import parse_qs, urlparse

import jinja_partials
# import speech_recognition as sr
from flask import Flask

from models import db
# from services import files
from routes import test

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///snippets.sqlite3"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# r = sr.Recognizer()


# def get_seconds_from_time(time):
#     """
#     time: str
#         format: 1m30s or 90s or 90
#     """
#     if "m" in time:
#         minutes, seconds = time.split("m")
#     else:
#         minutes = 0
#         seconds = time
#     seconds = seconds.replace("s", "")
#     return int(minutes) * 60 + int(seconds)


# # TODO: Consider switching to just using whisper instead of speech_recognition
# def whisper_recognize(clip):
#     with sr.AudioFile(clip) as source:
#         audio = r.record(source)
#         text_whisper = r.recognize_whisper(audio)
#     return text_whisper


# def get_time_from_url(url):
#     parsed_url = urlparse(url)
#     params = parse_qs(parsed_url.query)
#     if "t" in params:
#         time = params["t"][0]
#         return time

#     fragment = parsed_url.fragment
#     regex = "t=(\d+[sm]?\d+[s]?)"
#     time = re.search(regex, fragment)
#     if time:
#         time = time.group(1)
#         return time

#     return 0


# def add_source(url, title=None, thumbnail=None, provider=None):
#     parsed_url = urlparse(url)
#     url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"

#     existing_source = Source.query.filter_by(url=url).first()
#     if existing_source:
#         source = existing_source
#     else:
#         source = Source(url=url, title=title, thumb_url=thumbnail, provider=provider)
#         db.session.add(source)
#         db.session.commit()
#     return source


# def add_snippet(audio_filepath, time, duration, source, user_id):
#     seconds = get_seconds_from_time(time)
#     clip_wav = files.create_wav_clip(audio_filepath, seconds, duration)
#     text = whisper_recognize(clip_wav)
#     snippet = Snippet(
#         source_id=source.id, user_id=user_id, time=seconds, duration=duration, text=text
#     )
#     db.session.add(snippet)
#     db.session.commit()

#     return text


# def process_source_url(url, user_id, time, duration):
#     title = None
#     thumbnail_path = None
#     parsed_url = urlparse(url)
#     if parsed_url.hostname in ["www.youtube.com", "youtu.be"]:
#         source, audio_filepath, time = process_youtube_link(url)
#     elif parsed_url.hostname in ["pca.st"]:
#         source, audio_filepath, time = process_pocketcast_link(url)
#     else:
#         audio_filepath = files.download_file(url)
#         source = add_source(url, title=title, thumbnail=thumbnail_path)

#     add_snippet(audio_filepath, time, duration, source, user_id)
#     return render_template("partials/sources.html", sources=get_sources(1))


# def get_sources(user_id):
#     sources = (
#         db.session()
#         .query(Source)
#         .join(Snippet)
#         .order_by(Snippet.created_at.desc())
#         .all()
#     )
#     for source in sources:
#         source.snippets.sort(key=lambda x: x.time, reverse=False)
#     return sources


if __name__ == "__main__":
    db.init_app(app)
    app.register_blueprint(test)
    jinja_partials.register_extensions(app)
    app.run(debug=True)
