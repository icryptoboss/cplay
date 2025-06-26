from flask import Flask, request, jsonify, render_template, redirect, url_for
import base64
import os
import requests
import json
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Config
CLASSPLUS_TOKEN = "#"
CLASSPLUS_DOMAINS = [
    "media-cdn.classplusapp.com",
    "cdn-wl-assets.classplus.co",
    "media-aws.classplusapp.com",
    "classplusapp.com",
    "cpvod.testbook.com"
]
SIGNING_APIS = [
    "https://ugxclassplusapi.vercel.app/get/cp?url="
]

UPLOAD_FOLDER = "uploads"
RECENT_FILE = "recent.json"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Emojis
EMOJIS = ["🎯", "📘", "📚", "📺", "🧠", "🎓", "🔥", "🔑", "💡", "🌀", "📼", "🎬"]

# Helpers
def is_classplus_url(url):
    return any(domain in url for domain in CLASSPLUS_DOMAINS) and url.endswith(".m3u8")

def sign_with_classplus_token(url):
    try:
        headers = {'x-access-token': CLASSPLUS_TOKEN, 'User-Agent': 'Mobile-Android'}
        r = requests.get("https://api.classplusapp.com/cams/uploader/video/jw-signed-url",
                         params={"url": url}, headers=headers, timeout=10)
        data = r.json()
        return data.get("url")
    except Exception as e:
        print(f"[!] Token signing failed: {e}")
        return None

def sign_with_public_apis(url):
    for api in SIGNING_APIS:
        try:
            full_url = f"{api}{requests.utils.quote(url)}"
            r = requests.get(full_url, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=10)
            data = r.json()
            if data.get("status") and data.get("url"):
                return data["url"]
        except Exception as e:
            print(f"[!] Fallback signing failed: {e}")
    return None

def save_to_recent(title, url):
    entry = {"title": title, "url": url}

    try:
        if os.path.exists(RECENT_FILE):
            with open(RECENT_FILE, "r", encoding="utf-8") as f:
                recent = json.load(f)
        else:
            recent = []
    except:
        recent = []

    # Avoid duplicates
    recent = [item for item in recent if item["url"] != url]

    # Add emoji
    entry["emoji"] = EMOJIS[hash(url) % len(EMOJIS)]
    recent.insert(0, entry)
    recent = recent[:20]

    with open(RECENT_FILE, "w", encoding="utf-8") as f:
        json.dump(recent, f, indent=2)

# Routes
@app.route("/")
def home():
    # Load recent videos
    try:
        with open(RECENT_FILE, "r", encoding="utf-8") as f:
            recent = json.load(f)[:10]
    except:
        recent = []

    # Add emoji fallback
    for item in recent:
        if "emoji" not in item:
            item["emoji"] = EMOJIS[hash(item["url"]) % len(EMOJIS)]

    # Load txt playlists
    txt_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith(".txt")][:10]
    return render_template("index.html", recent_videos=recent, txt_playlists=txt_files)

@app.route("/recent")
def recent():
    try:
        with open(RECENT_FILE, "r", encoding="utf-8") as f:
            recent = json.load(f)
    except:
        recent = []

    for item in recent:
        if "emoji" not in item:
            item["emoji"] = EMOJIS[hash(item["url"]) % len(EMOJIS)]

    txt_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith(".txt")]
    return render_template("recent.html", recent_videos=recent, txt_playlists=txt_files)

@app.route("/get/cp")
def get_cp():
    raw_url = request.args.get("url")
    encrypted = request.args.get("encrypted", "false").lower() == "true"

    if not raw_url:
        return jsonify({"status": False, "message": "No URL provided"})

    if encrypted:
        try:
            raw_url = base64.urlsafe_b64decode(raw_url + "==").decode()
        except:
            return jsonify({"status": False, "message": "Invalid encrypted URL"})

    if not is_classplus_url(raw_url):
        return jsonify({"status": False, "message": "Invalid or unsupported video URL"})

    if "cdn-wl-assets.classplus.co" in raw_url:
        return jsonify({"status": True, "url": raw_url})

    signed = sign_with_classplus_token(raw_url)
    if signed:
        return jsonify({"status": True, "url": signed})

    fallback_signed = sign_with_public_apis(raw_url)
    if fallback_signed:
        return jsonify({"status": True, "url": fallback_signed})

    return jsonify({"status": False, "message": "Failed to sign the video URL."})

@app.route("/player")
def player():
    raw_url = request.args.get("url")
    encrypted = request.args.get("encrypted", "false").lower() == "true"
    title = request.args.get("title")

    if not raw_url:
        return redirect(url_for('home'))

    try:
        url = base64.urlsafe_b64decode(raw_url + "==").decode() if encrypted else raw_url
    except:
        url = raw_url

    if not title:
        parts = url.split("/")
        title = parts[-2] if len(parts) >= 2 else "Untitled Video"

    save_to_recent(title.strip(), url.strip())
    return render_template("player.html")

@app.route("/upload_playlist", methods=["POST"])
def upload_playlist():
    file = request.files.get("playlist_file")
    if file and file.filename.endswith(".txt"):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        return redirect(url_for("show_playlist", filename=filename))
    return "Only .txt files are allowed", 400

@app.route("/playlist/<filename>")
def show_playlist(filename):
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    entries = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if ":" in line:
                    title, url = line.strip().split(":", 1)
                    entries.append({"title": title.strip(), "url": url.strip()})
    except Exception as e:
        return f"Error reading playlist: {e}", 500

    return render_template("playlist.html", entries=entries)

# Run
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)