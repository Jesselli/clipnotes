from datetime import datetime

import models as db


def generate_source_markdown(source_id, user_id, exclusions=[], latest=False):
    since = datetime.min
    if latest and (
        sync_record := db.SyncRecord.get_user_sync_record(source_id, user_id)
    ):
        since = sync_record.synced_at
    source = db.Source.find_by_id(source_id)
    snippets = db.Snippet.get_snippets_since(source_id, since)

    markdown = ""
    if "title" not in exclusions:
        markdown = f"# {source.title}\n\n"
        markdown += f"[{source.title}]({source.url})\n\n"
    if "thumbnail" not in exclusions:
        markdown += f"![thumbnail]({source.thumb_url})\n\n"
    for snippet in snippets:
        text = snippet.text.lstrip()
        start = snippet.start_time
        markdown += f"{text} [{start}]({source.url}?t={start})\n\n"

    return markdown
