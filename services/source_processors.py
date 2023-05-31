import re
import uuid
import time
import logging
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


def is_source_supported(source_url):
    parsed_url = urlparse(source_url)
    if parsed_url.hostname in ["www.youtube.com", "youtu.be"]:
        return True
    elif parsed_url.hostname in ["pca.st"]:
        return True
    else:
        return False


def get_time_from_url(url: str) -> int:
    parsed_url = urlparse(url)
    params = parse_qs(parsed_url.query)
    if "t" in params:
        time = params["t"][0]
        return int(time)

    fragment = parsed_url.fragment
    regex = r"t=(\d+[sm]?\d+[s]?)"
    time = re.search(regex, fragment)
    if time:
        time = time.group(1)
        return int(time)

    return 0


def get_seconds_from_time_str(time):
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


def get_url_without_query_params(url):
    parsed_url = urlparse(url)
    url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    return url


def add_source(url, title=None, thumbnail=None, provider=None):
    url = get_url_without_query_params(url)
    existing_source = Session.query(Source).filter_by(url=url).first()
    if existing_source:
        source = existing_source
    else:
        source = Source(url=url, title=title, thumb_url=thumbnail, provider=provider)
        source.add_to_db()
    return source


def add_snippet(audio_filepath, time, duration, source, user_id):
    clip_wav = files.create_wav_clip(audio_filepath, time, duration)
    text = whisper_recognize(clip_wav)
    snippet = Snippet(
        source_id=source.id, user_id=user_id, time=time, duration=duration, text=text
    )
    snippet.add_to_db()

    return text


def process_url(url, user_id, time, duration):
    title = None
    thumbnail_path = None
    parsed_url = urlparse(url)

    if not time:
        if url_time := get_time_from_url(url):
            time = url_time
        else:
            logging.warning("No time specified or found in url.")
            time = 0

    base_url = get_url_without_query_params(url)
    if Source.find_snippet(base_url, time, duration):
        logging.info("Snippet already exists. Skipping processing.")
        return

    logging.debug(f"Processing url {base_url} at time {time} for duration {duration}")
    if parsed_url.hostname in ["www.youtube.com", "youtu.be"]:
        source, audio_filepath = process_youtube_link(url)
    elif parsed_url.hostname in ["pca.st"]:
        source, audio_filepath = process_pocketcast_link(url)
    else:
        audio_filepath = files.download_file(url)
        source = add_source(url, title=title, thumbnail=thumbnail_path)

    if source and audio_filepath:
        add_snippet(audio_filepath, time, duration, source, user_id)
    files.cleanup_tmp_files()


def process_youtube_link(url):
    filename = uuid.uuid4()
    ydl_opts = {
        "format": "mp3/bestaudio/best",
        "outtmpl": f"{Config.TMP_DIRECTORY}/{filename}.%(ext)s",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }
        ],
        "writeinfojson": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        ydl.download([url])

    if not info_dict:
        logging.error("Could not extract info from youtube link.")
        # TODO This is not a good thing to return, probably
        return None, None

    title = info_dict.get("title", "")
    # TODO: Use subtitles if avaialble, instead of audio
    # TODO: Include option to use automatic_captions
    # TODO: Include tags if available
    # TODO: Include source name (Veritasium, Daily Stoic, etc.)
    audio_filepath = f"{Config.TMP_DIRECTORY}/{filename}.mp3"
    thumbnail = info_dict.get("thumbnail", "")
    source = add_source(url, title=title, thumbnail=thumbnail, provider="youtube")
    return source, audio_filepath


def process_pocketcast_link(url):
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    download_button = soup.find("a", {"class": "download-button"})
    if not download_button:
        logging.error("No download button found.")
        # TODO This is a bad thing to return
        return None, None

    download_link = download_button["href"]
    audio_filepath = files.download_file(download_link)

    title = soup.find("meta", {"property": "og:title"})["content"]
    thumb_url = soup.find("meta", {"property": "og:image"})["content"]

    source = add_source(url, title, thumb_url, "pocketcast")
    return source, audio_filepath


def process_queue():
    while True:
        time.sleep(1)
        if task := queue.get():
            logging.info("Starting queue job.")
            process_url(task["url"], task["user_id"], task["time"], task["duration"])
            queue.task_done()
            logging.info("Queue job complete.")


def add_to_queue(url, user_id, time, duration):
    logging.info(f"Adding {url} to queue")
    queue.put({"url": url, "user_id": user_id, "time": time, "duration": duration})


def add_batch_to_queue(tasks):
    for task in tasks:
        add_to_queue(task["url"], task["user_id"], task["time"], task["duration"])
