from datetime import datetime
from models import Source, Snippet, SyncRecord


def generate_source_markdown(source_id, user_id, exclusions=[], latest=False):
    since = datetime.min
    if latest and (sync_record := SyncRecord.get_user_sync_record(source_id, user_id)):
        since = sync_record.synced_at
    source = Source.find_by_id(source_id)
    snippets = Snippet.get_snippets_since(source_id, since)

    markdown = ""
    if "title" not in exclusions:
        markdown = f"# {source.title}\n\n"
        markdown += f"[{source.title}]({source.url})\n\n"
    if "thumbnail" not in exclusions:
        markdown += f"![thumbnail]({source.thumb_url})\n\n"
    for snippet in snippets:
        markdown += f"{snippet.text.lstrip()} [{snippet.time}]({source.url}?t={snippet.time})\n\n"

    return markdown
