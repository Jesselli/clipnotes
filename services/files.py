import os
import pathlib
import subprocess
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


def clip_m4b_to_wav(filepath, start_time, end_time):
    start_seconds = str(start_time)
    duration_seconds = str(end_time - start_time)
    path = pathlib.Path(filepath)
    clip_path = f"{Config.TMP_DIRECTORY}/{path.stem}_clip.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            start_seconds,
            "-t",
            duration_seconds,
            "-i",
            filepath,
            clip_path,
        ]
    )
    return clip_path


def clip_mp3_to_wav(filepath, start_time, end_time):
    podcast = AudioSegment.from_mp3(filepath)
    start_ms = start_time * 1000
    end_ms = end_time * 1000
    clip = podcast[start_ms:end_ms]
    clip_path = os.path.splitext(filepath)[0] + "_clip.wav"
    clip.export(clip_path, format="wav")
    return clip_path


def cleanup_tmp_files():
    for f in os.listdir(Config.TMP_DIRECTORY):
        os.remove(os.path.join(Config.TMP_DIRECTORY, f))
