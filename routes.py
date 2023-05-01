from flask import request, Blueprint, render_template
from models import Source, Snippet, db

from services import source_processors
from services import snippet_db

test = Blueprint("test", __name__)


@test.route("/")
def index():
    # TODO Add support for multiple users
    user_id = 1
    sources = snippet_db.get_sources(user_id)
    return render_template("index.html", sources=sources)


@test.route("/source/<int:source_id>/markdown", methods=["GET"])
def source_to_markdown(source_id):
    source = Source.query.get(source_id)
    snippets = Snippet.query.filter_by(source_id=source_id).all()
    md = f"# {source.title}\n\n"
    md += f"![thumbnail]({source.thumb_url})\n\n"
    md += f"[{source.title}]({source.url})\n\n"
    for snippet in snippets:
        md += f"{snippet.text.lstrip()} [{snippet.time}]({source.url}?t={snippet.time})\n\n"
    return md


@test.route("/source/<int:source_id>", methods=["DELETE"])
def delete_source(source_id):
    snippets = Snippet.query.filter_by(source_id=source_id).all()
    for snippet in snippets:
        db.session.delete(snippet)
    source = Source.query.get(source_id)
    db.session.delete(source)
    db.session.commit()
    return "<div/>"


@test.route("/snippets", methods=["GET", "POST"])
def snippets():
    if request.method == "POST":
        if request.form:
            url = request.form.get("url")
            duration = request.form.get("duration", 60, type=int)
            time = request.form.get("time", 0)
            user_id = 1
            return source_processors.process_url(url, user_id, time, duration)
        else:
            url = request.args.get("url")
            time = request.args.get("time")
            duration = request.args.get("duration", 60, type=int)
            user_id = 1
            return source_processors.process_url(url, user_id, time, duration)


@test.route("/snippet/<int:snippet_id>", methods=["GET", "PUT", "DELETE"])
def snippet(snippet_id):
    if request.method == "PUT":
        text = request.form.get("text")
        Snippet.query.filter_by(id=snippet_id).update({"text": text})
        db.session.commit()
        return text
    elif request.method == "DELETE":
        Snippet.query.filter_by(id=snippet_id).delete()
        db.session.commit()
        return "<div/>"
