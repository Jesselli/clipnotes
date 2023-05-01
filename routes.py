from flask import request, Blueprint, render_template
from models import Source, Snippet, db

from services import source_processors
from services import snippet_db

# TODO: Rename this blueprint to something more meaningful
test = Blueprint("test", __name__)

# TODO: Separate out the backend from the HTML rendering


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
    return ""


# TODO: We may not need the GET method here
@test.route("/snippets", methods=["GET", "POST"])
def snippets():
    if request.method == "POST":
        if request.form:
            url = request.form.get("url")
            duration = request.form.get("duration", 60, type=int)
            time = request.form.get("time", 0)
            # TODO: Add support for other users
            user_id = 1
            source_processors.process_url(url, user_id, time, duration)
            sources = snippet_db.get_sources(user_id)
            return render_template("partials/sources.html", sources=sources)
        else:
            url = request.args.get("url")
            time = request.args.get("time")
            duration = request.args.get("duration", 60, type=int)
            # TODO: Add support for other users
            user_id = 1
            source_processors.process_url(url, user_id, time, duration)
            sources = snippet_db.get_sources(user_id)
            return render_template("partials/sources.html", sources=sources)


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
        return ""
