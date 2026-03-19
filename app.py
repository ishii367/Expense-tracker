from flask import Flask, render_template, request, redirect, url_for, session, Response
import bcrypt
import mysql.connector
import csv
from io import StringIO
from collections import defaultdict
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "super_secret_key"


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )


# ---------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, hashed)
        )
        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for("login"))

    return render_template("register.html")


# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = False
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"].encode()

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, password FROM users WHERE username = %s",
            (username,)
        )
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and bcrypt.checkpw(password, user[1]):
            session["user_id"] = user[0]
            return redirect(url_for("home"))

        error = True

    return render_template("login.html", error=error)


# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- DASHBOARD ----------
@app.route("/", methods=["GET", "POST"])
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    success = False   # ✅ ADDED

    # ---------- ADD EXPENSE ----------
    if request.method == "POST":
        try:
            cur.execute(
                """
                INSERT INTO expenses (user_id, title, amount, category, date)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    session["user_id"],
                    request.form.get("title"),
                    float(request.form.get("amount", 0)),
                    request.form.get("category"),
                    request.form.get("date")
                )
            )
            conn.commit()
            success = True   # ✅ ADDED
        except Exception as e:
            print("ERROR:", e)

    # ---------- FETCH EXPENSES ----------
    cur.execute(
        "SELECT id, title, amount, category, date FROM expenses WHERE user_id=%s",
        (session["user_id"],)
    )
    expenses = cur.fetchall()

    monthly = defaultdict(float)
    total = 0

    for e in expenses:
        e["formatted_date"] = f"{e['date'].day}/{e['date'].month}/{e['date'].year}"
        total += float(e["amount"])
        monthly[e["date"].strftime("%Y-%m")] += float(e["amount"])

    # ---------- BUDGET LOGIC ----------
    current_month = None
    budget = 0

    if monthly:
        current_month = sorted(monthly.keys())[-1]

        cur.execute(
            "SELECT amount FROM budgets WHERE user_id=%s AND month=%s",
            (session["user_id"], current_month)
        )
        result = cur.fetchone()

        if result:
            budget = float(result["amount"]) if isinstance(result, dict) else float(result[0])

    cur.close()
    conn.close()

    return render_template(
        "index.html",
        total=total,
        monthly_labels=list(monthly.keys()),
        monthly_values=list(monthly.values()),
        edit_expense=None,
        edit_index=None,
        budget=budget,
        current_month=current_month,
        success=success   # ✅ ADDED
    )

# ---------- UPDATE ----------
@app.route("/update/<int:index>", methods=["POST"])
def update(index):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute(
        "SELECT id FROM expenses WHERE user_id=%s",
        (session["user_id"],)
    )
    expenses = cur.fetchall()

    expense_id = expenses[index]["id"]

    cur.execute(
        """
        UPDATE expenses
        SET title=%s, amount=%s, category=%s, date=%s
        WHERE id=%s
        """,
        (
            request.form.get("title"),
            float(request.form.get("amount", 0)),
            request.form.get("category"),
            request.form.get("date"),
            expense_id
        )
    )

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("history"))


# ---------- DELETE ----------
@app.route("/delete/<int:index>")
def delete(index):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute(
        "SELECT id FROM expenses WHERE user_id=%s",
        (session["user_id"],)
    )
    expenses = cur.fetchall()

    if index < len(expenses):   # ✅ safety check
        expense_id = expenses[index]["id"]

        cur.execute(
            "DELETE FROM expenses WHERE id=%s",
            (expense_id,)
        )
        conn.commit()

    cur.close()
    conn.close()

    return redirect(url_for("history"))

@app.route("/delete_user")
def delete_user():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db_connection()
    cur = conn.cursor()

    # delete expenses first
    cur.execute("DELETE FROM expenses WHERE user_id=%s", (user_id,))

    # delete user
    cur.execute("DELETE FROM users WHERE id=%s", (user_id,))

    conn.commit()
    cur.close()
    conn.close()

    session.clear()

    return redirect(url_for("register"))


# ---------- SPLIT ----------
@app.route("/split", methods=["POST"])
def split_bill():
    if "user_id" not in session:
        return redirect(url_for("login"))

    per_person = round(
        float(request.form.get("total", 0)) / int(request.form.get("people", 1)), 2
    )

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO expenses (user_id, title, amount, category, date)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            session["user_id"],
            "Split Bill (Group Expense)",
            per_person,
            "Split Bill",
            request.form.get("date")
        )
    )

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("history"))


# ---------- HISTORY ----------
@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute(
        "SELECT id, title, amount, category, date FROM expenses WHERE user_id=%s",
        (session["user_id"],)
    )
    expenses = cur.fetchall()

    for e in expenses:
        e["formatted_date"] = f"{e['date'].day}/{e['date'].month}/{e['date'].year}"

    months = sorted({e["date"].strftime("%Y-%m") for e in expenses})

    cur.close()
    conn.close()

    return render_template(
        "history.html",
        expenses=expenses,
        months=months,
        selected_category=None,
        selected_month=None,
        search_query=""
    )


# ---------- EXPORT ----------
@app.route("/export")
def export_csv():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT title, amount, category, date FROM expenses WHERE user_id=%s",
        (session["user_id"],)
    )
    rows = cur.fetchall()

    cur.close()
    conn.close()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["Title", "Amount", "Category", "Date"])
    writer.writerows(rows)

    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=expenses.csv"}
    )

from openpyxl import Workbook
from flask import send_file
import io


# ---------- EXPORT EXCEL ----------
@app.route("/export_excel")
def export_excel():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT title, amount, category, date FROM expenses WHERE user_id=%s",
        (session["user_id"],)
    )
    rows = cur.fetchall()

    cur.close()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Expenses"

    ws.append(["Title", "Amount", "Category", "Date"])

    for row in rows:
        ws.append([
            row[0],
            float(row[1]),
            row[2],
            row[3].strftime("%d/%m/%Y")
        ])

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="expenses.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )    

# ---------- EDIT ----------
@app.route("/edit/<int:index>")
def edit(index):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute(
        "SELECT * FROM expenses WHERE user_id=%s",
        (session["user_id"],)
    )
    expenses = cur.fetchall()

    edit_expense = expenses[index]

    # prepare chart again
    monthly = defaultdict(float)
    total = 0

    for e in expenses:
        total += float(e["amount"])
        monthly[e["date"].strftime("%Y-%m")] += float(e["amount"])

    cur.close()
    conn.close()

    return render_template(
        "index.html",
        total=total,
        monthly_labels=list(monthly.keys()),
        monthly_values=list(monthly.values()),
        edit_expense=edit_expense,
        edit_index=index
    )

# ---------- SET BUDGET ----------
@app.route("/set_budget", methods=["POST"])
def set_budget():
    if "user_id" not in session:
        return redirect(url_for("login"))

    amount = float(request.form.get("amount", 0))
    month = request.form.get("month")

    conn = get_db_connection()
    cur = conn.cursor()

    # check if already exists
    cur.execute(
        "SELECT id FROM budgets WHERE user_id=%s AND month=%s",
        (session["user_id"], month)
    )
    existing = cur.fetchone()

    if existing:
        cur.execute(
            "UPDATE budgets SET amount=%s WHERE user_id=%s AND month=%s",
            (amount, session["user_id"], month)
        )
    else:
        cur.execute(
            "INSERT INTO budgets (user_id, amount, month) VALUES (%s,%s,%s)",
            (session["user_id"], amount, month)
        )

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=False)