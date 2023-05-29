import time
import logging
from datetime import timezone

import requests
from dateutil.parser import parse

from models import ExternalSyncRecord, User, UserSettings

from . import source_processors

readwise_url = "https://readwise.io/api/v2"


# TODO Just reuse the existing snippet model?
class Snippet:
    def __init__(self, url, time_seconds=None, duration_seconds=None):
        self.url = url
        self.time_seconds = time_seconds
        self.duration_seconds = duration_seconds


def get_token_from_db(user_id):
    user_settings = UserSettings.find(user_id, "readwise_token")
    if user_settings:
        return user_settings.value
    return None


def time_to_seconds(note: str) -> int:
    if not note:
        return None
    split_note = note.split(":")
    if len(split_note) != 2:
        return None
    minutes = int(split_note[0])
    seconds = int(split_note[1])
    return (minutes * 60) + seconds


def time_duration_from_note(note: str, default_duration: int) -> (int, int):
    if not note:
        return 0, default_duration

    split_note = note.split("-")
    if len(split_note) == 0:
        return 0, default_duration
    elif len(split_note) == 1:
        return time_to_seconds(split_note[0]), default_duration

    start = time_to_seconds(split_note[0])
    end = time_to_seconds(split_note[1])
    time = start + ((end - start) // 2)
    duration = end - start
    return time, duration


def get_snippets_from_highlights(highlights, since, note, default_duration):
    snippets = []
    for highlight in highlights:
        if since and parse(highlight["created_at"]) < since:
            continue
        h_note = highlight.get("note", "")
        time, duration = time_duration_from_note(h_note, default_duration)
        # TODO Make sure this is a supported url
        url = highlight["text"]
        snippet = Snippet(url, time, duration)
        snippets.append(snippet)
    return snippets


def get_snippets_from_results(results, titles, note, since, default_duration):
    snippets = []
    for result in results:
        r_title = result.get("title", "")
        if r_title not in titles:
            continue

        highlights = result.get("highlights", [])
        highlight_snippets = get_snippets_from_highlights(
            highlights, since, note, default_duration
        )
        snippets.extend(highlight_snippets)
    return snippets


def get_snippets_from_new_highlights(user_id, titles=[], note=None):
    logging.debug("Retrieving new highlights from Readwise")
    token = get_token_from_db(user_id)
    if not token:
        logging.warning("No Readwise token found")
        return []

    headers = {"Authorization": f"Token {token}"}
    response = requests.get(f"{readwise_url}/export", headers=headers)
    response_json = response.json()
    results = response_json["results"]
    last_sync = get_utc_sync_datetime(user_id)
    logging.debug(f"Last sync datetime: {last_sync}")
    default_duration = UserSettings.find(user_id, "readwise_duration")
    if default_duration:
        default_duration = int(default_duration.value)
    else:
        default_duration = 60
    snippets = get_snippets_from_results(
        results, titles, note, last_sync, default_duration
    )
    logging.debug(f"Found {len(snippets)} new highlights")
    return snippets


def get_utc_sync_datetime(user_id):
    sync_record = ExternalSyncRecord.get_readwise_sync_record(user_id)
    if sync_record:
        return sync_record.synced_at.replace(tzinfo=timezone.utc)
    return None


def add_or_update_sync_record(user_id):
    sync_record = ExternalSyncRecord.get_readwise_sync_record(user_id)
    if not sync_record:
        ExternalSyncRecord.add_readwise_sync_record(user_id)
    else:
        ExternalSyncRecord.update_readwise_sync_record(user_id)


def get_all_titles(user_id):
    titles = []
    token = get_token_from_db(user_id)
    if not token:
        return titles
    headers = {"Authorization": f"Token {token}"}
    response = requests.get(f"{readwise_url}/export", headers=headers)
    response_json = response.json()
    results = response_json["results"]
    for result in results:
        titles.append(result["title"])
    return titles


def batch_tasks_from_snippets(snippets, user_id):
    tasks = []
    for snippet in snippets:
        tasks.append(
            {
                "url": snippet.url,
                "user_id": user_id,
                "time": snippet.time_seconds,
                "duration": snippet.duration_seconds,
            }
        )
    return tasks


def add_new_highlights_to_queue():
    users = User.get_all()
    for user in users:
        # TODO: Don't use string literals for settings names
        titles = get_sync_titles_from_db(user.id)
        note = UserSettings.find(user.id, "readwise_notes")
        if note:
            note = note.value
        snippets = get_snippets_from_new_highlights(user.id, titles, note)
        add_or_update_sync_record(user.id)
        tasks = batch_tasks_from_snippets(snippets, user.id)
        source_processors.add_batch_to_queue(tasks)


def get_sync_titles_from_db(user_id):
    title_settings = UserSettings.find_all(user_id, "readwise_titles")
    titles = []
    for title_setting in title_settings:
        titles.append(title_setting.value)
    return titles


def save_sync_titles_to_db(user_id, titles):
    UserSettings.delete(user_id, "readwise_titles")
    for title in titles:
        UserSettings.create(user_id, "readwise_titles", title)


def timer_job():
    while True:
        time.sleep(60)
        logging.info("Readwise timer job triggered")
        add_new_highlights_to_queue()
