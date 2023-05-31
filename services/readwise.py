import logging
import time
from datetime import timezone
from typing import Optional

import requests
from dateutil.parser import parse
from flask import url_for

from models import ExternalSyncRecord, User, UserSettings

from . import source_processors, time_str

SETTING_TITLES = "readwise_titles"
SETTING_TOKEN = "readwise_token"
SETTING_DURATION = "readwise_duration"
readwise_url = "https://readwise.io/api/v2"


class SnippetTask:
    def __init__(self, url, user_id, time_seconds, duration_seconds):
        self.url = url
        self.time = time_seconds
        self.duration = duration_seconds
        self.user_id = user_id


def request_readwise(user_id, method, path, query={}):
    try:
        token = get_readwise_token_from_db(user_id)
        headers = {"Authorization": f"Token {token}"}
        response = requests.request(
            method,
            f"{readwise_url}/{path}",
            headers=headers,
            params=query
        )
    except Exception as e:
        logging.error(f"Failed to reach Readwise: {e}")
        return None
    return response


def get_readwise_token_from_db(user_id: int) -> Optional[str]:
    user_settings = UserSettings.find(user_id, SETTING_TOKEN)
    if user_settings:
        return user_settings.value
    return None


def get_snippets_from_highlights(user_id, highlights, last_sync):
    snippets = []
    for highlight in highlights:
        if last_sync and parse(highlight["highlighted_at"]) < last_sync:
            continue

        url = highlight["text"]
        if not source_processors.is_source_supported(url):
            logging.warning(f"Skipping unsupported url: {url}")
            continue

        h_note = highlight.get("note", "")
        default_duration = get_default_duration(user_id)
        time, duration = time_str.parse_time_duration(h_note, default_duration)
        snippet = SnippetTask(url, user_id, time, duration)
        snippets.append(snippet)
    return snippets


def get_highlights_for_title(user_id, book_id):
    query = {"book_id": book_id}
    response = request_readwise(user_id, "GET", "highlights", query)
    if not response:
        return []
    response_json = response.json()
    results = response_json["results"]
    return results


def get_default_duration(user_id):
    default_duration = UserSettings.find(user_id, SETTING_DURATION)
    if default_duration:
        default_duration = int(default_duration.value)
    else:
        default_duration = 60
    return default_duration


def get_new_snippets(user_id, titles=[]):
    logging.debug("Retrieving new highlights from Readwise")

    highlights = []
    for title in titles:
        logging.debug(f"Syncing title: {title}")
        title_highlights = get_highlights_for_title(user_id, title)
        highlights.extend(title_highlights)

    last_sync = get_utc_sync_datetime(user_id)
    logging.debug(f"Last sync datetime: {last_sync}")

    snippets = get_snippets_from_highlights(
        user_id,
        highlights,
        last_sync,
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
    response = request_readwise(user_id, "GET", "books")
    if not response:
        return titles
    response_json = response.json()
    return response_json["results"]


def batch_tasks_from_snippets(snippets):
    tasks = []
    for snippet in snippets:
        tasks.append(snippet.__dict__)
    return tasks


def add_new_highlights_to_queue():
    users = User.get_all()
    for user in users:
        titles = get_sync_titles_from_db(user.id)
        snippets = get_new_snippets(user.id, titles)
        add_or_update_sync_record(user.id)
        tasks = batch_tasks_from_snippets(snippets)
        source_processors.add_batch_to_queue(tasks)


def get_sync_titles_from_db(user_id):
    title_settings = UserSettings.find_all(user_id, SETTING_TITLES)
    titles = []
    for title_setting in title_settings:
        titles.append(int(title_setting.value))
    return titles


def save_sync_titles_to_db(user_id, titles):
    UserSettings.delete(user_id, SETTING_TITLES)
    for title in titles:
        UserSettings.create(user_id,  SETTING_TITLES, title)


def timer_job():
    while True:
        time.sleep(60)
        logging.info("Readwise timer job triggered")
        add_new_highlights_to_queue()
