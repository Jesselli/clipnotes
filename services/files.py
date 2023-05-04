import os
from urllib.parse import urlparse

import requests
from pydub import AudioSegment

from config import Config


def download_file(url, directory=Config.TMP_DIRECTORY, filename=None):
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


def cleanup_tmp_files():
    for f in os.listdir(Config.TMP_DIRECTORY):
        os.remove(os.path.join(Config.TMP_DIRECTORY, f))
