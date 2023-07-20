import subprocess
import os
import shutil
import requests
import logging
import audible
from datetime import datetime
from typing import List, Optional
import models as db
from config import Config
from string import Template
from pathlib import Path

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
    creationTime: datetime
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
        self.creationTime = created_dt
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


def get_all_clips() -> List[AudibleClip]:
    auth = audible.Authenticator.from_file("audible_auth.json")

    with audible.Client(auth=auth) as client:
        library = client.get(
            "1.0/library",
            num_results=1000,
            response_groups="product_desc, product_attrs, media",
            sort_by="-PurchaseDate",
        )
        books = library["items"]
        all_clips = []
        for book in books:
            bookmarks = get_book_clips(client, book)
            all_clips.extend(bookmarks)
        return all_clips


def get_book_clips(client: audible.Client, book) -> List[AudibleClip]:
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
    for file in os.listdir(Config.AUDIBLE_DIRECTORY):
        if not os.path.isfile(os.path.join(Config.AUDIBLE_DIRECTORY, file)):
            continue
        elif asin in file:
            return os.path.join(Config.AUDIBLE_DIRECTORY, file)
    return None


def download_book(client, asin) -> str:
    if book_file := find_book_file(asin):
        logging.info(f"Book {asin} already downloaded")
        return book_file

    client._response_callback = lambda resp: resp.next_request
    url = DOWNLOAD_URL.substitute(asin=asin.zfill(10))
    resp = client.get(url)
    book_file = os.path.join(Config.AUDIBLE_DIRECTORY, f"{asin}.aax")
    with requests.get(resp.url, stream=True) as r:
        if not r.ok:
            msg = "Failed to download Audible book"
            raise ConnectionError(msg, r)
        with open(book_file, "wb") as f:
            shutil.copyfileobj(r.raw, f)

    logging.info(f"Downloaded {book_file}")
    return book_file


def create_models(user_id: int, audible_clip: AudibleClip):
    book_file = os.path.join(Config.AUDIBLE_DIRECTORY, f"{audible_clip.asin}.aax")
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
    auth = audible.Authenticator.from_file("audible_auth.json")
    activation_bytes = auth.get_activation_bytes("activation_bytes", True, True)
    audible_data = db.Audible.get_audible_data(queue_item.id)
    with audible.Client(auth=auth) as client:
        book_file = download_book(client, audible_data.asin)
    if book_file.endswith("aax"):
        book_file = aax_to_m4b(book_file, activation_bytes)
    return book_file


# def get_audible_auth():
#     # TODO GET RID OF THIS BEFORE COMMIT
#     auth = audible.Authenticator.from_login(
#         "jesselli@gmail.com",
#         "A!m7A!z1O(n6",
#         locale="us",
#         with_username=False,
#     )
#     auth.to_file("audible_auth.json")
