import uuid
import time
import logging
from typing import Optional
from urllib.parse import urlparse

import yt_dlp
import requests
import speech_recognition as sr
from bs4 import BeautifulSoup

from models import Snippet, Source, SnippetQueue, QueueItemStatus
from services import files
from config import Config

r = sr.Recognizer()


def is_source_supported(source_url):
    parsed_url = urlparse(source_url)
    if parsed_url.hostname in ["www.youtube.com", "youtu.be"]:
        return True
    elif parsed_url.hostname in ["pca.st"]:
        return True
    else:
        return False


# TODO: Consider switching to just using whisper instead of speech_recognition
def whisper_recognize(clip):
    with sr.AudioFile(clip) as source:
        audio = r.record(source)
        text_whisper = r.recognize_whisper(audio)
    return text_whisper


def add_source(provider: str, **info: dict):
    if existing_source := Source.find_by_url(info["url"]):
        return existing_source
    else:
        source = Source(
            url=info["url"],
            title=info["title"],
            thumb_url=info["thumbnail"],
            provider=provider,
        )
        source.add_to_db()
        return source


def transcribe(queue_item: SnippetQueue, audio_filepath: str):
    time = queue_item.time
    duration = queue_item.duration

    clip_wav = files.create_wav_clip(
        audio_filepath,
        time,
        duration,
    )
    text = whisper_recognize(clip_wav)
    return text


def process_snippet_task(queue_item: SnippetQueue):
    queue_item.update_status(QueueItemStatus.PROCESSING)

    existing_snippet = Source.find_snippet(
        queue_item.url,
        queue_item.time,
        queue_item.duration,
    )
    if existing_snippet:
        logging.debug("Snippet already exists")
        queue_item.update_status(QueueItemStatus.DONE)
        # TODO: Need to check if THIS user has the snippet.
        # TODO: Also check if already queued

    # TODO Handle illegal queued urls
    parsed_url = urlparse(queue_item.url)
    if parsed_url.hostname in ["www.youtube.com", "youtu.be"]:
        queue_item.update_status(QueueItemStatus.DOWNLOADING)
        yt_info = download_youtube_data(queue_item)
        audio_filepath = yt_info["audio_filepath"]
        source = add_source("youtube", **yt_info)
    elif parsed_url.hostname in ["pca.st"]:
        queue_item.update_status(QueueItemStatus.DOWNLOADING)
        pc_info = download_pocketcast_data(queue_item)
        audio_filepath = pc_info["audio_filepath"]
        source = add_source("pocketcast", **pc_info)

    if source and audio_filepath:
        queue_item.update_status(QueueItemStatus.TRANSCRIBING)
        text = transcribe(queue_item, audio_filepath)

        # TODO Do we need Snippet and SnippetQueue?
        snippet = Snippet(
            source_id=source.id,
            user_id=queue_item.user_id,
            time=queue_item.time,
            duration=queue_item.duration,
            text=text,
        )
        snippet.add_to_db()
        queue_item.update_status(QueueItemStatus.DONE)

    files.cleanup_tmp_files()


def download_youtube_data(queue_item: SnippetQueue) -> Optional[dict]:
    # TODO Create table for queue item status? Or an enum?

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

    url = queue_item.url
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        ydl.download([url])

    # TODO Might not always be mp3.
    info_dict["audio_filepath"] = f"{Config.TMP_DIRECTORY}/{filename}.mp3"
    # TODO We should always use the base url and time/duration
    info_dict["url"] = url
    return info_dict


def download_pocketcast_data(queue_item: SnippetQueue):
    info_dict = {}
    url = queue_item.url
    info_dict["url"] = url

    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    download_button = soup.find("a", {"class": "download-button"})
    if not download_button:
        logging.error("No download button found.")
        return None

    download_link = download_button["href"]
    audio_filepath = files.download_file(download_link)
    info_dict["audio_filepath"] = audio_filepath

    title = soup.find("meta", {"property": "og:title"})["content"]
    info_dict["title"] = title

    thumb_url = soup.find("meta", {"property": "og:image"})["content"]
    info_dict["thumbnail"] = thumb_url

    return info_dict


def process_queue():
    while True:
        time.sleep(10)
        if queue_item := SnippetQueue.get_next_item():
            logging.info(f"Starting queue job {queue_item.id}")
            process_snippet_task(queue_item)
            logging.info(f"Queue job {queue_item.id} complete.")
