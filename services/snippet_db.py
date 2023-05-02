from models import Snippet, Source, Session


def get_sources(user_id):
    sources = (
        Session
        .query(Source)
        .join(Snippet)
        .order_by(Snippet.created_at.desc())
        .all()
    )
    for source in sources:
        source.snippets.sort(key=lambda x: x.time, reverse=False)
    return sources
