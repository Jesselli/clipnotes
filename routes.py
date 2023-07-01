import uuid

from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

import models as db
from services.time_str import get_time_from_url, get_url_without_time
from services.markdown import generate_source_markdown

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
    sources = db.Source.get_user_sources_snippets(current_user.id)
    queue = db.Snippet.get_user_queue(current_user.id)
    return render_template(
        "index.html",
        sources=sources,
        queue=queue,
    )


@main.post("/login")
def login_post():
    if request.form:
        username = request.form["email"]
        password = request.form["password"]
        user = db.User.find_by_email(username)
        if user and check_password_hash(user.password, password):
            login_user(user)
            response = Response("Logged in", 200)
            response.headers["HX-Redirect"] = "/"
            return response

    flash("Invalid credentials.", "danger")
    return render_template("partials/login_form.html")


# TODO Cleanup the UserSettings code in routes.py
@main.get("/settings")
@login_required
def get_settings():
    user_id = current_user.id
    user_settings = db.UserSettings.find_by_user_id(user_id)
    settings = {}
    for user_setting in user_settings:
        settings[user_setting.name] = user_setting.value
    return render_template("settings.html", settings=settings)


@main.post("/settings")
def post_settings():
    # TODO Re-implement settings page
    return ""


@main.post("/register")
def register_user():
    password = request.form["password"]
    password_confirmation = request.form["confirm_password"]
    if password != password_confirmation:
        flash("Passwords must match.", "danger")
        return render_template("partials/register_form.html")
    email = request.form["email"]
    password_hash = generate_password_hash(password)

    user = db.User.find_by_email(email)
    if user:
        flash("User already exists.", "danger")
        return render_template("partials/register_form.html")

    db.User.create(email, password_hash)
    flash("User created. Please login.", "success")
    response = Response("success", 200)
    response.headers["HX-Redirect"] = "/login"
    return response


@main.get("/source/<int:source_id>/markdown")
@login_required
def get_source_markdown(source_id):
    user_id = current_user.id
    return generate_source_markdown(source_id, user_id)


@main.delete("/source/<int:source_id>")
def delete_source(source_id):
    source = db.Source.find_by_id(source_id)
    snippets = source.snippets
    for snippet in snippets:
        snippet.delete_from_db()
    source.delete_from_db()
    return ""


@main.put("/snippet/<int:snippet_id>")
def update_snippet(snippet_id):
    text = request.form.get("text")
    snippet = db.Snippet.find_by_id(snippet_id)
    snippet.update_text(text)
    return text


@main.delete("/snippet/<int:snippet_id>")
def delete_snippet(snippet_id):
    snippet = db.Snippet.find_by_id(snippet_id)
    snippet.delete_from_db()
    return ""


@main.get("/devices")
@login_required
def get_devices():
    if current_user and current_user.is_authenticated:
        user_id = current_user.id

    devices = db.Device.find_devices_for_user(user_id)
    return render_template("devices.html", devices=devices)


@main.post("/devices")
def add_device():
    user_id = current_user.id
    if request.form:
        name = request.form.get("device_name")
    if db.Device.find_by_name(user_id, name):
        return "Device already exists", 400

    device_key = uuid.uuid4().hex
    device_key_hashed = generate_password_hash(device_key)
    new_device = db.Device(
        device_name=name,
        user_id=current_user.id,
        device_key=device_key_hashed,
        last_four=f"{'*'*20}{device_key[-4:]}",
    )
    new_device.add_to_db()
    return render_template("partials/device_input.html", device_key=device_key)


@main.get("/devices/table")
def get_device_table():
    user_id = current_user.id
    devices = db.Device.find_devices_for_user(user_id)
    return render_template("partials/device_table.html", devices=devices)


@main.delete("/devices/<int:device_id>")
def delete_device(device_id):
    device = db.Device.find_by_id(device_id)
    device.delete_from_db()
    return ""


@main.post("/enqueue")
def enqueue():
    # TODO Consider changing the UI to start/end time fields
    url = request.form.get("url")
    time = get_time_from_url(url)
    source_url = get_url_without_time(url)
    duration = request.form.get("duration", type=int)
    start_time = request.form.get("start")
    end_time = request.form.get("end")
    if duration:
        start_time = time - (duration // 2)
        end_time = time + (duration // 2)
    user_id = current_user.id
    source = db.Source.add(source_url)
    db.Snippet.add(user_id, source.id, start_time, end_time)
    queue = db.Snippet.get_user_queue(user_id)
    return render_template("partials/queue.html", queue=queue)


@main.get("/queue/<queue_id>")
def get_queue_item(queue_id):
    queue_item = db.Snippet.find_by_id(queue_id)
    return render_template("partials/queue_item.html", queue_item=queue_item)


# API BLUEPRINT


@api.get("/source/<int:source_id>/markdown")
def api_get_source_markdown(source_id):
    api_key = request.headers.get("X-Api-Key")

    user_id = db.Device.find_by_key(api_key).user_id
    get_latest = request.args.get("latest", default=False, type=bool)
    exclusions = request.args.get("exclude", [])
    return generate_source_markdown(
        source_id, user_id, latest=get_latest, exclusions=exclusions
    )


@api.post("/source/<int:source_id>/sync")
def api_update_sync(source_id):
    api_key = request.headers.get("X-Api-Key")
    user_id = db.Device.find_by_key(api_key).user_id
    sync_record = db.SyncRecord.find_by_user_source(user_id, source_id)
    if sync_record:
        sync_record.update_sync_time()
    else:
        sync_record = db.SyncRecord(user_id=user_id, source_id=source_id)
        sync_record.add_to_db()
    return jsonify(sync_record)


@api.get("/sources")
def api_get_sources():
    # TODO Better parsing of args -- failure states
    api_key = request.headers.get("X-Api-Key")
    user_id = db.Device.find_by_key(api_key).user_id
    sources = db.Source.get_user_sources_snippets(user_id)
    return jsonify(sources)


@api.post("/enqueue")
def api_enqueue():
    # TODO Better parsing of args -- failure states
    api_key = request.headers.get("X-Api-Key")
    url = request.args.get("url")
    source_url = get_url_without_time(url)
    start = request.args.get("start", type=int)
    end = request.args.get("end", type=int)
    user_id = db.Device.find_by_key(api_key).user_id
    source = db.Source.add(source_url)
    db.Snippet.add(user_id, source.id, start, end)
    return "Success", 200
