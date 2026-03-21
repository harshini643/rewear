import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, g
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from model.predict import recommend_similar_items
from model.train_model import train_and_save_model

app = Flask(__name__)
app.config["SECRET_KEY"] = "rewear-secret-key-2024"
app.config["DATABASE"] = os.path.join(app.root_path, "database", "rewear.db")
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "images", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.join(app.root_path, "database"), exist_ok=True)


# --------------------------------------------------
# DATABASE HELPERS
# --------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    last_id = cur.lastrowid
    cur.close()
    return last_id


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


# --------------------------------------------------
# SCHEMA
# --------------------------------------------------
SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        points INTEGER DEFAULT 100,
        role TEXT DEFAULT 'user',
        created_at TEXT DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        category TEXT,
        type TEXT,
        size TEXT,
        condition TEXT,
        tags TEXT,
        points INTEGER DEFAULT 50,
        image TEXT DEFAULT 'default.jpg',
        status TEXT DEFAULT 'available',
        approved INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS swaps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requester_id INTEGER NOT NULL,
        owner_id INTEGER NOT NULL,
        requested_item_id INTEGER NOT NULL,
        offered_item_id INTEGER,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (requester_id) REFERENCES users(id),
        FOREIGN KEY (owner_id) REFERENCES users(id),
        FOREIGN KEY (requested_item_id) REFERENCES items(id),
        FOREIGN KEY (offered_item_id) REFERENCES items(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS redemptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        points_used INTEGER NOT NULL,
        redeemed_on TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (item_id) REFERENCES items(id)
    )
    """
]


def init_db():
    db = get_db()
    for stmt in SCHEMA:
        db.execute(stmt)
    db.commit()

    admin = query("SELECT * FROM users WHERE email = ?", ("admin@rewear.com",), one=True)
    if not admin:
        execute("""
            INSERT INTO users (name, email, password, points, role)
            VALUES (?, ?, ?, ?, ?)
        """, ("Admin", "admin@rewear.com", generate_password_hash("admin123"), 1000, "admin"))


def seed_db():
    existing = query("SELECT id FROM items LIMIT 1", one=True)
    if existing:
        return

    priya = execute("""
        INSERT INTO users (name, email, password, points, role)
        VALUES (?, ?, ?, ?, ?)
    """, ("Priya Sharma", "priya@demo.com", generate_password_hash("demo123"), 250, "user"))

    rahul = execute("""
        INSERT INTO users (name, email, password, points, role)
        VALUES (?, ?, ?, ?, ?)
    """, ("Rahul Verma", "rahul@demo.com", generate_password_hash("demo123"), 180, "user"))

    ananya = execute("""
        INSERT INTO users (name, email, password, points, role)
        VALUES (?, ?, ?, ?, ?)
    """, ("Ananya Iyer", "ananya@demo.com", generate_password_hash("demo123"), 320, "user"))

    admin = query("SELECT id FROM users WHERE email = ?", ("admin@rewear.com",), one=True)
    admin_id = admin["id"]

    sample_items = [
        (priya, "Floral Kurti", "Beautiful floral print kurti, worn twice.", "Women", "Top", "M", "Like New", "kurti,floral,ethnic", 60, "floral_kurti.png", 1),
        (priya, "Blue Denim Jacket", "Classic denim jacket, great condition.", "Women", "Jacket", "S", "Good", "denim,jacket,casual", 80, "blue_denim_jacket.jpg", 1),
        (rahul, "Men's Formal Shirt", "White formal shirt, barely worn.", "Men", "Shirt", "L", "Like New", "formal,shirt,white", 55, "mens_formal_shirt.jpg", 1),
        (rahul, "Chinos", "Khaki chinos in excellent condition.", "Men", "Pants", "32", "Good", "chinos,pants,casual", 70, "chinos.jpg", 1),
        (ananya, "Kids Summer Dress", "Cute summer dress for ages 5-6.", "Kids", "Dress", "5-6Y", "Good", "dress,kids,summer", 40, "kids_summer_dress.jpg", 1),
        (ananya, "Ethnic Saree", "Silk saree with blouse, festival wear.", "Women", "Saree", "Free", "Excellent", "saree,silk,ethnic,festival", 120, "ethnic_saree.png", 1),
        (admin_id, "Sports T-Shirt", "Nike dry-fit sports tee.", "Men", "T-Shirt", "M", "Good", "sports,tshirt,nike,casual", 45, "sports_tshirt.png", 1),
        (priya, "Palazzo Pants", "Comfortable palazzo pants for summer.", "Women", "Pants", "M", "Like New", "palazzo,pants,casual,summer", 50, "palazzo_pants.png", 1),
        (rahul, "Linen Kurta", "Light linen kurta, perfect for summer.", "Men", "Kurta", "L", "Good", "kurta,linen,ethnic,summer", 65, "linen_kurta.jpeg", 1),
        (ananya, "Winter Coat", "Woollen winter coat, barely used.", "Women", "Coat", "M", "Excellent", "coat,winter,woollen", 150, "winter_coat.jpg", 1),
    ]

    for item in sample_items:
        execute("""
            INSERT INTO items (
                user_id, title, description, category, type, size,
                condition, tags, points, image, approved
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, item)

    print("Database seeded successfully.")


def update_old_images():
    updates = {
        "Floral Kurti": "floral_kurti.png",
        "Blue Denim Jacket": "blue_denim_jacket.jpg",
        "Men's Formal Shirt": "mens_formal_shirt.jpg",
        "Chinos": "chinos.jpg",
        "Kids Summer Dress": "kids_summer_dress.jpg",
        "Ethnic Saree": "ethnic_saree.png",
        "Sports T-Shirt": "sports_tshirt.png",
        "Palazzo Pants": "palazzo_pants.png",
        "Linen Kurta": "linen_kurta.jpeg",
        "Winter Coat": "winter_coat.jpg"
    }

    for title, image in updates.items():
        execute("UPDATE items SET image = ? WHERE title = ?", (image, title))

    print("Images updated successfully.")


# --------------------------------------------------
# UTILITIES
# --------------------------------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session or session.get("user_role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.template_filter("fmtdate")
def fmtdate_filter(value):
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d %b %Y")
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y")
    except Exception:
        return str(value)[:10]


@app.context_processor
def inject_user():
    user = None
    if "user_id" in session:
        user = row_to_dict(query("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True))
        if user:
            session["user_points"] = user["points"]

    return {
        "current_user": user,
        "session_user_id": session.get("user_id"),
        "session_user_name": session.get("user_name"),
        "session_user_role": session.get("user_role"),
        "session_user_points": session.get("user_points")
    }


# --------------------------------------------------
# ROUTES
# --------------------------------------------------
@app.route("/")
def index():
    featured_items = rows_to_dicts(query("""
        SELECT items.*, users.name AS owner_name
        FROM items
        JOIN users ON items.user_id = users.id
        WHERE items.approved = 1 AND items.status = 'available'
        ORDER BY items.id DESC
        LIMIT 6
    """))

    stats = {
        "items": query("SELECT COUNT(*) AS c FROM items WHERE approved = 1", one=True)["c"],
        "users": query("SELECT COUNT(*) AS c FROM users", one=True)["c"],
        "swaps": query("SELECT COUNT(*) AS c FROM swaps WHERE status = 'completed'", one=True)["c"],
    }

    return render_template("index.html", featured_items=featured_items, stats=stats)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        flash("You are already logged in.", "info")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not name or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("signup.html")

        existing_user = query("SELECT id FROM users WHERE email = ?", (email,), one=True)

        if existing_user:
            flash("Account already exists. Please login.", "warning")
            return redirect(url_for("login"))

        hashed_password = generate_password_hash(password)

        execute("""
            INSERT INTO users (name, email, password, points, role)
            VALUES (?, ?, ?, ?, ?)
        """, (name, email, hashed_password, 100, "user"))

        flash("Signup successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        flash("You are already logged in.", "info")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        user = row_to_dict(query("""
            SELECT * FROM users WHERE email = ?
        """, (email,), one=True))

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_role"] = user["role"]
            session["user_points"] = user["points"]

            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]

    user = row_to_dict(query("SELECT * FROM users WHERE id = ?", (uid,), one=True))
    my_items = rows_to_dicts(query("""
        SELECT * FROM items
        WHERE user_id = ?
        ORDER BY id DESC
    """, (uid,)))

    my_swaps = rows_to_dicts(query("""
        SELECT swaps.*,
               req_user.name AS requester_name,
               own_user.name AS owner_name,
               req_item.title AS requested_item_title,
               off_item.title AS offered_item_title
        FROM swaps
        JOIN users req_user ON swaps.requester_id = req_user.id
        JOIN users own_user ON swaps.owner_id = own_user.id
        JOIN items req_item ON swaps.requested_item_id = req_item.id
        LEFT JOIN items off_item ON swaps.offered_item_id = off_item.id
        WHERE swaps.requester_id = ? OR swaps.owner_id = ?
        ORDER BY swaps.id DESC
    """, (uid, uid)))

    redemptions = rows_to_dicts(query("""
        SELECT redemptions.*, items.title
        FROM redemptions
        JOIN items ON redemptions.item_id = items.id
        WHERE redemptions.user_id = ?
        ORDER BY redemptions.id DESC
    """, (uid,)))

    return render_template(
        "dashboard.html",
        user=user,
        my_items=my_items,
        my_swaps=my_swaps,
        redemptions=redemptions
    )


@app.route("/browse")
@login_required
def browse():
    category = request.args.get("category", "").strip()
    size = request.args.get("size", "").strip()
    item_type = request.args.get("type", "").strip()
    condition = request.args.get("condition", "").strip()
    search = request.args.get("search", "").strip()

    sql = """
        SELECT items.*, users.name AS owner_name
        FROM items
        JOIN users ON items.user_id = users.id
        WHERE items.approved = 1
          AND items.status = 'available'
    """
    args = []

    if category:
        sql += " AND items.category = ?"
        args.append(category)

    if size:
        sql += " AND items.size = ?"
        args.append(size)

    if item_type:
        sql += " AND items.type = ?"
        args.append(item_type)

    if condition:
        sql += " AND items.condition = ?"
        args.append(condition)

    if search:
        sql += " AND (items.title LIKE ? OR items.tags LIKE ?)"
        args.extend([f"%{search}%", f"%{search}%"])

    sql += " ORDER BY items.id DESC"

    items = rows_to_dicts(query(sql, args))

    return render_template(
        "browse.html",
        items=items,
        category=category,
        size=size,
        type=item_type,
        condition=condition,
        search=search
    )


@app.route("/add_item", methods=["GET", "POST"])
@login_required
def add_item():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        item_type = request.form.get("type", "").strip()
        size = request.form.get("size", "").strip()
        condition = request.form.get("condition", "").strip()
        tags = request.form.get("tags", "").strip()
        points = int(request.form.get("points", 50))

        image_filename = "default.jpg"

        if "image" in request.files:
            image_file = request.files["image"]
            if image_file and image_file.filename:
                if not allowed_file(image_file.filename):
                    flash("Only image files are allowed.", "danger")
                    return redirect(url_for("add_item"))

                filename = secure_filename(image_file.filename)
                timestamp = str(int(datetime.utcnow().timestamp()))
                filename = f"{timestamp}_{filename}"
                save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                image_file.save(save_path)
                image_filename = filename

        execute("""
            INSERT INTO items (
                user_id, title, description, category, type, size,
                condition, tags, points, image, status, approved
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"], title, description, category, item_type,
            size, condition, tags, points, image_filename, "available", 1
        ))

        train_and_save_model()

        flash("Item added successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_item.html")


@app.route("/item/<int:item_id>")
@login_required
def item_detail(item_id):
    item = row_to_dict(query("""
        SELECT items.*, users.name AS owner_name, users.id AS owner_id
        FROM items
        JOIN users ON items.user_id = users.id
        WHERE items.id = ?
    """, (item_id,), one=True))

    if not item:
        flash("Item not found.", "warning")
        return redirect(url_for("browse"))

    if not item["approved"] and session.get("user_id") != item["user_id"]:
        flash("This item is not available.", "warning")
        return redirect(url_for("browse"))

    item["owner"] = row_to_dict(query(
        "SELECT * FROM users WHERE id = ?",
        (item["user_id"],),
        one=True
    ))

    current_item = {
        "id": item["id"],
        "title": item["title"],
        "category": item["category"],
        "type": item["type"],
        "size": item["size"],
        "condition": item["condition"],
        "tags": item["tags"],
        "points": item["points"]
    }

    recommended_items = recommend_similar_items(current_item, top_n=4)

    my_items = []
    if session.get("user_id"):
        my_items = rows_to_dicts(query("""
            SELECT * FROM items
            WHERE user_id = ? AND approved = 1 AND status = 'available'
        """, (session["user_id"],)))

    return render_template(
        "item_detail.html",
        item=item,
        my_items=my_items,
        recommended_items=recommended_items
    )


@app.route("/request_swap/<int:item_id>", methods=["POST"])
@login_required
def request_swap(item_id):
    offered_item_id = request.form.get("offered_item_id") or None

    requested_item = query("SELECT * FROM items WHERE id = ?", (item_id,), one=True)

    if not requested_item:
        flash("Requested item not found.", "danger")
        return redirect(url_for("browse"))

    if requested_item["user_id"] == session["user_id"]:
        flash("You cannot request swap for your own item.", "warning")
        return redirect(url_for("item_detail", item_id=item_id))

    existing = query("""
        SELECT id FROM swaps
        WHERE requester_id = ? AND requested_item_id = ? AND status = 'pending'
    """, (session["user_id"], item_id), one=True)

    if existing:
        flash("You already have a pending swap request for this item.", "info")
        return redirect(url_for("item_detail", item_id=item_id))

    execute("""
        INSERT INTO swaps (
            requester_id, owner_id, requested_item_id,
            offered_item_id, status
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        requested_item["user_id"],
        item_id,
        offered_item_id,
        "pending"
    ))

    flash("Swap request sent successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/swap_action/<int:swap_id>/<action>")
@login_required
def swap_action(swap_id, action):
    swap = query("SELECT * FROM swaps WHERE id = ?", (swap_id,), one=True)

    if not swap:
        flash("Swap request not found.", "danger")
        return redirect(url_for("dashboard"))

    if swap["owner_id"] != session["user_id"]:
        flash("You are not allowed to perform this action.", "danger")
        return redirect(url_for("dashboard"))

    if action == "accept":
        execute("UPDATE swaps SET status = 'accepted' WHERE id = ?", (swap_id,))
        flash("Swap request accepted.", "success")

    elif action == "reject":
        execute("UPDATE swaps SET status = 'rejected' WHERE id = ?", (swap_id,))
        flash("Swap request rejected.", "warning")

    elif action == "complete":
        execute("UPDATE swaps SET status = 'completed' WHERE id = ?", (swap_id,))
        execute("UPDATE items SET status = 'swapped' WHERE id = ?", (swap["requested_item_id"],))

        if swap["offered_item_id"]:
            execute("UPDATE items SET status = 'swapped' WHERE id = ?", (swap["offered_item_id"],))

        execute("UPDATE users SET points = points + 20 WHERE id = ?", (swap["owner_id"],))
        execute("UPDATE users SET points = points + 20 WHERE id = ?", (swap["requester_id"],))

        if session.get("user_id"):
            updated_user = query("SELECT points FROM users WHERE id = ?", (session["user_id"],), one=True)
            if updated_user:
                session["user_points"] = updated_user["points"]

        train_and_save_model()
        flash("Swap completed successfully.", "success")

    return redirect(url_for("dashboard"))


@app.route("/redeem/<int:item_id>", methods=["POST"])
@login_required
def redeem_item(item_id):
    item = query("SELECT * FROM items WHERE id = ?", (item_id,), one=True)
    user = query("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)

    if not item:
        flash("Item not found.", "danger")
        return redirect(url_for("browse"))

    if item["user_id"] == session["user_id"]:
        flash("You cannot redeem your own item.", "warning")
        return redirect(url_for("item_detail", item_id=item_id))

    if item["status"] != "available" or item["approved"] != 1:
        flash("Item is not available for redemption.", "warning")
        return redirect(url_for("item_detail", item_id=item_id))

    if user["points"] < item["points"]:
        flash("Not enough points to redeem this item.", "danger")
        return redirect(url_for("item_detail", item_id=item_id))

    execute("UPDATE users SET points = points - ? WHERE id = ?", (item["points"], session["user_id"]))
    execute("UPDATE users SET points = points + ? WHERE id = ?", (item["points"], item["user_id"]))
    execute("UPDATE items SET status = 'redeemed' WHERE id = ?", (item_id,))
    execute("""
        INSERT INTO redemptions (user_id, item_id, points_used)
        VALUES (?, ?, ?)
    """, (session["user_id"], item_id, item["points"]))

    updated_points = query("SELECT points FROM users WHERE id = ?", (session["user_id"],), one=True)
    if updated_points:
        session["user_points"] = updated_points["points"]

    train_and_save_model()
    flash("Item redeemed successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin")
@admin_required
def admin():
    pending_items = rows_to_dicts(query("""
        SELECT items.*, users.name AS owner_name
        FROM items
        JOIN users ON items.user_id = users.id
        WHERE items.approved = 0
        ORDER BY items.id DESC
    """))

    approved_items = rows_to_dicts(query("""
        SELECT items.*, users.name AS owner_name
        FROM items
        JOIN users ON items.user_id = users.id
        WHERE items.approved = 1
        ORDER BY items.id DESC
    """))

    all_users = rows_to_dicts(query("SELECT * FROM users ORDER BY id DESC"))
    all_swaps = rows_to_dicts(query("SELECT * FROM swaps ORDER BY id DESC"))

    return render_template(
        "admin.html",
        pending_items=pending_items,
        approved_items=approved_items,
        all_users=all_users,
        all_swaps=all_swaps
    )


@app.route("/admin/approve/<int:item_id>")
@admin_required
def approve_item(item_id):
    execute("UPDATE items SET approved = 1, status = 'available' WHERE id = ?", (item_id,))
    train_and_save_model()
    flash("Item approved successfully.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/reject/<int:item_id>")
@admin_required
def reject_item(item_id):
    execute("UPDATE items SET approved = 0, status = 'rejected' WHERE id = ?", (item_id,))
    train_and_save_model()
    flash("Item rejected.", "warning")
    return redirect(url_for("admin"))


@app.route("/admin/delete/<int:item_id>")
@admin_required
def delete_item(item_id):
    execute("DELETE FROM items WHERE id = ?", (item_id,))
    train_and_save_model()
    flash("Item deleted.", "danger")
    return redirect(url_for("admin"))


@app.route("/admin/make_admin/<int:user_id>")
@admin_required
def make_admin(user_id):
    execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
    flash("User promoted to admin.", "success")
    return redirect(url_for("admin"))


@app.route("/api/recommendations/<int:item_id>")
def api_recommendations(item_id):
    item = row_to_dict(query("SELECT * FROM items WHERE id = ?", (item_id,), one=True))
    if not item:
        return jsonify([])

    current_item = {
        "id": item["id"],
        "title": item["title"],
        "category": item["category"],
        "type": item["type"],
        "size": item["size"],
        "condition": item["condition"],
        "tags": item["tags"],
        "points": item["points"]
    }

    recs = recommend_similar_items(current_item, top_n=4)

    return jsonify([
        {
            "id": r.get("id"),
            "title": r.get("title"),
            "category": r.get("category"),
            "size": r.get("size"),
            "condition": r.get("condition"),
            "points": r.get("points"),
            "image": r.get("image"),
            "similarity_score": r.get("similarity_score")
        }
        for r in recs
    ])


# --------------------------------------------------
# MAIN
# --------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_db()
        update_old_images()
        train_and_save_model()

    app.run(debug=True, port=5000)