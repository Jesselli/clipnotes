from models import Snippet, Source, db


def get_sources(user_id):
    sources = (
        db.session()
        .query(Source)
        .join(Snippet)
        .order_by(Snippet.created_at.desc())
        .all()
    )
    for source in sources:
        source.snippets.sort(key=lambda x: x.time, reverse=False)
    return sources
