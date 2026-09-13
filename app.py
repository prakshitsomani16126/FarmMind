from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import urllib.request
import urllib.parse
import json
import sqlite3
import os

app = Flask(__name__)

app.secret_key = os.environ["SECRET_KEY"]


DATABASE = "database.db"


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def add_column_if_missing(conn, table, column, definition):
    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()

    existing_columns = [column_info["name"] for column_info in columns]

    if column not in existing_columns:
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def create_tables():

    conn = get_db()

    # USERS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # CROPS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            variety TEXT,
            sowing_date TEXT,
            harvest_date TEXT,
            field_name TEXT,
            status TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # EXPENSES
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            crop TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            expense_date TEXT,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # INCOME
    conn.execute("""
        CREATE TABLE IF NOT EXISTS income (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            crop TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            income_date TEXT,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # IRRIGATION
    conn.execute("""
        CREATE TABLE IF NOT EXISTS irrigation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            crop TEXT NOT NULL,
            irrigation_date TEXT,
            water_liters REAL,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # PESTS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            crop TEXT NOT NULL,
            pest_name TEXT NOT NULL,
            severity TEXT,
            treatment TEXT,
            treatment_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # DECISIONS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            crop TEXT NOT NULL,
            decision TEXT NOT NULL,
            weather TEXT NOT NULL,
            outcome TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Migration for old database
    tables = [
        "crops",
        "expenses",
        "income",
        "irrigation",
        "pests",
        "decisions"
    ]

    for table in tables:
        add_column_if_missing(
            conn,
            table,
            "user_id",
            "INTEGER"
        )

    conn.commit()
    conn.close()


# =========================================================
# LOGIN REQUIRED
# =========================================================

def login_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if "user_id" not in session:
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped_view


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
@login_required
def index():

    user_id = session["user_id"]

    conn = get_db()

    crops = conn.execute(
        """
        SELECT * FROM crops
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    expenses = conn.execute(
        """
        SELECT * FROM expenses
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    income = conn.execute(
        """
        SELECT * FROM income
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    decisions = conn.execute(
        """
        SELECT * FROM decisions
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    total_expense = sum(
        row["amount"] for row in expenses
    )

    total_income = sum(
        row["quantity"] * row["price"]
        for row in income
    )

    profit = total_income - total_expense

    successful = sum(
        1
        for row in decisions
        if row["outcome"].lower() == "success"
    )

    failed = sum(
        1
        for row in decisions
        if row["outcome"].lower() == "failed"
    )

    conn.close()

    return render_template(
        "index.html",
        crops=crops,
        expenses=expenses,
        income=income,
        decisions=decisions,
        total_expense=total_expense,
        total_income=total_income,
        profit=profit,
        successful=successful,
        failed=failed
    )


# =========================================================
# CROPS
# =========================================================

@app.route("/crops", methods=["GET", "POST"])
@login_required
def crops():

    user_id = session["user_id"]

    conn = get_db()

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        variety = request.form.get("variety", "").strip()
        sowing_date = request.form.get("sowing_date", "")
        harvest_date = request.form.get("harvest_date", "")
        field_name = request.form.get("field_name", "").strip()
        status = request.form.get("status", "").strip()

        if name:

            conn.execute("""
                INSERT INTO crops
                (
                    user_id,
                    name,
                    variety,
                    sowing_date,
                    harvest_date,
                    field_name,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                name,
                variety,
                sowing_date,
                harvest_date,
                field_name,
                status
            ))

            conn.commit()

        conn.close()

        return redirect(url_for("crops"))

    crop_list = conn.execute(
        """
        SELECT * FROM crops
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    return render_template(
        "crops.html",
        crops=crop_list
    )


# =========================================================
# EXPENSES
# =========================================================

@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():

    user_id = session["user_id"]

    conn = get_db()

    if request.method == "POST":

        crop = request.form.get("crop", "").strip()
        category = request.form.get("category", "").strip()
        amount = request.form.get("amount", 0)
        expense_date = request.form.get("expense_date", "")
        notes = request.form.get("notes", "").strip()

        try:
            amount = float(amount)
        except ValueError:
            amount = 0

        if crop and category and amount >= 0:

            conn.execute("""
                INSERT INTO expenses
                (
                    user_id,
                    crop,
                    category,
                    amount,
                    expense_date,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                crop,
                category,
                amount,
                expense_date,
                notes
            ))

            conn.commit()

        conn.close()

        return redirect(url_for("expenses"))

    expense_list = conn.execute(
        """
        SELECT * FROM expenses
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    return render_template(
        "expenses.html",
        expenses=expense_list
    )


# =========================================================
# INCOME
# =========================================================

@app.route("/income", methods=["GET", "POST"])
@login_required
def income():

    user_id = session["user_id"]

    conn = get_db()

    if request.method == "POST":

        crop = request.form.get("crop", "").strip()
        quantity = request.form.get("quantity", 0)
        price = request.form.get("price", 0)
        income_date = request.form.get("income_date", "")
        notes = request.form.get("notes", "").strip()

        try:
            quantity = float(quantity)
            price = float(price)
        except ValueError:
            quantity = 0
            price = 0

        if crop and quantity >= 0 and price >= 0:

            conn.execute("""
                INSERT INTO income
                (
                    user_id,
                    crop,
                    quantity,
                    price,
                    income_date,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                crop,
                quantity,
                price,
                income_date,
                notes
            ))

            conn.commit()

        conn.close()

        return redirect(url_for("income"))

    income_list = conn.execute(
        """
        SELECT * FROM income
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    return render_template(
        "income.html",
        income=income_list
    )


# =========================================================
# IRRIGATION
# =========================================================

@app.route("/irrigation", methods=["GET", "POST"])
@login_required
def irrigation():

    user_id = session["user_id"]

    conn = get_db()

    if request.method == "POST":

        crop = request.form.get("crop", "").strip()
        irrigation_date = request.form.get("irrigation_date", "")
        water_liters = request.form.get("water_liters", 0)
        notes = request.form.get("notes", "").strip()

        try:
            water_liters = float(water_liters)
        except ValueError:
            water_liters = 0

        if crop and water_liters >= 0:

            conn.execute("""
                INSERT INTO irrigation
                (
                    user_id,
                    crop,
                    irrigation_date,
                    water_liters,
                    notes
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                user_id,
                crop,
                irrigation_date,
                water_liters,
                notes
            ))

            conn.commit()

        conn.close()

        return redirect(url_for("irrigation"))

    irrigation_list = conn.execute(
        """
        SELECT * FROM irrigation
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    return render_template(
        "irrigation.html",
        irrigations=irrigation_list
    )


# =========================================================
# PESTS
# =========================================================

@app.route("/pests", methods=["GET", "POST"])
@login_required
def pests():

    user_id = session["user_id"]

    conn = get_db()

    if request.method == "POST":

        crop = request.form.get("crop", "").strip()
        pest_name = request.form.get("pest_name", "").strip()
        severity = request.form.get("severity", "").strip()
        treatment = request.form.get("treatment", "").strip()
        treatment_date = request.form.get("treatment_date", "")

        if crop and pest_name:

            conn.execute("""
                INSERT INTO pests
                (
                    user_id,
                    crop,
                    pest_name,
                    severity,
                    treatment,
                    treatment_date
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                crop,
                pest_name,
                severity,
                treatment,
                treatment_date
            ))

            conn.commit()

        conn.close()

        return redirect(url_for("pests"))

    pest_list = conn.execute(
        """
        SELECT * FROM pests
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    return render_template(
        "pests.html",
        pests=pest_list
    )


# =========================================================
# SMART RECOMMENDATIONS
# =========================================================

@app.route("/recommendations")
@login_required
def recommendations():
    return render_template("recommendations.html")


@app.route("/api/recommendation", methods=["POST"])
@login_required
def recommendation():

    data = request.get_json(silent=True) or {}

    crop = data.get("crop", "").strip().lower()
    weather = data.get("weather", "").strip().lower()

    advice = []

    if "rice" in crop:
        advice.append(
            "Maintain adequate soil moisture because rice generally requires consistent water availability."
        )

    if "wheat" in crop:
        advice.append(
            "Monitor soil moisture and avoid unnecessary irrigation."
        )

    if "tomato" in crop:
        advice.append(
            "Regularly inspect plants for pests and disease symptoms."
        )

    if "maize" in crop or "corn" in crop:
        advice.append(
            "Ensure balanced irrigation and regularly monitor nutrient requirements."
        )

    if weather == "rain":
        advice.append(
            "Rainy conditions may reduce irrigation requirements. Avoid overwatering."
        )

    elif weather == "hot":
        advice.append(
            "Hot conditions can increase water loss. Monitor soil moisture more frequently."
        )

    elif weather == "cold":
        advice.append(
            "Cold conditions can slow crop growth. Monitor plants for stress and disease."
        )

    elif weather == "normal":
        advice.append(
            "Continue regular monitoring of soil moisture, crop health and pests."
        )

    if not advice:
        advice.append(
            "Monitor soil moisture, weather conditions and crop health regularly."
        )

    return jsonify({
        "advice": advice
    })


# =========================================================
# DELETE CROPS
# =========================================================

@app.route("/delete_crop/<int:id>")
@login_required
def delete_crop(id):

    user_id = session["user_id"]

    conn = get_db()

    conn.execute(
        """
        DELETE FROM crops
        WHERE id = ? AND user_id = ?
        """,
        (id, user_id)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("crops"))


# =========================================================
# DELETE EXPENSE
# =========================================================

@app.route("/delete_expense/<int:id>")
@login_required
def delete_expense(id):

    user_id = session["user_id"]

    conn = get_db()

    conn.execute(
        """
        DELETE FROM expenses
        WHERE id = ? AND user_id = ?
        """,
        (id, user_id)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("expenses"))


# =========================================================
# DELETE INCOME
# =========================================================

@app.route("/delete_income/<int:id>")
@login_required
def delete_income(id):

    user_id = session["user_id"]

    conn = get_db()

    conn.execute(
        """
        DELETE FROM income
        WHERE id = ? AND user_id = ?
        """,
        (id, user_id)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("income"))


# =========================================================
# DELETE IRRIGATION
# =========================================================

@app.route("/delete_irrigation/<int:id>")
@login_required
def delete_irrigation(id):

    user_id = session["user_id"]

    conn = get_db()

    conn.execute(
        """
        DELETE FROM irrigation
        WHERE id = ? AND user_id = ?
        """,
        (id, user_id)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("irrigation"))


# =========================================================
# DELETE PEST
# =========================================================

@app.route("/delete_pest/<int:id>")
@login_required
def delete_pest(id):

    user_id = session["user_id"]

    conn = get_db()

    conn.execute(
        """
        DELETE FROM pests
        WHERE id = ? AND user_id = ?
        """,
        (id, user_id)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("pests"))


# =========================================================
# ANALYTICS
# =========================================================

@app.route("/analytics")
@login_required
def analytics():

    user_id = session["user_id"]

    db = get_db()

    crops = db.execute(
        """
        SELECT * FROM crops
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    crop_names = []
    crop_income = []
    crop_expenses = []
    crop_profit = []

    for crop in crops:

        name = crop["name"]

        income_total = db.execute(
            """
            SELECT COALESCE(SUM(quantity * price), 0) AS total
            FROM income
            WHERE crop = ? AND user_id = ?
            """,
            (name, user_id)
        ).fetchone()["total"]

        expense_total = db.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE crop = ? AND user_id = ?
            """,
            (name, user_id)
        ).fetchone()["total"]

        crop_names.append(name)
        crop_income.append(income_total)
        crop_expenses.append(expense_total)
        crop_profit.append(income_total - expense_total)

    total_income = db.execute(
        """
        SELECT COALESCE(SUM(quantity * price), 0) AS total
        FROM income
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()["total"]

    total_expense = db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expenses
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()["total"]

    profit = total_income - total_expense

    db.close()

    return render_template(
        "analytics.html",
        crop_names=crop_names,
        crop_income=crop_income,
        crop_expenses=crop_expenses,
        crop_profit=crop_profit,
        total_income=total_income,
        total_expense=total_expense,
        profit=profit
    )


# =========================================================
# WEATHER
# =========================================================

@app.route("/weather", methods=["GET", "POST"])
@login_required
def weather():

    weather_data = None
    error = None
    city = ""

    if request.method == "POST":

        city = request.form.get(
            "city",
            ""
        ).strip()

        if not city:

            error = "Please enter a city."

        else:

            try:

                geo_url = (
                    "https://geocoding-api.open-meteo.com/v1/search?"
                    + urllib.parse.urlencode({
                        "name": city,
                        "count": 1,
                        "language": "en",
                        "format": "json"
                    })
                )

                with urllib.request.urlopen(
                    geo_url,
                    timeout=10
                ) as response:

                    geo_data = json.loads(
                        response.read().decode()
                    )

                if not geo_data.get("results"):

                    error = (
                        "City not found. Please try another city."
                    )

                else:

                    location = geo_data["results"][0]

                    latitude = location["latitude"]
                    longitude = location["longitude"]

                    weather_url = (
                        "https://api.open-meteo.com/v1/forecast?"
                        + urllib.parse.urlencode({
                            "latitude": latitude,
                            "longitude": longitude,
                            "current": (
                                "temperature_2m,"
                                "relative_humidity_2m,"
                                "precipitation,"
                                "wind_speed_10m,"
                                "weather_code"
                            ),
                            "timezone": "auto"
                        })
                    )

                    with urllib.request.urlopen(
                        weather_url,
                        timeout=10
                    ) as response:

                        weather_response = json.loads(
                            response.read().decode()
                        )

                    current = weather_response.get("current")

                    if not current:

                        error = (
                            "Weather data is currently unavailable."
                        )

                    else:

                        weather_data = {
                            "city": location["name"],
                            "country": location.get(
                                "country",
                                ""
                            ),
                            "temperature": current.get(
                                "temperature_2m"
                            ),
                            "humidity": current.get(
                                "relative_humidity_2m"
                            ),
                            "precipitation": current.get(
                                "precipitation"
                            ),
                            "wind": current.get(
                                "wind_speed_10m"
                            ),
                            "weather_code": current.get(
                                "weather_code"
                            )
                        }

            except Exception:

                error = (
                    "Unable to fetch weather data. "
                    "Please check your internet connection and try again."
                )

    return render_template(
        "weather.html",
        weather_data=weather_data,
        error=error,
        city=city
    )


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if "user_id" in session:
        return redirect(url_for("index"))

    error = None

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        db = get_db()

        user = db.execute(
            """
            SELECT * FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        db.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["user_name"] = user["name"]

            return redirect(url_for("index"))

        error = "Invalid email or password."

    return render_template(
        "login.html",
        error=error
    )


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if "user_id" in session:
        return redirect(url_for("index"))

    error = None

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not name or not email or not password:

            error = "Please fill all fields."

        elif len(password) < 6:

            error = (
                "Password must contain at least 6 characters."
            )

        else:

            db = get_db()

            try:

                db.execute(
                    """
                    INSERT INTO users
                    (name, email, password)
                    VALUES (?, ?, ?)
                    """,
                    (
                        name,
                        email,
                        generate_password_hash(password)
                    )
                )

                db.commit()

                return redirect(
                    url_for("login")
                )

            except sqlite3.IntegrityError:

                error = (
                    "An account with this email already exists."
                )

            finally:

                db.close()

    return render_template(
        "register.html",
        error=error
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
@login_required
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    create_tables()

    app.run(
        debug=False
    )