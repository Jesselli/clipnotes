import re
import uuid
from queue import Queue
from urllib.parse import parse_qs, urlparse

import yt_dlp
import requests
import speech_recognition as sr
from bs4 import BeautifulSoup

from models import Snippet, Source, Session
from services import files
from config import Config

r = sr.Recognizer()
queue = Queue()


def get_time_from_url(url):
    parsed_url = urlparse(url)
    params = parse_qs(parsed_url.query)
    if "t" in params:
        time = params["t"][0]
        return time

    fragment = parsed_url.fragment
    regex = r"t=(\d+[sm]?\d+[s]?)"
    time = re.search(regex, fragment)
    if time:
        time = time.group(1)
        return time

    return 0


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


# TODO: Consider switching to just using whisper instead of speech_recognition
def whisper_recognize(clip):
    with sr.AudioFile(clip) as source:
        audio = r.record(source)
        text_whisper = r.recognize_whisper(audio)
    return text_whisper


def add_source(url, title=None, thumbnail=None, provider=None):
    parsed_url = urlparse(url)
    url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"

    existing_source = Session.query(Source).filter_by(url=url).first()
    if existing_source:
        source = existing_source
    else:
        source = Source(url=url, title=title, thumb_url=thumbnail, provider=provider)
        Session.add(source)
        Session.commit()
    return source


def add_snippet(audio_filepath, time, duration, source, user_id):
    seconds = get_seconds_from_time(time)
    clip_wav = files.create_wav_clip(audio_filepath, seconds, duration)
    text = whisper_recognize(clip_wav)
    snippet = Snippet(
        source_id=source.id, user_id=user_id, time=seconds, duration=duration, text=text
    )
    Session.add(snippet)
    Session.commit()

    return text


def process_url(url, user_id, time, duration):
    title = None
    thumbnail_path = None
    parsed_url = urlparse(url)
    if parsed_url.hostname in ["www.youtube.com", "youtu.be"]:
        source, audio_filepath, time = process_youtube_link(url)
    elif parsed_url.hostname in ["pca.st"]:
        source, audio_filepath, time = process_pocketcast_link(url)
    else:
        audio_filepath = files.download_file(url)
        source = add_source(url, title=title, thumbnail=thumbnail_path)

    add_snippet(audio_filepath, time, duration, source, user_id)
    files.cleanup_tmp_files()


def process_youtube_link(url):
    filename = uuid.uuid4()
    ydl_opts = {
        "format": "mp3/bestaudio/best",
        'outtmpl': f'{Config.TMP_DIRECTORY}/{filename}.%(ext)s',
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }
        ],
        'writeinfojson': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        ydl.download([url])

    title = info_dict.get("title", "")
    audio_filepath = f"{Config.TMP_DIRECTORY}/{filename}.mp3"
    thumbnail = info_dict.get("thumbnail", "")
    time = get_time_from_url(url)
    source = add_source(
        url, title=title, thumbnail=thumbnail, provider="youtube"
    )
    return source, audio_filepath, time


def process_pocketcast_link(url):
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    download_link = soup.find("a", {"class": "download-button"})["href"]
    audio_filepath = files.download_file(download_link)

    title = soup.find("meta", {"property": "og:title"})["content"]
    thumb_url = soup.find("meta", {"property": "og:image"})["content"]

    time = get_time_from_url(url)
    source = add_source(url, title, thumb_url, "pocketcast")
    return source, audio_filepath, time


def process_queue():
    while True:
        task = queue.get()
        if task:
            process_url(task["url"], task["user_id"], task["time"], task["duration"])
            queue.task_done()


def add_to_queue(url, user_id, time, duration):
    queue.put({"url": url, "user_id": user_id, "time": time, "duration": duration})