from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash
)
from datetime import datetime
from twilio.rest import Client
import sqlite3
import os


app = Flask(__name__)

# Flask needs a secret key to use flash messages.
# For local development, this fallback is okay.
# Later, before deployment, we'll move this into an environment variable.
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "development-secret-key"
)


# -------------------------
# DATABASE SETUP
# -------------------------

def init_db():
    connection = sqlite3.connect("jobs.db")

    connection.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            job_title TEXT NOT NULL,
            status TEXT NOT NULL,
            date_applied DATE NOT NULL
        )
    """)

    connection.commit()
    connection.close()


# -------------------------
# SMS REMINDER FUNCTION
# -------------------------

def send_sms_reminder():
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]

    client = Client(
        account_sid,
        auth_token
    )

    message = client.messages.create(
        body="sms_internal_alerts",
        from_=os.environ["TWILIO_PHONE_NUMBER"],
        to=os.environ["MY_PHONE_NUMBER"]
    )

    return message.sid


# Make sure database exists
init_db()


# -------------------------
# HOME PAGE
# -------------------------

@app.route("/")
def home():
    connection = sqlite3.connect("jobs.db")

    applications = connection.execute(
        "SELECT * FROM applications"
    ).fetchall()

    total = connection.execute(
        "SELECT COUNT(*) FROM applications"
    ).fetchone()[0]

    applied = connection.execute(
        "SELECT COUNT(*) FROM applications WHERE status = ?",
        ("Applied",)
    ).fetchone()[0]

    interviews = connection.execute(
        "SELECT COUNT(*) FROM applications WHERE status = ?",
        ("Interview",)
    ).fetchone()[0]

    offers = connection.execute(
        "SELECT COUNT(*) FROM applications WHERE status = ?",
        ("Offered",)
    ).fetchone()[0]

    connection.close()

    applications_with_days = []

    for application in applications:
        date_applied = datetime.strptime(
            application[4],
            "%Y-%m-%d"
        )

        days_since = (
            datetime.now() - date_applied
        ).days

        applications_with_days.append(
            application + (days_since,)
        )

    return render_template(
        "index.html",
        applications=applications_with_days,
        total=total,
        applied=applied,
        interviews=interviews,
        offers=offers
    )


# -------------------------
# ADD APPLICATION
# -------------------------

@app.route("/add", methods=["GET", "POST"])
def add_job():

    if request.method == "POST":
        company = request.form["company_name"]
        job_title = request.form["job_title"]
        status = request.form["status"]
        date_applied = request.form["date_applied"]

        connection = sqlite3.connect("jobs.db")

        connection.execute(
            """
            INSERT INTO applications (
                company_name,
                job_title,
                status,
                date_applied
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                company,
                job_title,
                status,
                date_applied
            )
        )

        connection.commit()
        connection.close()

        flash(
            "Application added successfully!",
            "success"
        )

        return redirect(
            url_for("home")
        )

    return render_template(
        "add_job.html"
    )


# -------------------------
# DELETE APPLICATION
# -------------------------

@app.route("/delete/<int:id>")
def delete_job(id):
    connection = sqlite3.connect("jobs.db")

    connection.execute(
        "DELETE FROM applications WHERE id = ?",
        (id,)
    )

    connection.commit()
    connection.close()

    flash(
        "Application deleted.",
        "success"
    )

    return redirect(
        url_for("home")
    )


# -------------------------
# EDIT APPLICATION
# -------------------------

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_job(id):
    connection = sqlite3.connect("jobs.db")

    if request.method == "POST":
        company = request.form["company_name"]
        job_title = request.form["job_title"]
        status = request.form["status"]
        date_applied = request.form["date_applied"]

        connection.execute(
            """
            UPDATE applications
            SET company_name = ?,
                job_title = ?,
                status = ?,
                date_applied = ?
            WHERE id = ?
            """,
            (
                company,
                job_title,
                status,
                date_applied,
                id
            )
        )

        connection.commit()
        connection.close()

        flash(
            "Application updated successfully!",
            "success"
        )

        return redirect(
            url_for("home")
        )

    application = connection.execute(
        "SELECT * FROM applications WHERE id = ?",
        (id,)
    ).fetchone()

    connection.close()

    return render_template(
        "edit_job.html",
        application=application
    )


# -------------------------
# SMS REMINDER
# -------------------------

@app.route("/remind/<int:id>")
def remind_job(id):
    connection = sqlite3.connect("jobs.db")

    application = connection.execute(
        "SELECT * FROM applications WHERE id = ?",
        (id,)
    ).fetchone()

    connection.close()

    if not application:
        flash(
            "Application could not be found.",
            "error"
        )

        return redirect(
            url_for("home")
        )

    try:
        send_sms_reminder()

        flash(
            "SMS reminder sent successfully!",
            "success"
        )

    except Exception as error:
        print("Twilio error:", error)

        flash(
            "SMS reminder could not be sent.",
            "error"
        )

    return redirect(
        url_for("home")
    )


# -------------------------
# START FLASK
# -------------------------

if __name__ == "__main__":
    app.run(debug=True)