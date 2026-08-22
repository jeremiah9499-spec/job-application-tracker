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


    # USERS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)


    # APPLICATIONS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id SERIAL PRIMARY KEY,
            company_name TEXT NOT NULL,
            job_title TEXT NOT NULL,
            status TEXT NOT NULL,
            date_applied DATE NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        )
    """)


    # This handles the existing applications table
    # that was created before users existed.
    cursor.execute("""
        ALTER TABLE applications
        ADD COLUMN IF NOT EXISTS user_id
        INTEGER REFERENCES users(id)
        ON DELETE CASCADE
    """)


    connection.commit()

    cursor.close()
    connection.close()


# -------------------------
# LOGIN REQUIRED DECORATOR
# -------------------------

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


# -------------------------
# SMS REMINDER FUNCTION
# -------------------------

def send_sms_reminder():

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


    message = client.messages.create(

        body="sms_internal_alerts",

        from_=os.environ[
            "TWILIO_PHONE_NUMBER"
        ],

        to=os.environ[
            "MY_PHONE_NUMBER"
        ]
    )


    return message.sid


# Make sure database tables exist
init_db()


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


        # -------------------------
        # VALIDATION
        # -------------------------

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


        # Check whether email already exists
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


        # Hash password before saving it
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


        # Automatically log user in
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
# HOME PAGE
# =================================================

@app.route("/")
@login_required
def home():

    user_id = session["user_id"]


    connection = get_db_connection()

    cursor = connection.cursor()


    # Only load THIS USER'S applications
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


    cursor.close()
    connection.close()


    # -------------------------
    # DAYS WAITING
    # -------------------------

    applications_with_days = []


    for application in applications:

        date_applied = application[4]


        if isinstance(
            date_applied,
            str
        ):

            date_applied = datetime.strptime(
                date_applied,
                "%Y-%m-%d"
            ).date()


        days_since = (
            date.today()
            - date_applied
        ).days


        applications_with_days.append(
            application
            + (days_since,)
        )


    return render_template(
        "index.html",
        applications=applications_with_days,
        total=total,
        applied=applied,
        interviews=interviews,
        offers=offers
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


    # user_id is included here for security.
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


# =================================================
# START FLASK
# =================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )