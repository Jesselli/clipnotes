import re
from urllib.parse import parse_qs, urlparse


def get_url_without_time(url: str) -> str:
    parsed_url = urlparse(url, allow_fragments=False)
    return parsed_url._replace(query="").geturl()


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


def time_to_seconds(note: str) -> int:
    if not note:
        return None
    split_note = note.split(":")
    if len(split_note) != 2:
        return None
    minutes = int(split_note[0])
    seconds = int(split_note[1])
    return (minutes * 60) + seconds


def parse_start_end_time(time_str: str) -> tuple[int, int]:
    """
    Returns the start and end times in seconds
    time_str expected format: 1:30-2:00
    """
    if not time_str:
        return None, None

    split_note = time_str.split("-")
    if len(split_note) != 2:
        return None, None

    start = time_to_seconds(split_note[0])
    end = time_to_seconds(split_note[1])
    return start, end
