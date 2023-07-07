import audible
from datetime import datetime
from typing import List


class AudibleClip:
    asin: str
    title: str
    startTime: int
    endTime: int
    creationTime: datetime

    def __init__(
        self,
        asin: str,
        title: str,
        startTimeStr: str,
        endTimeStr: str,
        createTimeStr: str,
    ):
        createdDateTime = datetime.strptime(createTimeStr, "%Y-%m-%d %H:%M:%S.%f")
        self.asin = asin
        self.title = title
        self.startTime = int(startTimeStr)
        self.endTime = int(endTimeStr)
        self.creationTime = createdDateTime


def get_all_clips() -> List[AudibleClip]:
    auth = audible.Authenticator.from_file("audible_auth.json")
    auth.get_activation_bytes("activation_bytes", True)

    with audible.Client(auth=auth) as client:
        library = client.get(
            "1.0/library",
            num_results=1000,
            response_groups="product_desc, product_attrs",
            sort_by="-PurchaseDate",
        )
        books = library["items"]
        all_clips = []
        for book in books:
            deets = client.get(f"1.0/library/{book['asin']}", response_groups="media")
            bookmarks = get_book_clips(client, book)
            all_clips.extend(bookmarks)
        return all_clips
        # download_book(client, book["asin"])


def get_book_clips(client: audible.Client, book) -> List[AudibleClip]:
    url = "https://cde-ta-g7g.amazon.com/FionaCDEServiceEngine/"
    url += f"sidecar?type=AUDI&key={book['asin']}"
    client._response_callback = lambda resp: resp
    resp = client.get(url)
    bookmarks = []
    try:
        body = resp.json()["payload"]

        for bookmark in body["records"]:
            if bookmark["type"] != "audible.clip":
                continue

            creationTime = bookmark.get("creationTime")
            startPosition = bookmark.get("startPosition")
            endPosition = bookmark.get("endPosition")
            clip = AudibleClip(
                book["asin"],
                book["title"],
                startPosition,
                endPosition,
                creationTime,
            )
            bookmarks.append(clip)
    except KeyError:
        print("FAILED response")
        print(resp.text)
    return bookmarks
