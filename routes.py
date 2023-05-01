from flask import request, Blueprint, render_template
from models import Source, Snippet, db

from services import source_processors
from services import snippet_db

blueprint = Blueprint("test", __name__)

# TODO: Separate out the api from the rendering


@blueprint.get("/")
def index():
    # TODO Add support for multiple users
    user_id = 1
    sources = snippet_db.get_sources(user_id)
    return render_template("index.html", sources=sources)


@blueprint.get("/source/<int:source_id>/markdown")
def source_to_markdown(source_id):
    source = Source.query.get(source_id)
    snippets = Snippet.query.filter_by(source_id=source_id).all()
    markdown = f"# {source.title}\n\n"
    markdown += f"![thumbnail]({source.thumb_url})\n\n"
    markdown += f"[{source.title}]({source.url})\n\n"
    for snippet in snippets:
        markdown += f"{snippet.text.lstrip()} [{snippet.time}]({source.url}?t={snippet.time})\n\n"
    return markdown


@blueprint.delete("/source/<int:source_id>")
def delete_source(source_id):
    snippets = Snippet.query.filter_by(source_id=source_id).all()
    for snippet in snippets:
        db.session.delete(snippet)
    source = Source.query.get(source_id)
    db.session.delete(source)
    db.session.commit()
    return ""


@blueprint.post("/snippets")
def create_snippet():
    sources = []
    if request.form:
        url = request.form.get("url")
        duration = request.form.get("duration", 60, type=int)
        time = request.form.get("time", 0)
        # TODO: Add support for other users
        user_id = 1
        source_processors.process_url(url, user_id, time, duration)
        sources = snippet_db.get_sources(user_id)
    return render_template("partials/sources.html", sources=sources)


@blueprint.put("/snippet/<int:snippet_id>")
def update_snippet(snippet_id):
    text = request.form.get("text")
    Snippet.query.filter_by(id=snippet_id).update({"text": text})
    db.session.commit()
    return text


@blueprint.delete("/snippet/<int:snippet_id>")
def delete_snippet(snippet_id):
    Snippet.query.filter_by(id=snippet_id).delete()
    db.session.commit()
    return ""
