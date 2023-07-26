import subprocess
import os
import shutil
import time
import requests
import logging
import audible
from datetime import datetime
from typing import List, Optional
import models as db
from config import Config
from string import Template
from pathlib import Path
from services import files

DOWNLOAD_URL = Template(
    "https://www.audible.com/library/download?asin=$asin&codec=AAX",
)

BOOKMARK_URL = Template(
    "https://cde-ta-g7g.amazon.com/FionaCDEServiceEngine/sidecar?type=AUDI&key=$asin",
)


class AudibleClip:
    asin: str
    title: str
    start_seconds: int
    end_seconds: int
    creation_time: datetime
    thumbnail: str

    def __init__(
        self,
        asin: str,
        title: str,
        start_seconds: int,
        end_seconds: int,
        create_time_str: str,
        thumbnail: str,
    ):
        created_dt = datetime.strptime(create_time_str, "%Y-%m-%d %H:%M:%S.%f")
        self.asin = asin
        self.title = title
        self.start_seconds = start_seconds
        self.end_seconds = end_seconds
        self.creation_time = created_dt
        self.thumbnail = thumbnail

    @staticmethod
    def from_book_dict(book, bookmark) -> "AudibleClip":
        creation_time = bookmark.get("creationTime")
        start_position = bookmark.get("startPosition")
        start_seconds = int(start_position) // 1000
        end_position = bookmark.get("endPosition")
        end_seconds = int(end_position) // 1000
        thumbnail = ""
        if "product_images" in book:
            if "500" in book["product_images"]:
                thumbnail = book["product_images"]["500"]

        return AudibleClip(
            book["asin"],
            book["title"],
            start_seconds,
            end_seconds,
            creation_time,
            thumbnail,
        )


def get_library_items(user_id: int) -> List:
    auth = get_audible_auth(user_id)
    with audible.Client(auth=auth) as client:
        library = client.get(
            "1.0/library",
            num_results=1000,
            response_groups="product_desc, product_attrs, media",
            sort_by="-PurchaseDate",
        )
    return library["items"]


def get_new_clips(user_id: int) -> List[AudibleClip]:
    books = get_library_items(user_id)
    all_clips = get_all_clips(user_id, books)

    last_sync = db.AudibleSyncRecord.get_user_last_sync(user_id)
    if last_sync:
        new_clips = [clip for clip in all_clips if clip.creation_time > last_sync]
    else:
        new_clips = all_clips

    db.AudibleSyncRecord.update_user_sync_record(user_id)
    return new_clips


def get_all_clips(user_id: int, books: List) -> List[AudibleClip]:
    auth = get_audible_auth(user_id)
    bookmarks = []
    with audible.Client(auth=auth) as client:
        for book in books:
            clips = get_clips_from_book(client, book)
            bookmarks.extend(clips)
    return bookmarks


def get_clips_from_book(client: audible.Client, book: dict) -> List[AudibleClip]:
    url = BOOKMARK_URL.substitute(asin=book["asin"])
    client._response_callback = lambda resp: resp
    resp = client.get(url)
    bookmarks = []
    try:
        body = resp.json()["payload"]
        for bookmark in body["records"]:
            if bookmark["type"] != "audible.clip":
                continue

            clip = AudibleClip.from_book_dict(book, bookmark)
            bookmarks.append(clip)
    except KeyError:
        msg = f"{book['title']} FAILED to get bookmarks: {resp.status_code}"
        logging.info(msg)
    return bookmarks


def find_book_file(asin: str) -> Optional[str]:
    audible_directory = files.get_audible_dir()
    for file in os.listdir(audible_directory):
        if not os.path.isfile(os.path.join(audible_directory, file)):
            continue
        elif asin in file:
            return os.path.join(audible_directory, file)
    return None


def download_book(client, asin) -> str:
    if book_file := find_book_file(asin):
        logging.info(f"Book {asin} already downloaded")
        return book_file

    logging.info(f"Downloading book for asin {asin}")
    client._response_callback = lambda resp: resp.next_request
    url = DOWNLOAD_URL.substitute(asin=asin.zfill(10))
    resp = client.get(url)
    book_file = os.path.join(files.get_audible_dir(), f"{asin}.aax")
    with requests.get(resp.url, stream=True) as r:
        if not r.ok:
            msg = "Failed to download Audible book"
            raise ConnectionError(msg, r)
        with open(book_file, "wb") as f:
            shutil.copyfileobj(r.raw, f)

    logging.info(f"Downloaded {book_file}")
    return book_file


def create_models(user_id: int, audible_clip: AudibleClip):
    book_file = f"file://{audible_clip.asin}.aax"
    source = db.Source.add(
        url=book_file,
        title=audible_clip.title,
        provider=db.SourceProvider.AUDIBLE,
        thumb_url=audible_clip.thumbnail,
    )
    snippet = db.Snippet.add(
        user_id,
        source.id,
        audible_clip.start_seconds,
        audible_clip.end_seconds,
    )
    db.Audible.add(
        snippet.id,
        audible_clip.asin,
    )


def aax_to_m4b(aax_path: str, activation_bytes: str) -> Optional[str]:
    logging.info(f"Converting {aax_path} to m4b")
    path = Path(aax_path)
    m4b_path = os.path.join(path.parents[0], f"{path.stem}.m4b")
    try:
        ffmpeg_proc = subprocess.run(
            [
                "ffmpeg",
                "-activation_bytes",
                activation_bytes,
                "-i",
                aax_path,
                "-c",
                "copy",
                m4b_path,
            ]
        )
        ffmpeg_proc.check_returncode()
    except subprocess.CalledProcessError as err:
        msg = f"Failed to convert aax to m4b: {err.stderr}"
        logging.error(msg)
        return None

    if ffmpeg_proc.returncode == 0:
        os.remove(aax_path)

    return m4b_path


def download_audible_data(queue_item: db.Snippet) -> Optional[str]:
    auth = get_audible_auth(queue_item.user_id)
    activation_bytes = get_activation_bytes(queue_item.user_id)
    audible_data = db.Audible.get_audible_data(queue_item.id)
    with audible.Client(auth=auth) as client:
        book_file = download_book(client, audible_data.asin)
    if book_file.endswith("aax"):
        book_file = aax_to_m4b(book_file, activation_bytes)
    return book_file


def sync_with_audible():
    while True:
        for user in db.User.get_all():
            logging.info(f"Syncing with Audible for user {user.id}")
            clips = get_new_clips(user.id)
            logging.info(f"Found {len(clips)} new Audible clips")
            for clip in clips:
                create_models(
                    user.id,
                    clip,
                )
        time.sleep(Config.AUDIBLE_SYNC_SECONDS)


def save_audible_auth_to_file(email: str, password: str):
    user = db.User.find_by_email(email)
    if not user:
        print("There is no ClipNotes user with that email")
        return

    auth = audible.Authenticator.from_login(
        email,
        password,
        locale="us",
        with_username=False,
    )

    user_id = str(user.id)
    audible_directory = files.get_audible_dir()
    file = os.path.join(audible_directory, user_id, "audible_auth.json")
    auth.to_file(file)
    return auth


def get_audible_auth(user_id: int) -> audible.Authenticator:
    auth_file = os.path.join(
        files.get_audible_dir(),
        str(user_id),
        "audible_auth.json",
    )
    return audible.Authenticator.from_file(auth_file)


def get_activation_bytes(user_id: int):
    activation_file = os.path.join(
        files.get_audible_dir(),
        str(user_id),
        "activation_bytes",
    )
    return get_audible_auth(user_id).get_activation_bytes(activation_file, True)
