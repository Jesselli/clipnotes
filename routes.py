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

from models import Device, Snippet, Source, SyncRecord, User
from services import source_processors
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
    sources = Source.get_user_sources_snippets(current_user.id)
    return render_template("index.html", sources=sources)


@main.post("/login")
def login_post():
    if request.form:
        username = request.form["email"]
        password = request.form["password"]
        user = User.find_by_email(username)
        if user and check_password_hash(user.password, password):
            login_user(user)
            response = Response("Logged in", 200)
            response.headers["HX-Redirect"] = "/"
            return response

    style = "danger"
    message = "Invalid credentials."
    template = "partials/login_form.html"
    return render_template(template, message=message, style=style)


@main.post("/register")
def register_user():
    password = request.form["password"]
    password_confirmation = request.form["confirm_password"]
    if password != password_confirmation:
        style = "danger"
        message = "Passwords do not match."
        template = "partials/register_form.html"
        return render_template(template, message=message, style=style)
    email = request.form["email"]
    password_hash = generate_password_hash(password)

    user = User.find_by_email(email)
    if user:
        style = "danger"
        message = "User already exists."
        template = "partials/register_form.html"
        return render_template(template, message=message, style=style)

    User.create(email, password_hash)
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
    source = Source.find_by_id(source_id)
    snippets = source.snippets
    for snippet in snippets:
        snippet.delete_from_db()
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
        sources = Source.get_user_sources_snippets(current_user.id)
        return render_template("partials/sources.html", sources=sources)
    else:
        return "Not authenticated"


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
        new_device = Device(
            device_name=name, user_id=current_user.id, device_key=device_key
        )
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
    api_key = request.headers.get("X-Api-Key")
    user_id = Device.find_by_key(api_key).user_id
    get_latest = request.args.get("latest", default=False, type=bool)
    exclusions = request.args.get("exclude", [])
    return generate_source_markdown(
        source_id, user_id, latest=get_latest, exclusions=exclusions
    )


@api.post("/source/<int:source_id>/sync")
def api_update_sync(source_id):
    api_key = request.headers.get("X-Api-Key")
    user_id = Device.find_by_key(api_key).user_id
    sync_record = SyncRecord.find_by_user_source(user_id, source_id)
    if sync_record:
        sync_record.update_sync_time()
    else:
        sync_record = SyncRecord(user_id=user_id, source_id=source_id)
        sync_record.add_to_db()
    return jsonify(sync_record)


@api.get("/sources")
def api_get_sources():
    # TODO Better parsing of args -- failure states
    api_key = request.headers.get("X-Api-Key")
    user_id = Device.find_by_key(api_key).user_id
    sources = Source.get_user_sources_snippets(user_id)
    return jsonify(sources)


@api.post("/enqueue")
def api_enqueue():
    api_key = request.headers.get("X-Api-Key")
    url = request.args.get("url")
    time = request.args.get("time", 0)
    duration = request.args.get("duration", 60, type=int)
    user_id = Device.find_by_key(api_key).user_id
    source_processors.add_to_queue(url, user_id, time, duration)
    return "Success", 200
