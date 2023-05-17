from datetime import datetime
import uuid

from flask import request, Blueprint, render_template, jsonify, redirect, Response
from models import Source, Snippet, User, SyncRecord, Device, Session
from sqlalchemy import and_
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_required, login_user, logout_user, current_user

from services import source_processors

main = Blueprint("main", __name__)
api = Blueprint("api", __name__, url_prefix="/api")


@main.get("/register")
def register():
    return render_template("register.html")


@main.get("/login")
def login():
    return render_template("login.html")


@main.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")


@main.get("/")
@login_required
def index():
    sources = Source.get_sources_and_snippets(current_user.id)
    return render_template("index.html", sources=sources)


@main.post("/login")
def login_post():
    if request.form:
        username = request.form["email"]
        password = request.form["password"]
        user = Session.query(User).filter_by(email=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            response = Response("Logged in", 200)
            response.headers["HX-Redirect"] = "/"
            return response
    return render_template("partials/login_form.html", message="Invalid credentials")


@main.post("/register")
def register_user():
    if request.form:
        username = request.form["email"]
        password_hash = generate_password_hash(request.form["password"])
        User.create(username, password_hash)
    return "Registered", 200


# TODO: Move this to a service
def get_markdown(source_id, user_id, exclusions=[], latest=False, since=datetime.min):
    source = Session.query(Source).get(source_id)
    filter = and_(Snippet.source_id == source_id, Snippet.created_at > since)
    snippets = Session.query(Snippet).filter(filter).all()

    if latest and (sync_record := SyncRecord.get_user_sync_record(source_id, user_id)):
        since = sync_record.synced_at

    markdown = ""
    if not latest and "title" not in exclusions:
        markdown = f"# {source.title}\n\n"
    if not latest and "thumbnail" not in exclusions:
        markdown += f"![thumbnail]({source.thumb_url})\n\n"
    if not latest:
        markdown += f"[{source.title}]({source.url})\n\n"
    for snippet in snippets:
        markdown += f"{snippet.text.lstrip()} [{snippet.time}]({source.url}?t={snippet.time})\n\n{snippet.text.lstrip()} [{snippet.time}]({source.url}?t={snippet.time})\n\n"
    return markdown


@main.get("/source/<int:source_id>/markdown")
@login_required
def get_source_markdown(source_id):
    user_id = current_user.id
    return get_markdown(source_id, user_id)


@main.delete("/source/<int:source_id>")
def delete_source(source_id):
    snippets = Session.query(Snippet).filter_by(source_id=source_id).all()
    for snippet in snippets:
        Session.delete(snippet)
    source = Session.query(Source).get(source_id)
    source.delete_from_db()
    return ""


@main.post("/snippets")
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


@main.post("/snippet/enqueue")
def enqueue_snippet():
    url = request.args.get("url")
    duration = request.args.get("duration", 60, type=int)
    time = request.args.get("time", 0)
    user_id = 1
    source_processors.add_to_queue(url, user_id, time, duration)
    return f"Added {url} to queue", 200


@main.put("/snippet/<int:snippet_id>")
def update_snippet(snippet_id):
    text = request.form.get("text")
    snippet = Snippet.find_by_id(snippet_id)
    snippet.update_text_in_db(text)
    return text


@main.delete("/snippet/<int:snippet_id>")
def delete_snippet(snippet_id):
    snippet = Snippet.find_by_id(snippet_id)
    snippet.delete_from_db()
    return ""


@main.get("/devices")
@login_required
def get_devices():
    if current_user and current_user.is_authenticated:
        user_id = current_user.id

    devices = Device.find_devices_for_user(user_id)
    return render_template("devices.html", devices=devices)


@main.post("/devices")
def add_device():
    if request.form:
        name = request.form.get("device_name")
    if Device.find_by_name(name):
        return "Device already exists", 400

    if current_user and current_user.is_authenticated:
        device_key = uuid.uuid4().hex
        new_device = Device(device_name=name, user_id=current_user.id, device_key=device_key)
        new_device.add_to_db()

    devices = Device.find_devices_for_user(current_user.id)
    return render_template("partials/device_table.html", devices=devices)


@main.delete("/devices/<int:device_id>")
def delete_device(device_id):
    device = Device.find_by_id(device_id)
    device.delete_from_db()
    return ""


# API BLUEPRINT


@api.get("/source/<int:source_id>/markdown")
def api_get_source_markdown(source_id):
    api_key = request.args.get("api_key")
    user_id = Device.find_by_key(api_key).user_id
    get_latest = request.args.get("get_latest", False)
    since = request.args.get("since", datetime.min)
    return get_markdown(source_id, user_id, get_latest=get_latest, since=since)


@api.post("/source/<int:source_id>/sync")
def create_sync_record(source_id):
    # TODO Update existing sync record if it exists and return the appropriate status code
    api_key = request.form.get("api_key")
    user_id = Device.find_by_key(api_key).user_id
    sync_record = SyncRecord(user_id=user_id, source_id=source_id)
    sync_record.add_to_db()
    return jsonify(sync_record)


@api.get("/sources")
def get_sources():
    # TODO Better parsing of args -- failure states
    api_key = request.args.get("api_key")
    user_id = Device.find_by_key(api_key).user_id
    sources = Source.get_sources_and_snippets(user_id)
    return jsonify(sources)
