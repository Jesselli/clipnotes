from datetime import datetime

from flask import request, Blueprint, render_template, jsonify, redirect
from models import Source, Snippet, User, SyncRecord, Device, Session
from sqlalchemy import and_
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, login_user, logout_user, current_user

from services import source_processors

blueprint = Blueprint("test", __name__)

# TODO: Separate out the api from the rest of the app


@blueprint.get("/register")
def register():
    return render_template("register.html")


@blueprint.get("/login")
def login():
    return render_template("login.html")


@blueprint.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")


@blueprint.get("/")
@login_required
def index():
    sources = Source.get_sources_and_snippets(current_user.id)
    return render_template("index.html", sources=sources)


@blueprint.post("/login")
def login_post():
    if request.form:
        username = request.form["email"]
        password = request.form["password"]
        user = Session.query(User).filter_by(email=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect("/")
    return "Invalid credentials", 401


@blueprint.post("/register")
def register_user():
    if request.form:
        username = request.form["email"]
        password_hash = generate_password_hash(request.form["password"])
        User.create(username, password_hash)
    return "Registered", 200


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
        markdown += f"{snippet.text.lstrip()} [{snippet.time}]({source.url}?t={snippet.time})\n\n{snippet.text.lstrip()} [{snippet.time}]({source.url}?t={snippet.time})\n\n"
    return markdown


@blueprint.post("/source/<int:source_id>/sync")
def create_sync_record(source_id):
    # TODO Add support for multiple users
    # TODO Update existing sync record if it exists and return the appropriate status code
    user_id = 1
    sync_record = SyncRecord(user_id=user_id, source_id=source_id)
    sync_record.add_to_db()
    return jsonify(sync_record)


# TODO: Move this to a service file
def get_sync_record(source_id):
    # TODO Add support for multiple users
    user_id = 1
    sync_record = (
        Session.query(SyncRecord)
        .filter_by(user_id=user_id, source_id=source_id)
        .order_by(SyncRecord.synced_at.desc())
        .first()
    )
    return sync_record


@blueprint.get("/sources")
def get_sources():
    # TODO Add support for multiple users
    user_id = 1
    sources = Source.get_sources_and_snippets(user_id)
    return jsonify(sources)


@blueprint.delete("/source/<int:source_id>")
def delete_source(source_id):
    snippets = Session.query(Snippet).filter_by(source_id=source_id).all()
    for snippet in snippets:
        Session.delete(snippet)
    source = Session.query(Source).get(source_id)
    source.delete_from_db()
    return ""


@blueprint.post("/snippets")
def create_snippet():
    sources = []
    url = request.form.get("url")
    duration = request.form.get("duration", 60, type=int)
    time = request.form.get("time", 0)
    if current_user and current_user.is_authenticated:
        source_processors.process_url(url, current_user.id, time, duration)
        sources = Source.get_sources_and_snippets(current_user.id)
        return render_template("partials/sources.html", sources=sources)
    else:
        return "Not authenticated"


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
    Snippet.update_text_in_db(snippet_id, text)
    return text


@blueprint.delete("/snippet/<int:snippet_id>")
def delete_snippet(snippet_id):
    Snippet.delete_from_db(snippet_id)
    return ""


@blueprint.get("/devices")
def get_devices():
    devices = Device.find_devices_for_user(current_user.id)
    return render_template("devices.html", devices=devices)


@blueprint.post("/devices")
def add_device():
    # name = request.args.get("device_name")
    name = request.form.get("device_name")
    if Device.find_by_name(name):
        return "Device already exists", 400

    if current_user and current_user.is_authenticated:
        new_device = Device(device_name=name, user_id=current_user.id)
        new_device.save_to_db()
    else:
        # TODO: Remove. Obviously this is just a temporary measure to get started
        new_device = Device(device_name=name, user_id=1)
        new_device.save_to_db()

    return "Created", 200
