import uuid
import time
import logging
from typing import Optional
from urllib.parse import urlparse

import yt_dlp
import requests
import speech_recognition as sr
from bs4 import BeautifulSoup

import models as db
from services import files, audible
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


def clip_audio(source: db.Source, queue_item: db.Snippet, audio_filepath: str):
    start_time = queue_item.start_time
    end_time = queue_item.end_time

    # TODO This should be based on file type not on source
    if source.provider == db.SourceProvider.AUDIBLE:
        clip_path = files.clip_m4b_to_wav(audio_filepath, start_time, end_time)
    else:
        clip_path = files.clip_mp3_to_wav(audio_filepath, start_time, end_time)

    return clip_path


def process_snippet_task(queue_item: db.Snippet):
    queue_item.update_status(db.SnippetStatus.PROCESSING)

    # TODO Handle illegal queued urls
    source = db.Source.find_by_id(queue_item.source_id)
    if source.provider == db.SourceProvider.YOUTUBE:
        queue_item.update_status(db.SnippetStatus.DOWNLOADING)
        yt_info = download_youtube_data(queue_item)
        audio_filepath = yt_info["audio_filepath"]
        source.update_title(yt_info["title"])
        source.update_thumb_url(yt_info["thumbnail"])
    elif source.provider == db.SourceProvider.POCKETCASTS:
        queue_item.update_status(db.SnippetStatus.DOWNLOADING)
        pc_info = download_pocketcast_data(queue_item)
        audio_filepath = pc_info["audio_filepath"]
        source.update_title(pc_info["title"])
        source.update_thumb_url(pc_info["thumbnail"])
    elif source.provider == db.SourceProvider.AUDIBLE:
        # TODO Use this pattern for YouTube and PocketCast?
        queue_item.update_status(db.SnippetStatus.DOWNLOADING)
        audio_filepath = audible.download_audible_data(queue_item)
        # TODO If we don't get a filepath, we need to set status to ERROR

    if source and audio_filepath:
        clip_path = clip_audio(source, queue_item, audio_filepath)
        queue_item.update_status(db.SnippetStatus.TRANSCRIBING)
        text = whisper_recognize(clip_path)

        queue_item.update_text(text)
        queue_item.update_status(db.SnippetStatus.DONE)

    files.cleanup_tmp_files()


def download_youtube_data(queue_item: db.Snippet) -> Optional[dict]:
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

    url = queue_item.get_source_url()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        ydl.download([url])

    # TODO Might not always be mp3.
    info_dict["audio_filepath"] = f"{Config.TMP_DIRECTORY}/{filename}.mp3"
    info_dict["url"] = url
    return info_dict


def download_pocketcast_data(queue_item: db.Snippet):
    info_dict = {}
    url = queue_item.get_source_url()
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
        if queue_item := db.Snippet.get_next_in_queue():
            logging.info(f"Starting queue job {queue_item.id}")
            process_snippet_task(queue_item)
            logging.info(f"Queue job {queue_item.id} complete.")
