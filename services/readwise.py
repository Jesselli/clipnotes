import requests
from models import UserSettings, User
from . import source_processors

readwise_url = "https://readwise.io/api/v2"


def get_readwise_user_token(user_id):
    user_settings = UserSettings.find_by_user_and_setting_name(
        user_id, "readwise_token"
    )
    if user_settings:
        return user_settings.setting_value
    return None


def get_highlights_text(user_id, title=None, note=None):
    token = get_readwise_user_token(user_id)
    headers = {"Authorization": f"Token {token}"}
    response = requests.get(f"{readwise_url}/export", headers=headers)
    response_json = response.json()
    results = response_json["results"]

    # TODO: Nesting yuck.
    highlight_text = []
    for result in results:
        r_title = result.get("title", "")
        if title and title.casefold() != r_title.casefold():
            continue

        highlights = result["highlights"]
        for highlight in highlights:
            h_note = highlight.get("note", "")
            if note and note.casefold() != h_note.casefold():
                continue
            highlight_text.append(highlight["text"])

    return highlight_text


def timer_job():
    print("Running timer job")
    users = User.get_all()
    for user in users:
        title = UserSettings.get_value(user.id, "readwise_titles")
        note = UserSettings.get_value(user.id, "readwise_notes")
        highlights = get_highlights_text(user.id, title, note)
        for highlight in highlights:
            source_processors.add_to_queue(highlight, user.id, 0, 60)
