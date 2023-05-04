from datetime import datetime

from flask import request, Blueprint, render_template, jsonify
from models import Source, Snippet, SyncRecord, Session
from sqlalchemy import and_

from services import source_processors
from services import snippet_db

blueprint = Blueprint("test", __name__)

# TODO: Separate out the api from the rest of the app


@blueprint.get("/")
def index():
    # TODO Add support for multiple users
    user_id = 1
    sources = snippet_db.get_sources(user_id)
    return render_template("index.html", sources=sources)


@blueprint.get("/source/<int:source_id>/markdown")
def get_source_markdown(source_id):
    # TODO Look into better ways of parsing requests -- reqparse? Marshmallow?
    exclusions = request.args.get("exclude", [])
    get_latest = request.args.get("latest", False)
    # TODO: This is ugly. Shouldn't mutate types.
    if str(get_latest).lower() == "true":
        get_latest = True
    elif str(get_latest).lower() == "false":
        get_latest = False

    since = datetime.min
    if get_latest and (sync_record := get_sync_record(source_id)):
        since = sync_record.synced_at

    source = Session.query(Source).get(source_id)
    filter = and_(Snippet.source_id == source_id, Snippet.created_at > since)
    snippets = Session.query(Snippet).filter(filter).all()
    markdown = ""
    if not get_latest and "title" not in exclusions:
        markdown = f"# {source.title}\n\n"
    if not get_latest and "thumbnail" not in exclusions:
        markdown += f"![thumbnail]({source.thumb_url})\n\n"
    if not get_latest:
        markdown += f"[{source.title}]({source.url})\n\n"
    for snippet in snippets:
        markdown += f"{snippet.text.lstrip()} [{snippet.time}]({source.url}?t={snippet.time})\n\n"
    return markdown


@blueprint.post('/source/<int:source_id>/sync')
def create_sync_record(source_id):
    # TODO Add support for multiple users
    # TODO Update existing sync record if it exists and return the appropriate status code
    user_id = 1
    sync_record = SyncRecord(user_id=user_id, source_id=source_id)
    Session.add(sync_record)
    Session.commit()
    return jsonify(sync_record)


# TODO: Move this to a service file
def get_sync_record(source_id):
    # TODO Add support for multiple users
    user_id = 1
    sync_record = Session.query(SyncRecord).filter_by(user_id=user_id, source_id=source_id).order_by(SyncRecord.synced_at.desc()).first()
    return sync_record


@blueprint.get("/sources")
def get_sources():
    # TODO Add support for multiple users
    user_id = 1
    sources = snippet_db.get_sources(user_id)
    return jsonify(sources)


@blueprint.delete("/source/<int:source_id>")
def delete_source(source_id):
    snippets = Session.query(Snippet).filter_by(source_id=source_id).all()
    for snippet in snippets:
        Session.delete(snippet)
    source = Session.query(Source).get(source_id)
    Session.delete(source)
    Session.commit()
    return ""


@blueprint.post("/snippets")
def create_snippet():
    sources = []
    url = request.form.get("url")
    duration = request.form.get("duration", 60, type=int)
    time = request.form.get("time", 0)
    # TODO: Add support for other users
    user_id = 1
    source_processors.process_url(url, user_id, time, duration)
    sources = snippet_db.get_sources(user_id)
    return render_template("partials/sources.html", sources=sources)


@blueprint.post("/snippet/enqueue")
def enqueue_snippet():
    url = request.args.get("url")
    duration = request.args.get("duration", 60, type=int)
    time = request.args.get("time", 0)
    user_id = 1
    source_processors.add_to_queue(url, user_id, time, duration)
    return f"Added {url} to queue", 200


@blueprint.put("/snippet/<int:snippet_id>")
def update_snippet(snippet_id):
    text = request.form.get("text")
    Session.query(Snippet).filter_by(id=snippet_id).update({"text": text})
    Session.commit()
    return text


@blueprint.delete("/snippet/<int:snippet_id>")
def delete_snippet(snippet_id):
    Session.query(Snippet).filter_by(id=snippet_id).delete()
    Session.commit()
    return ""
