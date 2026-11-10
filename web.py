import os
import time
import sqlite3
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "super_secret_nexus_key_change_in_prod"
DB_NAME = "store_vault.db"

# Secret API Key so your second Admin Web Script can control this store remotely
REMOTE_API_KEY = "nexus_remote_master_key_2026"

# Gallery upload folder setup
UPLOAD_FOLDER = os.path.join("static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "mp4", "webm", "mov"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def detect_media_type(path_or_url):
    ext = path_or_url.split("?")[0].rsplit(".", 1)[-1].lower()
    return "video" if ext in {"mp4", "webm", "mov"} else "image"

# ---------------------------------------------------------
# DATABASE SETUP & INITIALIZATION
# ---------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            title TEXT,
            subtitle TEXT,
            banner_url TEXT,
            announcement TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price TEXT NOT NULL,
            stock INTEGER DEFAULT 10,
            badge TEXT DEFAULT 'Featured',
            rating REAL DEFAULT 5.0,
            image_url TEXT NOT NULL,
            short_desc TEXT,
            full_specs TEXT
        )
    """)

    # Animated Video & Image Banner Slider Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS banner_slides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_url TEXT NOT NULL,
            media_type TEXT DEFAULT 'image',
            caption TEXT DEFAULT 'Featured Highlight',
            animation_style TEXT DEFAULT 'zoom-pan'
        )
    """)

    # Seed default config
    c.execute("SELECT COUNT(*) FROM config")
    if c.fetchone()[0] == 0:
        c.execute("""
            INSERT INTO config (id, title, subtitle, banner_url, announcement)
            VALUES (1, 'NEXUS // PRO VAULT', 'Next-Gen Digital & Physical Showcase',
                    'https://telegraphoto.online/images/7bee2a67-862e-434b-aefb-77c081be31e7.jpg',
                    '⚡ Welcome! Sign in as admin (admin / admin123) or use the Remote Admin Panel on Port 5001.')
        """)

    # Seed default Banner Slides (1 image + 1 sample HD video slide)
    c.execute("SELECT COUNT(*) FROM banner_slides")
    if c.fetchone()[0] == 0:
        sample_slides = [
            (
                "https://telegraphoto.online/images/7bee2a67-862e-434b-aefb-77c081be31e7.jpg",
                "image",
                "Exclusive Collector Drop",
                "zoom-pan"
            ),
            (
                "https://assets.mixkit.co/videos/preview/mixkit-futuristic-HUD-interface-in-a-dark-room-42514-large.mp4",
                "video",
                "Next-Gen Cybernetics & Pro Gear",
                "fade-scale"
            )
        ]
        c.executemany("""
            INSERT INTO banner_slides (media_url, media_type, caption, animation_style)
            VALUES (?, ?, ?, ?)
        """, sample_slides)

    # Seed default Admin account (admin / admin123)
    c.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if c.fetchone()[0] == 0:
        c.execute("""
            INSERT INTO users (username, password_hash, is_admin)
            VALUES (?, ?, 1)
        """, ("admin", generate_password_hash("admin123")))

    # Seed initial items
    c.execute("SELECT COUNT(*) FROM items")
    if c.fetchone()[0] == 0:
        sample_items = [
            (
                "Custom Featured Edition",
                "Exclusive",
                "$149.99",
                5,
                "Hot Drop",
                4.9,
                "https://telegraphoto.online/images/7bee2a67-862e-434b-aefb-77c081be31e7.jpg",
                "Limited-edition custom showcase item initialized with your image link.",
                "• High-Resolution Finish\n• Verified Authentic Serial\n• Instant Worldwide Dispatch\n• 2-Year Protection Warranty"
            ),
            (
                "Aether Pro Wireless Headset",
                "Audio",
                "$299.00",
                14,
                "Best Seller",
                4.8,
                "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=900&q=80",
                "Studio-grade spatial acoustics with carbon fiber headband and 40-hour battery.",
                "• 50mm Titanium Drivers\n• Active Noise Cancellation\n• Dual-Device Bluetooth 5.3\n• Detachable Broadcast Mic"
            ),
            (
                "Krono 75% Custom Keyboard",
                "Gear",
                "$189.00",
                8,
                "New",
                4.7,
                "https://images.unsplash.com/photo-1511467687858-23d96c32e4ae?auto=format&fit=crop&w=900&q=80",
                "CNC machined aluminum body with gasket mount and hot-swappable switches.",
                "• CNC Anodized Frame\n• PBT Double-Shot Keycaps\n• Per-Key South-Facing RGB\n• Tri-Mode Wireless Connection"
            )
        ]
        c.executemany("""
            INSERT INTO items (name, category, price, stock, badge, rating, image_url, short_desc, full_specs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_items)

    conn.commit()
    conn.close()

# ---------------------------------------------------------
# AUTHENTICATION DECORATORS
# ---------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin privileges required to access that page.", "error")
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function

def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        key = request.headers.get("X-API-KEY") or request.form.get("api_key")
        if key != REMOTE_API_KEY:
            return jsonify({"error": "Unauthorized Remote API Key"}), 401
        return f(*args, **kwargs)
    return decorated_function

def save_uploaded_file(file_obj):
    if file_obj and file_obj.filename and allowed_file(file_obj.filename):
        filename = f"{int(time.time())}_{secure_filename(file_obj.filename)}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file_obj.save(save_path)
        return f"/static/uploads/{filename}"
    return None

# ---------------------------------------------------------
# SHARED HTML LAYOUT
# ---------------------------------------------------------
BASE_HTML = """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ config.title }}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: #070a12; color: #f1f5f9; }
        .glass { background: rgba(15, 23, 42, 0.78); backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.08); }
        .card-glow:hover { box-shadow: 0 0 35px -5px rgba(6, 182, 212, 0.25); border-color: rgba(6, 182, 212, 0.45); }

        /* Animated Slider Keyframes */
        @keyframes kenBurnsZoom {
            0% { transform: scale(1) translate(0, 0); }
            50% { transform: scale(1.12) translate(-1%, -1%); }
            100% { transform: scale(1.04) translate(1%, 0); }
        }
        @keyframes pulseGlow {
            0%, 100% { filter: brightness(0.55) saturate(1.1); }
            50% { filter: brightness(0.7) saturate(1.35); }
        }
        .anim-zoom-pan { animation: kenBurnsZoom 14s ease-in-out infinite alternate; }
        .anim-pulse-glow { animation: pulseGlow 6s ease-in-out infinite; }
    </style>
</head>
<body class="min-h-screen flex flex-col selection:bg-cyan-500 selection:text-black">

    {% if config.announcement %}
    <div class="bg-gradient-to-r from-cyan-600/20 via-indigo-600/20 to-cyan-600/20 border-b border-cyan-500/20 text-center py-2 px-4 text-xs md:text-sm text-cyan-200 font-medium">
        {{ config.announcement }}
    </div>
    {% endif %}

    <nav class="sticky top-0 z-40 glass px-6 py-4">
        <div class="max-w-7xl mx-auto flex flex-wrap justify-between items-center gap-4">
            <a href="{{ url_for('home') }}" class="flex items-center gap-2 text-2xl font-extrabold tracking-tight">
                <span class="w-3 h-3 rounded-full bg-cyan-400 animate-pulse"></span>
                <span class="bg-gradient-to-r from-white via-cyan-300 to-indigo-400 bg-clip-text text-transparent">
                    {{ config.title }}
                </span>
            </a>

            <div class="flex items-center gap-3">
                <a href="{{ url_for('home') }}" class="px-3 py-2 text-sm text-slate-300 hover:text-white transition">Storefront</a>

                {% if session.get('user_id') %}
                    {% if session.get('is_admin') %}
                    <a href="{{ url_for('admin_dashboard') }}" 
                       class="px-4 py-2 text-sm font-bold rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 text-white shadow-lg shadow-cyan-500/20 hover:opacity-95 transition">
                        ⚙️ Local Admin
                    </a>
                    {% endif %}
                    <div class="flex items-center gap-3 pl-2 border-l border-slate-800">
                        <span class="text-xs px-2.5 py-1 rounded-full bg-slate-800 text-cyan-300 border border-slate-700">
                            👤 {{ session.get('username') }}
                        </span>
                        <a href="{{ url_for('logout') }}" class="text-xs text-rose-400 hover:text-rose-300 font-semibold">Logout</a>
                    </div>
                {% else %}
                    <a href="{{ url_for('login_page') }}" class="px-4 py-2 text-sm font-semibold rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 transition">
                        Login
                    </a>
                    <a href="{{ url_for('register_page') }}" class="px-4 py-2 text-sm font-bold rounded-xl bg-cyan-500 text-slate-950 hover:bg-cyan-400 transition">
                        Register
                    </a>
                {% endif %}
            </div>
        </div>
    </nav>

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        <div class="max-w-7xl w-full mx-auto px-6 pt-4 space-y-2">
          {% for category, msg in messages %}
            <div class="px-4 py-3 rounded-xl text-sm font-semibold flex justify-between items-center
                        {% if category == 'error' %}bg-rose-500/20 text-rose-200 border border-rose-500/40
                        {% else %}bg-emerald-500/20 text-emerald-200 border border-emerald-500/40{% endif %}">
                <span>{{ msg }}</span>
            </div>
          {% endfor %}
        </div>
      {% endif %}
    {% endwith %}

    <div class="flex-grow">{{ content | safe }}</div>

    <footer class="border-t border-slate-800/80 py-8 px-6 text-center text-xs text-slate-500 mt-16">
        <p>{{ config.title }} • Animated Video Slider & Remote Admin API Enabled</p>
    </footer>
</body>
</html>
"""

# ---------------------------------------------------------
# STOREFRONT ROUTE (WITH VIDEO & ANIMATION SLIDER)
# ---------------------------------------------------------
@app.route("/")
def home():
    conn = get_db()
    config = conn.execute("SELECT * FROM config WHERE id = 1").fetchone()
    slides = conn.execute("SELECT * FROM banner_slides ORDER BY id DESC").fetchall()
    q = request.args.get("q", "").strip()
    cat = request.args.get("cat", "").strip()

    query = "SELECT * FROM items WHERE 1=1"
    params = []
    if q:
        query += " AND (name LIKE ? OR short_desc LIKE ? OR category LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if cat:
        query += " AND category = ?"
        params.append(cat)
    query += " ORDER BY id DESC"

    items = conn.execute(query, params).fetchall()
    categories = [r["category"] for r in conn.execute("SELECT DISTINCT category FROM items").fetchall()]
    conn.close()

    store_content = render_template_string("""
    <!-- Animated Video & Image Hero Slider Banner -->
    <header class="relative w-full h-[380px] md:h-[460px] overflow-hidden border-b border-slate-800 bg-black">
        <div id="heroSlider">
            {% for slide in slides %}
            <div class="slide-item absolute inset-0 transition-all duration-1000 ease-out {% if loop.index0 == 0 %}opacity-100 scale-100 z-10{% else %}opacity-0 scale-105 z-0 pointer-events-none{% endif %}"
                 data-caption="{{ slide.caption }}">
                {% if slide.media_type == 'video' %}
                    <video src="{{ slide.media_url }}" autoplay loop muted playsinline
                           class="w-full h-full object-cover object-center brightness-50 {% if slide.animation_style == 'pulse-glow' %}anim-pulse-glow{% endif %}"></video>
                {% else %}
                    <img src="{{ slide.media_url }}" alt="Slide"
                         class="w-full h-full object-cover object-center brightness-50 {% if slide.animation_style == 'zoom-pan' %}anim-zoom-pan{% elif slide.animation_style == 'pulse-glow' %}anim-pulse-glow{% endif %}">
                {% endif %}
            </div>
            {% endfor %}
        </div>

        <div class="absolute inset-0 bg-gradient-to-t from-[#070a12] via-[#070a12]/30 to-transparent z-20 pointer-events-none"></div>

        <!-- Overlay Text & Controls -->
        <div class="absolute inset-0 max-w-7xl mx-auto px-6 flex flex-col justify-end pb-12 z-30">
            <div class="flex items-center gap-2 mb-3">
                <span class="px-3 py-1 text-xs font-bold uppercase tracking-widest bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 rounded-full">
                    Live Showcase
                </span>
                <span id="slideCaptionBadge" class="px-3 py-1 text-xs font-semibold bg-white/10 text-white rounded-full backdrop-blur-md">
                    {{ slides[0].caption if slides else 'Featured' }}
                </span>
            </div>
            <h1 class="text-4xl md:text-6xl font-extrabold tracking-tight text-white drop-shadow-lg">
                {{ config.title }}
            </h1>
            <p class="text-slate-300 text-base md:text-lg mt-2 max-w-2xl">
                {{ config.subtitle }}
            </p>

            <!-- Slider Navigation Dots & Arrows -->
            {% if slides|length > 1 %}
            <div class="flex items-center gap-3 mt-6">
                <button onclick="changeSlide(-1)" class="w-9 h-9 rounded-full glass flex items-center justify-center text-white hover:bg-cyan-500 hover:text-black transition">❮</button>
                <div class="flex gap-2" id="sliderDots">
                    {% for slide in slides %}
                    <button onclick="goToSlide({{ loop.index0 }})"
                            class="dot-btn h-2.5 rounded-full transition-all duration-300 {% if loop.index0 == 0 %}w-8 bg-cyan-400{% else %}w-2.5 bg-slate-600{% endif %}"></button>
                    {% endfor %}
                </div>
                <button onclick="changeSlide(1)" class="w-9 h-9 rounded-full glass flex items-center justify-center text-white hover:bg-cyan-500 hover:text-black transition">❯</button>
            </div>
            {% endif %}
        </div>
    </header>

    <!-- Search & Category Filter Bar -->
    <section class="max-w-7xl mx-auto px-6 pt-8">
        <div class="glass p-4 rounded-2xl flex flex-col md:flex-row justify-between items-center gap-4">
            <form method="GET" action="{{ url_for('home') }}" class="flex w-full md:w-96 gap-2">
                <input type="text" name="q" value="{{ q }}" placeholder="Search items, categories..." 
                       class="w-full px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white focus:outline-none focus:border-cyan-400">
                <button type="submit" class="px-4 py-2 rounded-xl bg-cyan-500 text-slate-950 font-bold text-sm hover:bg-cyan-400">
                    Search
                </button>
            </form>

            <div class="flex flex-wrap gap-2 items-center">
                <a href="{{ url_for('home') }}" 
                   class="px-3 py-1.5 rounded-lg text-xs font-bold transition {% if not current_cat %}bg-cyan-500 text-slate-950{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    All Items
                </a>
                {% for c in categories %}
                <a href="{{ url_for('home', cat=c) }}" 
                   class="px-3 py-1.5 rounded-lg text-xs font-bold transition {% if current_cat == c %}bg-cyan-500 text-slate-950{% else %}bg-slate-800 text-slate-300 hover:bg-slate-700{% endif %}">
                    {{ c }}
                </a>
                {% endfor %}
            </div>
        </div>
    </section>

    <!-- Product Grid -->
    <main class="max-w-7xl mx-auto px-6 py-10">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {% for item in items %}
            <div class="glass card-glow rounded-2xl overflow-hidden flex flex-col justify-between transition duration-300 group">
                <div>
                    <div class="h-56 w-full bg-slate-900 relative overflow-hidden">
                        <img src="{{ item.image_url }}" alt="{{ item.name }}" 
                             class="w-full h-full object-cover group-hover:scale-110 transition duration-500">
                        <span class="absolute top-3 left-3 px-2.5 py-1 text-[11px] font-bold uppercase rounded-md bg-black/75 text-cyan-300 backdrop-blur-md border border-cyan-500/30">
                            {{ item.badge }}
                        </span>
                        <span class="absolute top-3 right-3 px-2.5 py-1 text-xs font-bold rounded-md bg-black/75 text-amber-400 backdrop-blur-md">
                            ★ {{ item.rating }}
                        </span>
                    </div>

                    <div class="p-5">
                        <div class="text-xs font-semibold text-indigo-400 uppercase tracking-wider">{{ item.category }}</div>
                        <h3 class="text-lg font-bold text-white mt-1 line-clamp-1">{{ item.name }}</h3>
                        <p class="text-slate-400 text-xs mt-2 line-clamp-2 leading-relaxed">{{ item.short_desc }}</p>
                    </div>
                </div>

                <div class="p-5 pt-3 border-t border-slate-800/80 flex items-center justify-between">
                    <div>
                        <div class="text-xl font-extrabold text-cyan-400">{{ item.price }}</div>
                        <div class="text-[11px] {% if item.stock > 0 %}text-emerald-400{% else %}text-rose-400{% endif %}">
                            {% if item.stock > 0 %}{{ item.stock }} in stock{% else %}Out of Stock{% endif %}
                        </div>
                    </div>
                    <button onclick='openDetails({{ item | tojson }})'
                            class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-cyan-500 hover:text-slate-950 text-xs font-bold transition">
                        Inspect Details →
                    </button>
                </div>
            </div>
            {% endfor %}
        </div>
    </main>

    <!-- Product Details Modal -->
    <div id="detailsModal" class="hidden fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="glass rounded-3xl max-w-2xl w-full overflow-hidden border border-slate-700 shadow-2xl">
            <div class="grid grid-cols-1 md:grid-cols-2">
                <div class="h-64 md:h-auto bg-slate-950">
                    <img id="modalImg" src="" alt="" class="w-full h-full object-cover">
                </div>
                <div class="p-6 flex flex-col justify-between">
                    <div>
                        <div class="flex justify-between items-center">
                            <span id="modalCategory" class="text-xs font-bold uppercase tracking-widest text-cyan-400"></span>
                            <span id="modalRating" class="text-xs font-bold text-amber-400"></span>
                        </div>
                        <h3 id="modalTitle" class="text-2xl font-extrabold text-white mt-1"></h3>
                        <div id="modalPrice" class="text-2xl font-black text-cyan-400 mt-2"></div>
                        <p id="modalDesc" class="text-xs text-slate-300 mt-3 leading-relaxed"></p>
                        <div class="mt-4 pt-3 border-t border-slate-800">
                            <div class="text-xs font-bold text-slate-400 uppercase mb-1">Full Specifications & Slots:</div>
                            <pre id="modalSpecs" class="text-xs text-slate-300 whitespace-pre-wrap font-sans leading-relaxed"></pre>
                        </div>
                    </div>
                    <div class="mt-6 flex justify-between items-center pt-4 border-t border-slate-800">
                        <span id="modalStock" class="text-xs font-bold text-emerald-400"></span>
                        <button onclick="document.getElementById('detailsModal').classList.add('hidden')" 
                                class="px-5 py-2 rounded-xl bg-cyan-500 text-slate-950 font-bold text-xs hover:bg-cyan-400">
                            Close Preview
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Animated Video & Image Slider Controller
        const slides = document.querySelectorAll('.slide-item');
        const dots = document.querySelectorAll('.dot-btn');
        const captionBadge = document.getElementById('slideCaptionBadge');
        let currentSlide = 0;
        let slideTimer = null;

        function showSlide(index) {
            if (slides.length <= 1) return;
            slides[currentSlide].classList.remove('opacity-100', 'scale-100', 'z-10');
            slides[currentSlide].classList.add('opacity-0', 'scale-105', 'z-0', 'pointer-events-none');
            if (dots[currentSlide]) {
                dots[currentSlide].classList.remove('w-8', 'bg-cyan-400');
                dots[currentSlide].classList.add('w-2.5', 'bg-slate-600');
            }

            currentSlide = (index + slides.length) % slides.length;

            slides[currentSlide].classList.remove('opacity-0', 'scale-105', 'z-0', 'pointer-events-none');
            slides[currentSlide].classList.add('opacity-100', 'scale-100', 'z-10');
            if (dots[currentSlide]) {
                dots[currentSlide].classList.remove('w-2.5', 'bg-slate-600');
                dots[currentSlide].classList.add('w-8', 'bg-cyan-400');
            }
            if (captionBadge) {
                captionBadge.innerText = slides[currentSlide].getAttribute('data-caption') || 'Featured';
            }
        }

        function changeSlide(step) {
            showSlide(currentSlide + step);
            resetTimer();
        }

        function goToSlide(index) {
            showSlide(index);
            resetTimer();
        }

        function resetTimer() {
            if (slideTimer) clearInterval(slideTimer);
            if (slides.length > 1) {
                slideTimer = setInterval(() => showSlide(currentSlide + 1), 6000);
            }
        }
        resetTimer();

        function openDetails(item) {
            document.getElementById('modalImg').src = item.image_url;
            document.getElementById('modalCategory').innerText = item.category + ' • ' + item.badge;
            document.getElementById('modalRating').innerText = '★ ' + item.rating + ' / 5.0';
            document.getElementById('modalTitle').innerText = item.name;
            document.getElementById('modalPrice').innerText = item.price;
            document.getElementById('modalDesc').innerText = item.short_desc;
            document.getElementById('modalSpecs').innerText = item.full_specs || 'Standard verified package.';
            document.getElementById('modalStock').innerText = item.stock > 0 ? (item.stock + ' Slots Available') : 'Sold Out';
            document.getElementById('detailsModal').classList.remove('hidden');
        }
    </script>
    """, config=config, slides=slides, items=[dict(ix) for ix in items], categories=categories, q=q, current_cat=cat)

    return render_template_string(BASE_HTML, config=config, content=store_content)

# ---------------------------------------------------------
# LOGIN & REGISTER ROUTES
# ---------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login_page():
    conn = get_db()
    config = conn.execute("SELECT * FROM config WHERE id = 1").fetchone()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = bool(user["is_admin"])
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for("admin_dashboard" if user["is_admin"] else "home"))
        else:
            flash("Invalid username or password.", "error")
            return redirect(url_for("login_page"))

    conn.close()
    login_html = """
    <div class="max-w-md mx-auto px-6 py-16">
        <div class="glass p-8 rounded-3xl border border-slate-800 shadow-2xl">
            <h2 class="text-2xl font-extrabold text-white">Sign In</h2>
            <p class="text-xs text-slate-400 mt-1">Default Admin: <code class="text-cyan-400">admin</code> / <code class="text-cyan-400">admin123</code></p>
            <form method="POST" class="space-y-4 mt-6">
                <div>
                    <label class="text-xs font-semibold text-slate-300">Username</label>
                    <input type="text" name="username" required class="w-full mt-1 px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white">
                </div>
                <div>
                    <label class="text-xs font-semibold text-slate-300">Password</label>
                    <input type="password" name="password" required class="w-full mt-1 px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white">
                </div>
                <button type="submit" class="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 text-white font-bold">
                    Login to Account
                </button>
            </form>
        </div>
    </div>
    """
    return render_template_string(BASE_HTML, config=config, content=login_html)

@app.route("/register", methods=["GET", "POST"])
def register_page():
    conn = get_db()
    config = conn.execute("SELECT * FROM config WHERE id = 1").fetchone()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        make_admin = 1 if request.form.get("is_admin") == "on" else 0
        try:
            conn.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
                         (username, generate_password_hash(password), make_admin))
            conn.commit()
            conn.close()
            flash("Account registered! You can now log in.", "success")
            return redirect(url_for("login_page"))
        except sqlite3.IntegrityError:
            conn.close()
            flash("Username already taken.", "error")
            return redirect(url_for("register_page"))

    conn.close()
    reg_html = """
    <div class="max-w-md mx-auto px-6 py-16">
        <div class="glass p-8 rounded-3xl border border-slate-800 shadow-2xl">
            <h2 class="text-2xl font-extrabold text-white">Create Account</h2>
            <form method="POST" class="space-y-4 mt-6">
                <input type="text" name="username" placeholder="Username" required class="w-full px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white">
                <input type="password" name="password" placeholder="Password" required class="w-full px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white">
                <label class="flex items-center gap-2 text-xs text-slate-300">
                    <input type="checkbox" name="is_admin"> Grant Admin Access
                </label>
                <button type="submit" class="w-full py-3 rounded-xl bg-cyan-500 text-slate-950 font-bold">Create Account</button>
            </form>
        </div>
    </div>
    """
    return render_template_string(BASE_HTML, config=config, content=reg_html)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# ---------------------------------------------------------
# LOCAL ADMIN DASHBOARD (WITH GALLERY SLIDER UPLOADER)
# ---------------------------------------------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    config = conn.execute("SELECT * FROM config WHERE id = 1").fetchone()
    items = conn.execute("SELECT * FROM items ORDER BY id DESC").fetchall()
    slides = conn.execute("SELECT * FROM banner_slides ORDER BY id DESC").fetchall()
    conn.close()

    admin_html = render_template_string("""
    <div class="max-w-7xl mx-auto px-6 py-10 space-y-10">
        <div class="flex flex-wrap justify-between items-center gap-4">
            <div>
                <h1 class="text-3xl font-extrabold text-white">⚙️ Local Admin Control Center</h1>
                <p class="text-sm text-slate-400">Manage video/image gallery sliders, item slots, or use your Remote Admin Web on Port 5001.</p>
            </div>
        </div>

        <!-- 1. VIDEO & IMAGE SLIDER MANAGER (GALLERY UPLOAD OR LINK) -->
        <div class="glass p-6 rounded-3xl border border-cyan-500/30">
            <h2 class="text-xl font-bold text-white mb-1">🎬 Animated Video & Image Banner Slider</h2>
            <p class="text-xs text-slate-400 mb-4">Upload an MP4/WebM video or image directly from your device gallery, or paste a direct URL.</p>

            <form action="{{ url_for('admin_add_slide') }}" method="POST" enctype="multipart/form-data" class="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
                <div>
                    <label class="text-xs text-cyan-300 font-semibold">Upload from Gallery (Video/Img)</label>
                    <input type="file" name="slide_file" accept="video/mp4,video/webm,video/quicktime,image/*"
                           class="w-full mt-1 px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs text-slate-300 file:mr-3 file:py-1 file:px-3 file:rounded-lg file:border-0 file:bg-cyan-500 file:text-slate-950 file:font-bold">
                </div>
                <div>
                    <label class="text-xs text-slate-400">OR Paste Video/Image URL</label>
                    <input type="url" name="media_url" placeholder="https://.../video.mp4 or .jpg"
                           class="w-full mt-1 px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                </div>
                <div>
                    <label class="text-xs text-slate-400">Slide Caption & Animation</label>
                    <div class="flex gap-2 mt-1">
                        <input type="text" name="caption" placeholder="Slide Caption" value="New Drop"
                               class="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                        <select name="animation_style" class="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs text-cyan-300 font-bold">
                            <option value="zoom-pan">Zoom Pan</option>
                            <option value="pulse-glow">Pulse Glow</option>
                            <option value="none">Static</option>
                        </select>
                    </div>
                </div>
                <button type="submit" class="py-2.5 px-5 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 text-white font-bold text-sm">
                    + Add Slide to Banner
                </button>
            </form>

            <!-- Active Slides Preview Grid -->
            <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4 mt-6">
                {% for s in slides %}
                <div class="relative rounded-2xl overflow-hidden border border-slate-700 bg-slate-950 h-28 group">
                    {% if s.media_type == 'video' %}
                        <video src="{{ s.media_url }}" autoplay loop muted playsinline class="w-full h-full object-cover"></video>
                        <span class="absolute top-2 left-2 px-2 py-0.5 text-[10px] font-bold bg-rose-600 text-white rounded">VIDEO</span>
                    {% else %}
                        <img src="{{ s.media_url }}" class="w-full h-full object-cover">
                        <span class="absolute top-2 left-2 px-2 py-0.5 text-[10px] font-bold bg-cyan-600 text-white rounded">IMAGE</span>
                    {% endif %}
                    <div class="absolute bottom-0 inset-x-0 bg-black/75 px-2 py-1 text-[11px] truncate">{{ s.caption }}</div>
                    <form action="{{ url_for('admin_delete_slide', slide_id=s.id) }}" method="POST"
                          class="absolute inset-0 bg-black/70 opacity-0 group-hover:opacity-100 flex items-center justify-center transition">
                        <button type="submit" class="px-3 py-1 rounded-lg bg-rose-500 text-white text-xs font-bold">Delete Slide</button>
                    </form>
                </div>
                {% endfor %}
            </div>
        </div>

        <!-- 2. ADD PRODUCT & BRANDING -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="lg:col-span-2 glass p-6 rounded-3xl border border-slate-800">
                <h2 class="text-xl font-bold text-white mb-4">➕ Add New Product Slot (Gallery Upload or Link)</h2>
                <form action="{{ url_for('admin_add_item') }}" method="POST" enctype="multipart/form-data" class="space-y-4">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <input type="text" name="name" placeholder="Product Title *" required class="px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                        <input type="text" name="category" placeholder="Category *" required class="px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <input type="text" name="price" placeholder="$49.99 *" required class="px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                        <input type="number" name="stock" value="10" required class="px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                        <input type="text" name="badge" value="Featured" class="px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                        <input type="number" step="0.1" name="rating" value="4.9" class="px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label class="text-xs text-cyan-300">Upload Item Photo from Gallery</label>
                            <input type="file" name="item_file" accept="image/*" class="w-full mt-1 px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs text-slate-300">
                        </div>
                        <div>
                            <label class="text-xs text-slate-400">OR Paste Image URL</label>
                            <input type="url" name="image_url" placeholder="https://..." class="w-full mt-1 px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                        </div>
                    </div>
                    <input type="text" name="short_desc" placeholder="Short Summary Description *" required class="w-full px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                    <textarea name="full_specs" rows="2" placeholder="• Bullet specifications..." class="w-full px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white"></textarea>
                    <button type="submit" class="px-6 py-3 rounded-xl bg-cyan-500 text-slate-950 font-bold text-sm">+ Publish Item</button>
                </form>
            </div>

            <div class="glass p-6 rounded-3xl border border-slate-800 h-fit">
                <h2 class="text-xl font-bold text-white mb-4">🖼️ Branding Settings</h2>
                <form action="{{ url_for('admin_update_config') }}" method="POST" class="space-y-4">
                    <input type="text" name="title" value="{{ config.title }}" required class="w-full px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                    <input type="text" name="subtitle" value="{{ config.subtitle }}" required class="w-full px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                    <input type="text" name="announcement" value="{{ config.announcement }}" class="w-full px-4 py-2 rounded-xl bg-slate-900 border border-slate-700 text-sm text-white">
                    <button type="submit" class="w-full py-3 rounded-xl bg-indigo-500 text-white font-bold text-sm">Save Branding</button>
                </form>
            </div>
        </div>
    </div>
    """, config=config, items=items, slides=slides)

    return render_template_string(BASE_HTML, config=config, content=admin_html)

# ---------------------------------------------------------
# LOCAL ADMIN ACTION ROUTES
# ---------------------------------------------------------
@app.route("/admin/add-slide", methods=["POST"])
@admin_required
def admin_add_slide():
    uploaded_url = save_uploaded_file(request.files.get("slide_file"))
    media_url = uploaded_url or request.form.get("media_url", "").strip()
    if not media_url:
        flash("Please upload a file from gallery or provide a URL.", "error")
        return redirect(url_for("admin_dashboard"))

    media_type = detect_media_type(media_url)
    caption = request.form.get("caption", "Featured Highlight")
    anim = request.form.get("animation_style", "zoom-pan")

    conn = get_db()
    conn.execute("INSERT INTO banner_slides (media_url, media_type, caption, animation_style) VALUES (?, ?, ?, ?)",
                 (media_url, media_type, caption, anim))
    conn.commit()
    conn.close()
    flash(f"Added new {media_type} slide to hero banner!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete-slide/<int:slide_id>", methods=["POST"])
@admin_required
def admin_delete_slide(slide_id):
    conn = get_db()
    conn.execute("DELETE FROM banner_slides WHERE id = ?", (slide_id,))
    conn.commit()
    conn.close()
    flash("Slide removed from banner.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/add-item", methods=["POST"])
@admin_required
def admin_add_item():
    uploaded_url = save_uploaded_file(request.files.get("item_file"))
    image_url = uploaded_url or request.form.get("image_url", "").strip() or "https://via.placeholder.com/600"

    conn = get_db()
    conn.execute("""
        INSERT INTO items (name, category, price, stock, badge, rating, image_url, short_desc, full_specs)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form.get("name"),
        request.form.get("category"),
        request.form.get("price"),
        int(request.form.get("stock", 10)),
        request.form.get("badge", "Featured"),
        float(request.form.get("rating", 5.0)),
        image_url,
        request.form.get("short_desc"),
        request.form.get("full_specs")
    ))
    conn.commit()
    conn.close()
    flash("New item slot added!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/update-config", methods=["POST"])
@admin_required
def admin_update_config():
    conn = get_db()
    conn.execute("UPDATE config SET title = ?, subtitle = ?, announcement = ? WHERE id = 1",
                 (request.form.get("title"), request.form.get("subtitle"), request.form.get("announcement")))
    conn.commit()
    conn.close()
    flash("Branding updated!", "success")
    return redirect(url_for("admin_dashboard"))

# ---------------------------------------------------------
# REMOTE CONTROL API ENDPOINTS (FOR EXTERNAL PYTHON WEB APP)
# ---------------------------------------------------------
@app.route("/api/state", methods=["GET"])
@api_key_required
def api_get_state():
    conn = get_db()
    config = dict(conn.execute("SELECT * FROM config WHERE id = 1").fetchone())
    items = [dict(r) for r in conn.execute("SELECT * FROM items ORDER BY id DESC").fetchall()]
    slides = [dict(r) for r in conn.execute("SELECT * FROM banner_slides ORDER BY id DESC").fetchall()]
    conn.close()
    return jsonify({"config": config, "items": items, "slides": slides})

@app.route("/api/add-slide", methods=["POST"])
@api_key_required
def api_add_slide():
    uploaded_url = save_uploaded_file(request.files.get("slide_file"))
    media_url = uploaded_url or request.form.get("media_url", "").strip()
    if not media_url:
        return jsonify({"error": "No media provided"}), 400
    media_type = detect_media_type(media_url)
    caption = request.form.get("caption", "Remote Highlight")
    anim = request.form.get("animation_style", "zoom-pan")

    conn = get_db()
    conn.execute("INSERT INTO banner_slides (media_url, media_type, caption, animation_style) VALUES (?, ?, ?, ?)",
                 (media_url, media_type, caption, anim))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "media_url": media_url})

@app.route("/api/delete-slide/<int:slide_id>", methods=["POST"])
@api_key_required
def api_delete_slide(slide_id):
    conn = get_db()
    conn.execute("DELETE FROM banner_slides WHERE id = ?", (slide_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})

@app.route("/api/add-item", methods=["POST"])
@api_key_required
def api_add_item():
    uploaded_url = save_uploaded_file(request.files.get("item_file"))
    image_url = uploaded_url or request.form.get("image_url", "").strip()
    conn = get_db()
    conn.execute("""
        INSERT INTO items (name, category, price, stock, badge, rating, image_url, short_desc, full_specs)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form.get("name"),
        request.form.get("category"),
        request.form.get("price"),
        int(request.form.get("stock", 10)),
        request.form.get("badge", "Featured"),
        float(request.form.get("rating", 5.0)),
        image_url,
        request.form.get("short_desc"),
        request.form.get("full_specs")
    ))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route("/api/delete-item/<int:item_id>", methods=["POST"])
@api_key_required
def api_delete_item(item_id):
    conn = get_db()
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})

@app.route("/api/update-config", methods=["POST"])
@api_key_required
def api_update_config():
    conn = get_db()
    conn.execute("UPDATE config SET title = ?, subtitle = ?, announcement = ? WHERE id = 1",
                 (request.form.get("title"), request.form.get("subtitle"), request.form.get("announcement")))
    conn.commit()
    conn.close()
    return jsonify({"status": "updated"})

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
