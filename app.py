from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash
)
from datetime import datetime, date
from twilio.rest import Client
import psycopg
import os


app = Flask(__name__)


# -------------------------
# FLASK SECRET KEY
# -------------------------

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "development-secret-key"
)


# -------------------------
# DATABASE CONNECTION
# -------------------------

def get_db_connection():
    database_url = os.environ["DATABASE_URL"]

    connection = psycopg.connect(
        database_url
    )

    return connection


# -------------------------
# DATABASE SETUP
# -------------------------

def init_db():
    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id SERIAL PRIMARY KEY,
            company_name TEXT NOT NULL,
            job_title TEXT NOT NULL,
            status TEXT NOT NULL,
            date_applied DATE NOT NULL
        )
    """)

    connection.commit()

    cursor.close()
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


# Make sure database table exists
init_db()


# -------------------------
# HOME PAGE
# -------------------------

@app.route("/")
def home():
    connection = get_db_connection()

    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM applications ORDER BY id DESC"
    )

    applications = cursor.fetchall()


    cursor.execute(
        "SELECT COUNT(*) FROM applications"
    )

    total = cursor.fetchone()[0]


    cursor.execute(
        """
        SELECT COUNT(*)
        FROM applications
        WHERE status = %s
        """,
        ("Applied",)
    )

    applied = cursor.fetchone()[0]


    cursor.execute(
        """
        SELECT COUNT(*)
        FROM applications
        WHERE status = %s
        """,
        ("Interview",)
    )

    interviews = cursor.fetchone()[0]


    cursor.execute(
        """
        SELECT COUNT(*)
        FROM applications
        WHERE status = %s
        """,
        ("Offered",)
    )

    offers = cursor.fetchone()[0]


    cursor.close()
    connection.close()


    # -------------------------
    # CALCULATE DAYS WAITING
    # -------------------------

    applications_with_days = []

    for application in applications:

        date_applied = application[4]

        # PostgreSQL returns DATE values
        # as real Python date objects.
        if isinstance(date_applied, str):
            date_applied = datetime.strptime(
                date_applied,
                "%Y-%m-%d"
            ).date()

        days_since = (
            date.today() - date_applied
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


        connection = get_db_connection()

        cursor = connection.cursor()


        cursor.execute(
            """
            INSERT INTO applications (
                company_name,
                job_title,
                status,
                date_applied
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                company,
                job_title,
                status,
                date_applied
            )
        )


        connection.commit()

        cursor.close()
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

    connection = get_db_connection()

    cursor = connection.cursor()


    cursor.execute(
        """
        DELETE FROM applications
        WHERE id = %s
        """,
        (id,)
    )


    connection.commit()

    cursor.close()
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

@app.route(
    "/edit/<int:id>",
    methods=["GET", "POST"]
)
def edit_job(id):

    connection = get_db_connection()

    cursor = connection.cursor()


    if request.method == "POST":

        company = request.form["company_name"]

        job_title = request.form["job_title"]

        status = request.form["status"]

        date_applied = request.form["date_applied"]


        cursor.execute(
            """
            UPDATE applications
            SET company_name = %s,
                job_title = %s,
                status = %s,
                date_applied = %s
            WHERE id = %s
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

        cursor.close()
        connection.close()


        flash(
            "Application updated successfully!",
            "success"
        )


        return redirect(
            url_for("home")
        )


    cursor.execute(
        """
        SELECT * FROM applications
        WHERE id = %s
        """,
        (id,)
    )


    application = cursor.fetchone()


    cursor.close()
    connection.close()


    if not application:

        flash(
            "Application could not be found.",
            "error"
        )

        return redirect(
            url_for("home")
        )


    return render_template(
        "edit_job.html",
        application=application
    )


# -------------------------
# SMS REMINDER
# -------------------------

@app.route("/remind/<int:id>")
def remind_job(id):

    connection = get_db_connection()

    cursor = connection.cursor()


    cursor.execute(
        """
        SELECT * FROM applications
        WHERE id = %s
        """,
        (id,)
    )


    application = cursor.fetchone()


    cursor.close()
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

        print(
            "Twilio error:",
            error
        )

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