import requests
from flask import Flask, render_template_string, request, redirect, url_for, flash

remote_app = Flask(__name__)
remote_app.secret_key = "remote_controller_secret"

# Point this to your main store's URL and API Key
MAIN_STORE_URL = "http://127.0.0.1:5000"
REMOTE_API_KEY = "nexus_remote_master_key_2026"
HEADERS = {"X-API-KEY": REMOTE_API_KEY}

REMOTE_HTML = """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Remote Admin Command Center (Port 5001)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #050811; color: #f8fafc; font-family: sans-serif; }
        .panel { background: rgba(17, 24, 39, 0.85); border: 1px solid rgba(56, 189, 248, 0.2); }
    </style>
</head>
<body class="min-h-screen p-6 md:p-10">
    <div class="max-w-6xl mx-auto space-y-8">

        <!-- Top Status Bar -->
        <div class="panel p-6 rounded-3xl flex flex-wrap justify-between items-center gap-4">
            <div>
                <span class="px-3 py-1 text-xs font-bold uppercase bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded-full">
                    🛰️ Standalone Remote Control Web (Port 5001)
                </span>
                <h1 class="text-2xl md:text-3xl font-extrabold mt-2">Remote Store Controller → {{ store_url }}</h1>
            </div>
            <a href="{{ store_url }}" target="_blank" class="px-5 py-2.5 rounded-xl bg-cyan-500 text-slate-950 font-bold text-sm hover:bg-cyan-400">
                Open Live Storefront ↗
            </a>
        </div>

        {% with messages = get_flashed_messages() %}
          {% if messages %}
            {% for m in messages %}
              <div class="p-4 rounded-2xl bg-cyan-500/20 border border-cyan-500/40 text-cyan-200 text-sm font-bold">{{ m }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <!-- Remote Video/Image Slider Uploader -->
        <div class="panel p-6 rounded-3xl">
            <h2 class="text-xl font-bold mb-4">🎞️ Remote Push: Video or Image Banner Slide</h2>
            <form action="/remote/add-slide" method="POST" enctype="multipart/form-data" class="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
                <div>
                    <label class="text-xs text-cyan-300 font-bold">Choose Video/Image from Gallery</label>
                    <input type="file" name="slide_file" accept="video/*,image/*" class="w-full mt-1 text-xs bg-slate-900 p-2 rounded-xl border border-slate-700">
                </div>
                <div>
                    <label class="text-xs text-slate-400">Or Direct Media URL</label>
                    <input type="url" name="media_url" placeholder="https://.../video.mp4" class="w-full mt-1 px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm">
                </div>
                <div class="flex gap-2">
                    <input type="text" name="caption" placeholder="Caption" value="Remote Promo" class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm">
                    <select name="animation_style" class="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs text-cyan-300 font-bold">
                        <option value="zoom-pan">Zoom Pan</option>
                        <option value="pulse-glow">Pulse Glow</option>
                    </select>
                </div>
                <button type="submit" class="py-2.5 px-4 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 font-bold text-sm">
                    Push Slide to Main Store
                </button>
            </form>

            <!-- Active Slides on Main Store -->
            <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mt-6">
                {% for s in state.slides %}
                <div class="relative h-24 rounded-xl overflow-hidden border border-slate-700 bg-black">
                    {% if s.media_type == 'video' %}
                        <video src="{{ store_url if s.media_url.startswith('/') else '' }}{{ s.media_url }}" autoplay loop muted class="w-full h-full object-cover"></video>
                    {% else %}
                        <img src="{{ store_url if s.media_url.startswith('/') else '' }}{{ s.media_url }}" class="w-full h-full object-cover">
                    {% endif %}
                    <form action="/remote/delete-slide/{{ s.id }}" method="POST" class="absolute top-1 right-1">
                        <button class="bg-rose-600 text-white text-[10px] px-2 py-0.5 rounded font-bold">✕</button>
                    </form>
                </div>
                {% endfor %}
            </div>
        </div>

        <!-- Remote Add Product & Remote Branding -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="lg:col-span-2 panel p-6 rounded-3xl">
                <h2 class="text-xl font-bold mb-4">📦 Remote Push: New Item Slot</h2>
                <form action="/remote/add-item" method="POST" enctype="multipart/form-data" class="space-y-3">
                    <div class="grid grid-cols-2 gap-3">
                        <input type="text" name="name" placeholder="Item Name *" required class="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm">
                        <input type="text" name="category" placeholder="Category *" required class="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm">
                    </div>
                    <div class="grid grid-cols-3 gap-3">
                        <input type="text" name="price" placeholder="$99.00 *" required class="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm">
                        <input type="number" name="stock" value="15" class="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm">
                        <input type="text" name="badge" value="Remote Drop" class="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm">
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                        <input type="file" name="item_file" accept="image/*" class="text-xs bg-slate-900 p-2 rounded-xl border border-slate-700">
                        <input type="url" name="image_url" placeholder="Or Image URL (https://...)" class="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm">
                    </div>
                    <input type="text" name="short_desc" placeholder="Short description *" required class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm">
                    <textarea name="full_specs" rows="2" placeholder="Full specs..." class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm"></textarea>
                    <button type="submit" class="px-6 py-2.5 rounded-xl bg-emerald-500 text-slate-950 font-extrabold text-sm">
                        Push Item to Storefront
                    </button>
                </form>
            </div>

            <div class="panel p-6 rounded-3xl h-fit">
                <h2 class="text-xl font-bold mb-4">⚡ Remote Branding Sync</h2>
                <form action="/remote/update-config" method="POST" class="space-y-3">
                    <input type="text" name="title" value="{{ state.config.title }}" class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm">
                    <input type="text" name="subtitle" value="{{ state.config.subtitle }}" class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm">
                    <input type="text" name="announcement" value="{{ state.config.announcement }}" class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm">
                    <button type="submit" class="w-full py-2.5 rounded-xl bg-indigo-500 font-bold text-sm">Sync Branding</button>
                </form>
            </div>
        </div>

        <!-- Remote Inventory List -->
        <div class="panel p-6 rounded-3xl">
            <h2 class="text-xl font-bold mb-4">🗂️ Live Store Inventory ({{ state.items|length }} Items)</h2>
            <div class="divide-y divide-slate-800 text-sm">
                {% for item in state.items %}
                <div class="py-3 flex justify-between items-center">
                    <div>
                        <span class="font-bold text-white">{{ item.name }}</span>
                        <span class="text-xs text-cyan-400 ml-2">{{ item.price }} ({{ item.stock }} slots)</span>
                    </div>
                    <form action="/remote/delete-item/{{ item.id }}" method="POST">
                        <button class="px-3 py-1 rounded-lg bg-rose-500/20 text-rose-300 hover:bg-rose-600 hover:text-white text-xs font-bold">
                            Remote Delete
                        </button>
                    </form>
                </div>
                {% endfor %}
            </div>
        </div>

    </div>
</body>
</html>
"""

@remote_app.route("/")
def dashboard():
    try:
        resp = requests.get(f"{MAIN_STORE_URL}/api/state", headers=HEADERS, timeout=5)
        state = resp.json()
    except Exception as e:
        state = {"config": {"title": "Offline", "subtitle": str(e), "announcement": ""}, "items": [], "slides": []}
        flash(f"Cannot reach Main Store at {MAIN_STORE_URL}. Make sure store_app.py is running!")
    return render_template_string(REMOTE_HTML, state=state, store_url=MAIN_STORE_URL)

@remote_app.route("/remote/add-slide", methods=["POST"])
def remote_add_slide():
    files = {}
    if "slide_file" in request.files and request.files["slide_file"].filename:
        f = request.files["slide_file"]
        files["slide_file"] = (f.filename, f.stream, f.mimetype)
    requests.post(f"{MAIN_STORE_URL}/api/add-slide", headers=HEADERS, data=request.form, files=files)
    flash("Slide pushed to main store!")
    return redirect(url_for("dashboard"))

@remote_app.route("/remote/delete-slide/<int:slide_id>", methods=["POST"])
def remote_delete_slide(slide_id):
    requests.post(f"{MAIN_STORE_URL}/api/delete-slide/{slide_id}", headers=HEADERS)
    flash("Slide removed remotely!")
    return redirect(url_for("dashboard"))

@remote_app.route("/remote/add-item", methods=["POST"])
def remote_add_item():
    files = {}
    if "item_file" in request.files and request.files["item_file"].filename:
        f = request.files["item_file"]
        files["item_file"] = (f.filename, f.stream, f.mimetype)
    requests.post(f"{MAIN_STORE_URL}/api/add-item", headers=HEADERS, data=request.form, files=files)
    flash("New item slot pushed to main store!")
    return redirect(url_for("dashboard"))

@remote_app.route("/remote/delete-item/<int:item_id>", methods=["POST"])
def remote_delete_item(item_id):
    requests.post(f"{MAIN_STORE_URL}/api/delete-item/{item_id}", headers=HEADERS)
    flash("Item deleted remotely!")
    return redirect(url_for("dashboard"))

@remote_app.route("/remote/update-config", methods=["POST"])
def remote_update_config():
    requests.post(f"{MAIN_STORE_URL}/api/update-config", headers=HEADERS, data=request.form)
    flash("Store branding synced remotely!")
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    remote_app.run(debug=True, port=5001)
