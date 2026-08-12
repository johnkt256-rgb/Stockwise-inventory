import csv
import io
import os
import sqlite3
from datetime import date
from functools import wraps

from flask import Flask, Response, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-before-online-deployment")
app.config["DATABASE"] = os.path.join(app.root_path, "inventory.db")


def db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db():
    connection = db()
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            barcode TEXT UNIQUE,
            unit TEXT NOT NULL DEFAULT 'units',
            reorder_level INTEGER NOT NULL DEFAULT 0,
            sale_price REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            batch_number TEXT NOT NULL,
            supplier TEXT,
            received_date TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity >= 0),
            initial_quantity INTEGER NOT NULL,
            cost_price REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            batch_id INTEGER,
            user_id INTEGER,
            movement_type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(batch_id) REFERENCES batches(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            entity TEXT NOT NULL,
            entity_id INTEGER,
            details TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
    """)
    connection.commit()


def log(action, entity, entity_id=None, details=""):
    db().execute(
        "INSERT INTO audit_logs (user_id, action, entity, entity_id, details) VALUES (?, ?, ?, ?, ?)",
        (session.get("user_id"), action, entity, entity_id, details),
    )
    db().commit()


def current_user():
    if not session.get("user_id"):
        return None
    return db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()


@app.context_processor
def inject_user():
    return {"current_user": current_user(), "today": date.today().isoformat()}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or user["role"] != "admin":
            flash("Administrator access is required.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


def product_stock_expression():
    return "COALESCE((SELECT SUM(quantity) FROM batches WHERE batches.product_id = products.id), 0)"


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if db().execute("SELECT id FROM users LIMIT 1").fetchone():
        return redirect(url_for("login"))
    if request.method == "POST":
        name = request.form["full_name"].strip()
        username = request.form["username"].strip().lower()
        password = request.form["password"]
        if not name or not username or len(password) < 8:
            flash("Use a name, username, and a password of at least 8 characters.", "error")
        else:
            db().execute("INSERT INTO users (full_name, username, password_hash, role) VALUES (?, ?, ?, 'admin')",
                         (name, username, generate_password_hash(password)))
            db().commit()
            flash("Administrator account created. Please sign in.", "success")
            return redirect(url_for("login"))
    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if not db().execute("SELECT id FROM users LIMIT 1").fetchone():
        return redirect(url_for("setup"))
    if request.method == "POST":
        user = db().execute("SELECT * FROM users WHERE username = ?", (request.form["username"].strip().lower(),)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session["user_id"] = user["id"]
            log("Signed in", "user", user["id"], user["username"])
            return redirect(url_for("dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    if current_user():
        log("Signed out", "user", session["user_id"])
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    connection = db()
    total_products = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    total_units = connection.execute("SELECT COALESCE(SUM(quantity), 0) FROM batches").fetchone()[0]
    expired = connection.execute("SELECT COUNT(*) FROM batches WHERE quantity > 0 AND expiry_date < date('now')").fetchone()[0]
    expiring = connection.execute("SELECT COUNT(*) FROM batches WHERE quantity > 0 AND expiry_date BETWEEN date('now') AND date('now', '+30 days')").fetchone()[0]
    low_stock = connection.execute(f"SELECT COUNT(*) FROM products WHERE {product_stock_expression()} <= reorder_level").fetchone()[0]
    alerts = connection.execute("""
        SELECT b.*, p.name, p.unit,
        CASE WHEN b.expiry_date < date('now') THEN 'Expired'
             WHEN b.expiry_date <= date('now', '+30 days') THEN 'Expiring soon'
             ELSE 'Safe' END AS expiry_status
        FROM batches b JOIN products p ON p.id = b.product_id
        WHERE b.quantity > 0 AND b.expiry_date <= date('now', '+30 days')
        ORDER BY b.expiry_date LIMIT 6
    """).fetchall()
    recent = connection.execute("""
        SELECT m.*, p.name, b.batch_number, u.full_name
        FROM stock_movements m JOIN products p ON p.id=m.product_id
        LEFT JOIN batches b ON b.id=m.batch_id LEFT JOIN users u ON u.id=m.user_id
        ORDER BY m.created_at DESC LIMIT 8
    """).fetchall()
    return render_template("dashboard.html", total_products=total_products, total_units=total_units,
                           expired=expired, expiring=expiring, low_stock=low_stock, alerts=alerts, recent=recent)


@app.route("/products")
@login_required
def products():
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    sql = f"SELECT products.*, {product_stock_expression()} AS stock FROM products WHERE 1=1"
    args = []
    if query:
        sql += " AND (name LIKE ? OR barcode LIKE ?)"
        args += [f"%{query}%", f"%{query}%"]
    if category:
        sql += " AND category = ?"
        args.append(category)
    sql += " ORDER BY name"
    rows = db().execute(sql, args).fetchall()
    categories = db().execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()
    return render_template("products.html", products=rows, categories=categories, query=query, chosen_category=category)


@app.route("/products/add", methods=["GET", "POST"])
@login_required
def add_product():
    if request.method == "POST":
        try:
            cursor = db().execute("""INSERT INTO products (name, category, barcode, unit, reorder_level, sale_price)
                                   VALUES (?, ?, ?, ?, ?, ?)""",
                                (request.form["name"].strip(), request.form["category"].strip(), request.form["barcode"].strip() or None,
                                 request.form["unit"].strip() or "units", int(request.form["reorder_level"] or 0), float(request.form["sale_price"] or 0)))
            db().commit()
            log("Created", "product", cursor.lastrowid, request.form["name"].strip())
            flash("Product added. Add a stock batch next.", "success")
            return redirect(url_for("product_detail", product_id=cursor.lastrowid))
        except sqlite3.IntegrityError:
            flash("That barcode is already assigned to another product.", "error")
    return render_template("product_form.html", product=None)


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    product = db().execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        return "Product not found", 404
    if request.method == "POST":
        try:
            db().execute("""UPDATE products SET name=?, category=?, barcode=?, unit=?, reorder_level=?, sale_price=? WHERE id=?""",
                         (request.form["name"].strip(), request.form["category"].strip(), request.form["barcode"].strip() or None,
                          request.form["unit"].strip() or "units", int(request.form["reorder_level"] or 0), float(request.form["sale_price"] or 0), product_id))
            db().commit(); log("Updated", "product", product_id, request.form["name"].strip())
            flash("Product updated.", "success")
            return redirect(url_for("product_detail", product_id=product_id))
        except sqlite3.IntegrityError:
            flash("That barcode is already assigned to another product.", "error")
    return render_template("product_form.html", product=product)


@app.route("/products/<int:product_id>")
@login_required
def product_detail(product_id):
    product = db().execute(f"SELECT products.*, {product_stock_expression()} AS stock FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        return "Product not found", 404
    batches = db().execute("""SELECT *, CASE WHEN expiry_date < date('now') THEN 'Expired' WHEN expiry_date <= date('now', '+30 days') THEN 'Expiring soon' ELSE 'Safe' END status
                            FROM batches WHERE product_id=? ORDER BY expiry_date""", (product_id,)).fetchall()
    return render_template("product_detail.html", product=product, batches=batches)


@app.post("/products/<int:product_id>/batches")
@login_required
def add_batch(product_id):
    product = db().execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not product:
        return "Product not found", 404
    quantity = int(request.form["quantity"])
    if quantity <= 0 or request.form["expiry_date"] <= date.today().isoformat():
        flash("Use a positive quantity and a future expiry date.", "error")
        return redirect(url_for("product_detail", product_id=product_id))
    cursor = db().execute("""INSERT INTO batches (product_id,batch_number,supplier,received_date,expiry_date,quantity,initial_quantity,cost_price)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (product_id, request.form["batch_number"].strip(), request.form["supplier"].strip(), request.form["received_date"], request.form["expiry_date"], quantity, quantity, float(request.form["cost_price"] or 0)))
    db().execute("INSERT INTO stock_movements (product_id,batch_id,user_id,movement_type,quantity,notes) VALUES (?, ?, ?, 'Stock in', ?, ?)",
                 (product_id, cursor.lastrowid, session["user_id"], quantity, "New batch received"))
    db().commit(); log("Received stock", "batch", cursor.lastrowid, f"{quantity} {product['unit']} of {product['name']}")
    flash("Batch received successfully.", "success")
    return redirect(url_for("product_detail", product_id=product_id))


@app.route("/issue", methods=["GET", "POST"])
@login_required
def issue_stock():
    products = db().execute(f"SELECT products.*, {product_stock_expression()} AS stock FROM products ORDER BY name").fetchall()
    if request.method == "POST":
        product_id, quantity = int(request.form["product_id"]), int(request.form["quantity"])
        product = db().execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        batches = db().execute("SELECT * FROM batches WHERE product_id=? AND quantity>0 AND expiry_date>=date('now') ORDER BY expiry_date, id", (product_id,)).fetchall()
        available = sum(batch["quantity"] for batch in batches)
        if quantity <= 0 or available < quantity:
            flash(f"Not enough usable stock. Available: {available} {product['unit']}.", "error")
        else:
            remaining = quantity
            for batch in batches:
                taken = min(remaining, batch["quantity"])
                db().execute("UPDATE batches SET quantity = quantity - ? WHERE id=?", (taken, batch["id"]))
                db().execute("INSERT INTO stock_movements (product_id,batch_id,user_id,movement_type,quantity,notes) VALUES (?, ?, ?, 'Stock out (FEFO)', ?, ?)",
                             (product_id, batch["id"], session["user_id"], -taken, request.form["notes"].strip() or "Issued using FEFO"))
                remaining -= taken
                if remaining == 0: break
            db().commit(); log("Issued stock using FEFO", "product", product_id, f"{quantity} {product['unit']} of {product['name']}")
            flash("Stock issued using FEFO—the earliest-expiring batch was used first.", "success")
            return redirect(url_for("product_detail", product_id=product_id))
    return render_template("issue.html", products=products)


@app.route("/scan", methods=["GET", "POST"])
@login_required
def scan():
    if request.method == "POST":
        code = request.form["barcode"].strip()
        product = db().execute("SELECT id FROM products WHERE barcode=?", (code,)).fetchone()
        if product:
            return redirect(url_for("product_detail", product_id=product["id"]))
        flash("No product matches that barcode. Add it or check the scan.", "error")
    return render_template("scan.html")


@app.route("/alerts")
@login_required
def alerts():
    expiry = db().execute("""SELECT b.*, p.name, p.unit, CASE WHEN b.expiry_date < date('now') THEN 'Expired' ELSE 'Expiring soon' END status
                           FROM batches b JOIN products p ON p.id=b.product_id WHERE b.quantity>0 AND b.expiry_date<=date('now','+30 days') ORDER BY b.expiry_date""").fetchall()
    low = db().execute(f"SELECT products.*, {product_stock_expression()} AS stock FROM products WHERE {product_stock_expression()} <= reorder_level ORDER BY stock").fetchall()
    return render_template("alerts.html", expiry=expiry, low=low)


@app.route("/analytics")
@login_required
def analytics():
    category = db().execute("""SELECT p.category, COALESCE(SUM(b.quantity),0) units, ROUND(COALESCE(SUM(b.quantity*b.cost_price),0),2) value
                              FROM products p LEFT JOIN batches b ON b.product_id=p.id GROUP BY p.category ORDER BY value DESC""").fetchall()
    movements = db().execute("""SELECT p.name, ABS(SUM(m.quantity)) issued FROM stock_movements m JOIN products p ON p.id=m.product_id
                               WHERE m.movement_type='Stock out (FEFO)' GROUP BY p.id ORDER BY issued DESC LIMIT 8""").fetchall()
    losses = db().execute("SELECT COALESCE(SUM(quantity*cost_price),0) FROM batches WHERE quantity>0 AND expiry_date<date('now')").fetchone()[0]
    return render_template("analytics.html", category=category, movements=movements, losses=losses)


@app.route("/activity")
@admin_required
def activity():
    logs = db().execute("SELECT a.*, u.full_name FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.created_at DESC LIMIT 100").fetchall()
    return render_template("activity.html", logs=logs)


@app.route("/users", methods=["GET", "POST"])
@admin_required
def users():
    if request.method == "POST":
        name = request.form["full_name"].strip()
        username = request.form["username"].strip().lower()
        password = request.form["password"]
        role = request.form["role"]
        if not name or not username or len(password) < 8:
            flash("Enter a name, username, and a password of at least 8 characters.", "error")
        else:
            try:
                cursor = db().execute("INSERT INTO users (full_name, username, password_hash, role) VALUES (?, ?, ?, ?)",
                                      (name, username, generate_password_hash(password), role))
                db().commit()
                log("Created account", "user", cursor.lastrowid, f"{username} ({role})")
                flash("Staff account created.", "success")
                return redirect(url_for("users"))
            except sqlite3.IntegrityError:
                flash("That username is already in use.", "error")
    people = db().execute("SELECT id, full_name, username, role, created_at FROM users ORDER BY role, full_name").fetchall()
    return render_template("users.html", people=people)


@app.route("/export/products.csv")
@login_required
def export_products():
    rows = db().execute(f"SELECT products.*, {product_stock_expression()} AS stock FROM products ORDER BY name").fetchall()
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["Product", "Category", "Barcode", "Stock", "Unit", "Reorder level", "Sale price"])
    for row in rows: writer.writerow([row["name"], row["category"], row["barcode"], row["stock"], row["unit"], row["reorder_level"], row["sale_price"]])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=inventory-products.csv"})


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG", "1") == "1")
