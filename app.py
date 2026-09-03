from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)

from datetime import datetime, date
from functools import wraps

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from twilio.rest import Client

import psycopg
import os
import re


app = Flask(__name__)


# =================================================
# FLASK SECRET KEY
# =================================================

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "development-secret-key"
)


# =================================================
# DATABASE CONNECTION
# =================================================

def get_db_connection():

    database_url = os.environ["DATABASE_URL"]

    return psycopg.connect(
        database_url
    )


# =================================================
# DATABASE SETUP
# =================================================

def init_db():

    connection = get_db_connection()
    cursor = connection.cursor()


    # USERS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            phone_number TEXT
        )
    """)


    cursor.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS phone_number TEXT
    """)


    # APPLICATIONS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id SERIAL PRIMARY KEY,
            company_name TEXT NOT NULL,
            job_title TEXT NOT NULL,
            status TEXT NOT NULL,
            date_applied DATE NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            last_follow_up DATE,
            follow_up_count INTEGER NOT NULL DEFAULT 0
        )
    """)


    cursor.execute("""
        ALTER TABLE applications
        ADD COLUMN IF NOT EXISTS user_id
        INTEGER REFERENCES users(id)
        ON DELETE CASCADE
    """)


    # FOLLOW-UP FIELDS
    cursor.execute("""
        ALTER TABLE applications
        ADD COLUMN IF NOT EXISTS last_follow_up DATE
    """)


    cursor.execute("""
        ALTER TABLE applications
        ADD COLUMN IF NOT EXISTS follow_up_count
        INTEGER NOT NULL DEFAULT 0
    """)


    connection.commit()

    cursor.close()
    connection.close()


# =================================================
# LOGIN REQUIRED
# =================================================

def login_required(view_function):

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):

        if "user_id" not in session:

            flash(
                "Please log in to continue.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        return view_function(
            *args,
            **kwargs
        )

    return wrapped_view


# =================================================
# PHONE NUMBER VALIDATION
# =================================================

def valid_phone_number(phone_number):

    pattern = r"^\+[1-9]\d{7,14}$"

    return bool(
        re.match(
            pattern,
            phone_number
        )
    )


# =================================================
# DATE HELPER
# =================================================

def make_date(value):

    if isinstance(
        value,
        str
    ):

        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).date()

    return value


# =================================================
# DOES APPLICATION NEED FOLLOW-UP?
# =================================================

def needs_follow_up(
    date_applied,
    last_follow_up
):

    date_applied = make_date(
        date_applied
    )

    if last_follow_up:

        last_follow_up = make_date(
            last_follow_up
        )


    days_waiting = (
        date.today()
        - date_applied
    ).days


    if last_follow_up is None:

        return (
            days_waiting > 7,
            days_waiting,
            None
        )


    days_since_follow_up = (
        date.today()
        - last_follow_up
    ).days


    return (
        days_since_follow_up > 7,
        days_waiting,
        days_since_follow_up
    )


# =================================================
# SMS REMINDER
# =================================================

def send_sms_reminder(
    phone_number,
    company_name,
    job_title,
    days_waiting
):

    account_sid = os.environ[
        "TWILIO_ACCOUNT_SID"
    ]

    auth_token = os.environ[
        "TWILIO_AUTH_TOKEN"
    ]


    client = Client(
        account_sid,
        auth_token
    )


    trial_mode = os.environ.get(
        "TWILIO_TRIAL_MODE",
        "true"
    ).lower() == "true"


    if trial_mode:

        message_body = (
            "sms_internal_alerts"
        )

    else:

        message_body = (
            f"NextStride Reminder: "
            f"You applied to {company_name} "
            f"for {job_title} "
            f"{days_waiting} days ago. "
            f"It may be time to follow up."
        )


    message = client.messages.create(

        body=message_body,

        from_=os.environ[
            "TWILIO_PHONE_NUMBER"
        ],

        to=phone_number
    )


    return message.sid


# Create/update database tables
init_db()


# =================================================
# LANDING PAGE
# =================================================

@app.route("/")
def landing():

    return render_template(
        "landing.html"
    )


# =================================================
# SIGN UP
# =================================================

@app.route(
    "/signup",
    methods=["GET", "POST"]
)
def signup():

    if "user_id" in session:

        return redirect(
            url_for("home")
        )


    if request.method == "POST":

        email = (
            request.form["email"]
            .strip()
            .lower()
        )

        password = request.form[
            "password"
        ]

        confirm_password = request.form[
            "confirm_password"
        ]


        if not email:

            flash(
                "Email is required.",
                "error"
            )

            return render_template(
                "signup.html"
            )


        if len(password) < 8:

            flash(
                "Password must be at least 8 characters.",
                "error"
            )

            return render_template(
                "signup.html"
            )


        if password != confirm_password:

            flash(
                "Passwords do not match.",
                "error"
            )

            return render_template(
                "signup.html"
            )


        connection = get_db_connection()
        cursor = connection.cursor()


        cursor.execute(
            """
            SELECT id
            FROM users
            WHERE email = %s
            """,
            (email,)
        )


        existing_user = cursor.fetchone()


        if existing_user:

            cursor.close()
            connection.close()

            flash(
                "An account with that email already exists.",
                "error"
            )

            return render_template(
                "signup.html"
            )


        password_hash = generate_password_hash(
            password
        )


        cursor.execute(
            """
            INSERT INTO users (
                email,
                password_hash
            )
            VALUES (%s, %s)
            RETURNING id
            """,
            (
                email,
                password_hash
            )
        )


        new_user = cursor.fetchone()

        user_id = new_user[0]


        connection.commit()

        cursor.close()
        connection.close()


        session.clear()

        session["user_id"] = user_id
        session["user_email"] = email


        flash(
            "Account created successfully!",
            "success"
        )


        return redirect(
            url_for("home")
        )


    return render_template(
        "signup.html"
    )


# =================================================
# LOGIN
# =================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if "user_id" in session:

        return redirect(
            url_for("home")
        )


    if request.method == "POST":

        email = (
            request.form["email"]
            .strip()
            .lower()
        )

        password = request.form[
            "password"
        ]


        connection = get_db_connection()
        cursor = connection.cursor()


        cursor.execute(
            """
            SELECT
                id,
                email,
                password_hash
            FROM users
            WHERE email = %s
            """,
            (email,)
        )


        user = cursor.fetchone()


        cursor.close()
        connection.close()


        if user is None:

            flash(
                "Incorrect email or password.",
                "error"
            )

            return render_template(
                "login.html"
            )


        if not check_password_hash(
            user[2],
            password
        ):

            flash(
                "Incorrect email or password.",
                "error"
            )

            return render_template(
                "login.html"
            )


        session.clear()

        session["user_id"] = user[0]
        session["user_email"] = user[1]


        flash(
            "Welcome back!",
            "success"
        )


        return redirect(
            url_for("home")
        )


    return render_template(
        "login.html"
    )


# =================================================
# LOGOUT
# =================================================

@app.route("/logout")
def logout():

    session.clear()


    flash(
        "You have been logged out.",
        "success"
    )


    return redirect(
        url_for("login")
    )


# =================================================
# ACCOUNT SETTINGS
# =================================================

@app.route(
    "/settings",
    methods=["GET", "POST"]
)
@login_required
def settings():

    user_id = session[
        "user_id"
    ]


    connection = get_db_connection()
    cursor = connection.cursor()


    if request.method == "POST":

        phone_number = (
            request.form["phone_number"]
            .strip()
        )


        if phone_number:

            if not valid_phone_number(
                phone_number
            ):

                cursor.close()
                connection.close()

                flash(
                    "Enter your phone number in international format, for example +14045551234.",
                    "error"
                )

                return redirect(
                    url_for("settings")
                )


        cursor.execute(
            """
            UPDATE users
            SET phone_number = %s
            WHERE id = %s
            """,
            (
                phone_number
                if phone_number
                else None,
                user_id
            )
        )


        connection.commit()

        cursor.close()
        connection.close()


        flash(
            "Account settings updated!",
            "success"
        )


        return redirect(
            url_for("settings")
        )


    cursor.execute(
        """
        SELECT
            email,
            phone_number
        FROM users
        WHERE id = %s
        """,
        (user_id,)
    )


    user = cursor.fetchone()


    cursor.close()
    connection.close()


    return render_template(
        "settings.html",
        user=user
    )


# =================================================
# PRIVATE DASHBOARD
# =================================================

@app.route("/dashboard")
@login_required
def home():

    user_id = session[
        "user_id"
    ]


    connection = get_db_connection()
    cursor = connection.cursor()


    # -------------------------
    # USER APPLICATIONS
    # -------------------------

    cursor.execute(
        """
        SELECT
            id,
            company_name,
            job_title,
            status,
            date_applied
        FROM applications
        WHERE user_id = %s
        ORDER BY id DESC
        LIMIT 5
        """,
        (user_id,)
    )


    applications = cursor.fetchall()


    # -------------------------
    # TOTAL
    # -------------------------

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM applications
        WHERE user_id = %s
        """,
        (user_id,)
    )

    total = cursor.fetchone()[0]


    # -------------------------
    # APPLIED
    # -------------------------

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM applications
        WHERE user_id = %s
        AND status = %s
        """,
        (
            user_id,
            "Applied"
        )
    )

    applied = cursor.fetchone()[0]


    # -------------------------
    # INTERVIEWS
    # -------------------------

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM applications
        WHERE user_id = %s
        AND status = %s
        """,
        (
            user_id,
            "Interview"
        )
    )

    interviews = cursor.fetchone()[0]


    # -------------------------
    # OFFERS
    # -------------------------

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM applications
        WHERE user_id = %s
        AND status = %s
        """,
        (
            user_id,
            "Offered"
        )
    )

    offers = cursor.fetchone()[0]


    # -------------------------
    # FOLLOW-UP CANDIDATES
    # -------------------------

    cursor.execute(
        """
        SELECT
            id,
            company_name,
            job_title,
            date_applied,
            last_follow_up
        FROM applications
        WHERE user_id = %s
        AND status = %s
        ORDER BY date_applied ASC
        """,
        (
            user_id,
            "Applied"
        )
    )


    follow_up_candidates = (
        cursor.fetchall()
    )


    cursor.close()
    connection.close()


    # -------------------------
    # DAYS WAITING
    # -------------------------

    applications_with_days = []


    for application in applications:

        date_applied = make_date(
            application[4]
        )


        days_since = (
            date.today()
            - date_applied
        ).days


        applications_with_days.append(
            application
            + (days_since,)
        )


    # -------------------------
    # DASHBOARD FOLLOW-UP PREVIEW
    # -------------------------

    follow_up_preview = []


    for application in follow_up_candidates:

        needs_attention, days_waiting, _ = (
            needs_follow_up(
                application[3],
                application[4]
            )
        )


        if needs_attention:

            follow_up_preview.append(
                {
                    "id": application[0],
                    "company_name": application[1],
                    "job_title": application[2],
                    "days_waiting": days_waiting
                }
            )


    return render_template(
        "index.html",
        applications=applications_with_days,
        total=total,
        applied=applied,
        interviews=interviews,
        offers=offers,
        follow_up_preview=follow_up_preview,
        follow_up_count=len(
            follow_up_preview
        )
    )


# =================================================
# APPLICATIONS PAGE
# =================================================

@app.route("/applications")
@login_required
def applications_page():

    user_id = session[
        "user_id"
    ]

    connection = get_db_connection()
    cursor = connection.cursor()

    # -------------------------
    # LOAD THIS USER'S
    # APPLICATIONS
    # -------------------------

    cursor.execute(
        """
        SELECT
            id,
            company_name,
            job_title,
            status,
            date_applied

        FROM applications

        WHERE user_id = %s

        ORDER BY id DESC
        """,
        (user_id,)
    )

    applications = cursor.fetchall()

    cursor.close()
    connection.close()

    # -------------------------
    # CALCULATE DAYS WAITING
    # -------------------------

    applications_with_days = []

    for application in applications:

        date_applied = make_date(
            application[4]
        )

        days_waiting = (
            date.today()
            - date_applied
        ).days

        applications_with_days.append(
            application
            + (days_waiting,)
        )

    return render_template(
        "applications.html",
        applications=applications_with_days
    )


# =================================================
# FOLLOW UPS PAGE
# =================================================

@app.route("/follow-ups")
@login_required
def follow_ups():

    user_id = session[
        "user_id"
    ]


    connection = get_db_connection()
    cursor = connection.cursor()


    cursor.execute(
        """
        SELECT
            id,
            company_name,
            job_title,
            status,
            date_applied,
            last_follow_up,
            follow_up_count
        FROM applications
        WHERE user_id = %s
        AND status = %s
        ORDER BY date_applied ASC
        """,
        (
            user_id,
            "Applied"
        )
    )


    applications = cursor.fetchall()


    cursor.close()
    connection.close()


    follow_up_applications = []


    for application in applications:

        needs_attention, days_waiting, days_since_follow_up = (
            needs_follow_up(
                application[4],
                application[5]
            )
        )


        if needs_attention:

            follow_up_applications.append(
                {
                    "id": application[0],
                    "company_name": application[1],
                    "job_title": application[2],
                    "status": application[3],
                    "date_applied": make_date(
                        application[4]
                    ),
                    "last_follow_up": (
                        make_date(
                            application[5]
                        )
                        if application[5]
                        else None
                    ),
                    "follow_up_count": application[6],
                    "days_waiting": days_waiting,
                    "days_since_follow_up": (
                        days_since_follow_up
                    )
                }
            )


    return render_template(
        "follow_ups.html",
        applications=follow_up_applications
    )


# =================================================
# MARK FOLLOWED UP
# =================================================

@app.route(
    "/follow-up/<int:id>",
    methods=["POST"]
)
@login_required
def mark_followed_up(id):

    user_id = session[
        "user_id"
    ]


    connection = get_db_connection()
    cursor = connection.cursor()


    cursor.execute(
        """
        UPDATE applications
        SET last_follow_up = CURRENT_DATE,
            follow_up_count = follow_up_count + 1
        WHERE id = %s
        AND user_id = %s
        RETURNING id
        """,
        (
            id,
            user_id
        )
    )


    updated_application = (
        cursor.fetchone()
    )


    connection.commit()

    cursor.close()
    connection.close()


    if not updated_application:

        flash(
            "Application could not be found.",
            "error"
        )

    else:

        flash(
            "Follow-up marked complete!",
            "success"
        )


    return redirect(
        url_for("follow_ups")
    )


# =================================================
# ADD APPLICATION
# =================================================

@app.route(
    "/add",
    methods=["GET", "POST"]
)
@login_required
def add_job():

    if request.method == "POST":

        company = request.form[
            "company_name"
        ]

        job_title = request.form[
            "job_title"
        ]

        status = request.form[
            "status"
        ]

        date_applied = request.form[
            "date_applied"
        ]

        user_id = session[
            "user_id"
        ]


        connection = get_db_connection()
        cursor = connection.cursor()


        cursor.execute(
            """
            INSERT INTO applications (
                company_name,
                job_title,
                status,
                date_applied,
                user_id
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                company,
                job_title,
                status,
                date_applied,
                user_id
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


# =================================================
# DELETE APPLICATION
# =================================================

@app.route(
    "/delete/<int:id>"
)
@login_required
def delete_job(id):

    user_id = session[
        "user_id"
    ]


    connection = get_db_connection()
    cursor = connection.cursor()


    cursor.execute(
        """
        DELETE FROM applications
        WHERE id = %s
        AND user_id = %s
        """,
        (
            id,
            user_id
        )
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


# =================================================
# EDIT APPLICATION
# =================================================

@app.route(
    "/edit/<int:id>",
    methods=["GET", "POST"]
)
@login_required
def edit_job(id):

    user_id = session[
        "user_id"
    ]


    connection = get_db_connection()
    cursor = connection.cursor()


    if request.method == "POST":

        company = request.form[
            "company_name"
        ]

        job_title = request.form[
            "job_title"
        ]

        status = request.form[
            "status"
        ]

        date_applied = request.form[
            "date_applied"
        ]


        cursor.execute(
            """
            UPDATE applications
            SET company_name = %s,
                job_title = %s,
                status = %s,
                date_applied = %s
            WHERE id = %s
            AND user_id = %s
            """,
            (
                company,
                job_title,
                status,
                date_applied,
                id,
                user_id
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
        SELECT
            id,
            company_name,
            job_title,
            status,
            date_applied
        FROM applications
        WHERE id = %s
        AND user_id = %s
        """,
        (
            id,
            user_id
        )
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


# =================================================
# SMS REMINDER
# =================================================

@app.route(
    "/remind/<int:id>"
)
@login_required
def remind_job(id):

    user_id = session[
        "user_id"
    ]


    connection = get_db_connection()
    cursor = connection.cursor()


    cursor.execute(
        """
        SELECT
            applications.id,
            applications.company_name,
            applications.job_title,
            applications.status,
            applications.date_applied,
            users.phone_number
        FROM applications
        JOIN users
        ON users.id = applications.user_id
        WHERE applications.id = %s
        AND applications.user_id = %s
        """,
        (
            id,
            user_id
        )
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


    phone_number = application[5]


    if not phone_number:

        flash(
            "Add your phone number in Account Settings before sending SMS reminders.",
            "error"
        )

        return redirect(
            url_for("settings")
        )


    company_name = application[1]
    job_title = application[2]

    date_applied = make_date(
        application[4]
    )


    days_waiting = (
        date.today()
        - date_applied
    ).days


    try:

        send_sms_reminder(
            phone_number,
            company_name,
            job_title,
            days_waiting
        )


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
            "SMS reminder could not be sent. If you are using a Twilio trial account, the destination number may need to be verified.",
            "error"
        )


    next_page = request.args.get(
        "next"
    )


    if next_page == "follow_ups":

        return redirect(
            url_for("follow_ups")
        )


    return redirect(
        url_for("home")
    )


# =================================================
# START FLASK
# =================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )