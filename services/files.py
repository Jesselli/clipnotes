import os
import pathlib
import subprocess
from urllib.parse import urlparse

import requests
from pydub import AudioSegment

from config import Config


def get_tmp_dir():
    os.makedirs(Config.TMP_DIRECTORY, exist_ok=True)
    return Config.TMP_DIRECTORY


def get_audible_dir():
    os.makedirs(Config.AUDIBLE_DIRECTORY, exist_ok=True)
    return Config.AUDIBLE_DIRECTORY


def download_file(url, filename=None):
    directory = get_tmp_dir()
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


def clip_m4b_to_wav(filepath, start_time, end_time):
    start_seconds = str(start_time)
    duration_seconds = str(end_time - start_time)
    path = pathlib.Path(filepath)
    clip_path = f"{get_tmp_dir()}/{path.stem}_clip.wav"
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
    tmp_directory = get_tmp_dir()
    for f in os.listdir(tmp_directory):
        os.remove(os.path.join(tmp_directory, f))
