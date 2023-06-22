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

    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, filename)
    with open(filepath, "wb") as f:
        f.write(r.content)
    return filepath


def create_wav_clip(filepath, start_time, end_time):
    extension = filepath.split(".")[-1]
    podcast = AudioSegment.from_file(filepath, format=extension)
    start_ms = start_time * 1000
    end_ms = end_time * 1000
    clip = podcast[start_ms:end_ms]
    clip_wav = os.path.splitext(filepath)[0] + ".wav"
    clip.export(clip_wav, format="wav")
    return clip_wav


def cleanup_tmp_files():
    for f in os.listdir(Config.TMP_DIRECTORY):
        os.remove(os.path.join(Config.TMP_DIRECTORY, f))
