import time
import logging
from datetime import timezone

import requests
from dateutil.parser import parse

from models import ExternalSyncRecord, User, UserSettings

from . import source_processors

readwise_url = "https://readwise.io/api/v2"


def get_readwise_user_token(user_id):
    user_settings = UserSettings.find_by_setting_name(user_id, "readwise_token")
    if user_settings:
        return user_settings.setting_value
    return None


def filter_highlights(highlights, since, note):
    filtered_highlights = []
    for highlight in highlights:
        if since and parse(highlight["created_at"]) < since:
            continue

        h_note = highlight.get("note", "")
        if note and note.casefold() != h_note.casefold():
            continue

        filtered_highlights.append(highlight["text"])
    return filtered_highlights


def filter_results(results, titles, note, since):
    highlights = []
    for result in results:
        r_title = result.get("title", "")
        if r_title not in titles:
            continue

        highlights.extend(filter_highlights(result["highlights"], since, note))
    return highlights


def get_new_highlights(user_id, titles=[], note=None):
    token = get_readwise_user_token(user_id)
    if not token:
        return []
    headers = {"Authorization": f"Token {token}"}
    response = requests.get(f"{readwise_url}/export", headers=headers)
    response_json = response.json()
    results = response_json["results"]
    last_sync_datetime = get_utc_sync_datetime(user_id)
    return filter_results(results, titles, note, last_sync_datetime)


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


def batch_tasks_from_highlights(highlights, user_id, time=0, duration=60):
    tasks = []
    for highlight in highlights:
        tasks.append(
            {
                "url": highlight,
                "user_id": user_id,
                "time": time,
                "duration": duration,
            }
        )
    return tasks


def get_titles(user_id):
    titles = []
    token = get_readwise_user_token(user_id)
    if not token:
        return titles
    headers = {"Authorization": f"Token {token}"}
    response = requests.get(f"{readwise_url}/export", headers=headers)
    response_json = response.json()
    results = response_json["results"]
    for result in results:
        titles.append(result["title"])
    return titles


def add_new_highlights_to_queue():
    users = User.get_all()
    for user in users:
        # TODO: Don't use string literals for settings names
        titles = get_sync_titles(user.id)
        note = UserSettings.get_value(user.id, "readwise_notes")
        highlights = get_new_highlights(user.id, titles, note)
        add_or_update_sync_record(user.id)
        tasks = batch_tasks_from_highlights(highlights, user.id)
        source_processors.add_batch_to_queue(tasks)


def get_sync_titles(user_id):
    title_settings = UserSettings.find_all_by_setting_name(user_id, "readwise_titles")
    titles = []
    for title_setting in title_settings:
        titles.append(title_setting.setting_value)
    return titles


def set_sync_titles(user_id, titles):
    UserSettings.delete_by_setting_name(user_id, "readwise_titles")
    for title in titles:
        setting = UserSettings(
            user_id=user_id, setting_name="readwise_titles", setting_value=title
        )
        setting.add_to_db()


def timer_job():
    while True:
        time.sleep(60)
        logging.info("Running timer job")
        add_new_highlights_to_queue()
