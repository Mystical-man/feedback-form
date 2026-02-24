"""
Feedback Collection for Events or Courses
A simple Flask app with SQLite. Single file, no ORM, beginner-friendly.
"""

import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from contextlib import contextmanager

# -----------------------------------------------------------------------------
# App and config
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "feedback-app-secret-key-change-in-production"
# SQLite DB path: instance/feedback.db
DATABASE = os.path.join(app.instance_path, "feedback.db")

# Question types we support
QUESTION_TYPES = [
    ("short_text", "Short Text"),
    ("long_text", "Long Text"),
    ("multiple_choice", "Multiple Choice (single)"),
    ("rating", "Rating (1-5)"),
]


# -----------------------------------------------------------------------------
# Database helpers (no ORM – raw SQLite)
# -----------------------------------------------------------------------------

def get_instance_path():
    """Ensure instance folder exists for SQLite file."""
    if not os.path.exists(app.instance_path):
        os.makedirs(app.instance_path)


def get_db():
    """Open a connection to the SQLite database."""
    get_instance_path()
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # so we get dict-like rows
    return conn


@contextmanager
def db_cursor():
    """Context manager: get a cursor and commit on success, rollback on error."""
    conn = get_db()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """
    Create all tables if they do not exist.
    Tables: forms, questions, responses, answers
    """
    with db_cursor() as cur:
        # Forms: each feedback form
        cur.execute("""
            CREATE TABLE IF NOT EXISTS forms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Questions: belong to a form
        cur.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                form_id INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                question_type TEXT NOT NULL,
                options TEXT,
                is_required INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (form_id) REFERENCES forms(id) ON DELETE CASCADE
            )
        """)
        # Responses: one per submission (who submitted, when)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                form_id INTEGER NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_anonymous INTEGER DEFAULT 1,
                respondent_name TEXT,
                respondent_email TEXT,
                FOREIGN KEY (form_id) REFERENCES forms(id) ON DELETE CASCADE
            )
        """)
        # Answers: one per question per response (actual answer data)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                response_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                answer_text TEXT,
                rating_value INTEGER,
                FOREIGN KEY (response_id) REFERENCES responses(id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
            )
        """)


# -----------------------------------------------------------------------------
# Route: Home – list all forms
# -----------------------------------------------------------------------------

@app.route("/")
def index():
    """Home page: show all forms with links to submit and view summary."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, title, description, created_at FROM forms ORDER BY created_at DESC"
        )
        forms = [dict(row) for row in cur.fetchall()]
    return render_template("index.html", forms=forms)


# -----------------------------------------------------------------------------
# Route: Create form (GET: show form, POST: save form + questions)
# -----------------------------------------------------------------------------

@app.route("/create", methods=["GET", "POST"])
def create_form():
    """Create a new feedback form with questions."""
    if request.method == "GET":
        return render_template("create_form.html", question_types=QUESTION_TYPES)

    # POST: save form and questions
    title = request.form.get("form_title", "").strip()
    description = request.form.get("form_description", "").strip()

    if not title:
        flash("Form title is required.", "error")
        return redirect(url_for("create_form"))

    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO forms (title, description) VALUES (?, ?)",
            (title, description),
        )
        form_id = cur.lastrowid

        # Collect question data from form (we use repeated name fields)
        # Fields: question_text_1, question_type_1, options_1, required_1, etc.
        idx = 1
        while True:
            qtext = request.form.get(f"question_text_{idx}", "").strip()
            if not qtext:
                break
            qtype = request.form.get(f"question_type_{idx}", "short_text")
            options = request.form.get(f"options_{idx}", "").strip()
            required = 1 if request.form.get(f"required_{idx}") == "on" else 0

            cur.execute(
                """INSERT INTO questions (form_id, question_text, question_type, options, is_required, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (form_id, qtext, qtype, options if qtype == "multiple_choice" else None, required, idx),
            )
            idx += 1

    flash("Form created successfully. Share the link below for responses.", "success")
    return redirect(url_for("form_submit_page", form_id=form_id))


# -----------------------------------------------------------------------------
# Route: Submit feedback (public URL)
# -----------------------------------------------------------------------------

@app.route("/form/<int:form_id>/submit", methods=["GET", "POST"])
def form_submit_page(form_id):
    """Display form for submitting feedback (GET) or save responses (POST)."""
    with db_cursor() as cur:
        cur.execute("SELECT id, title, description FROM forms WHERE id = ?", (form_id,))
        row = cur.fetchone()
        if not row:
            flash("Form not found.", "error")
            return redirect(url_for("index"))
        form = dict(row)
        cur.execute(
            """SELECT id, question_text, question_type, options, is_required, sort_order
               FROM questions WHERE form_id = ? ORDER BY sort_order""",
            (form_id,),
        )
        questions = [dict(r) for r in cur.fetchall()]

    if request.method == "GET":
        return render_template("form_submit.html", form=form, questions=questions)

    # POST: validate and save response + answers
    is_anonymous = request.form.get("is_anonymous") == "on"
    respondent_name = request.form.get("respondent_name", "").strip() if not is_anonymous else None
    respondent_email = request.form.get("respondent_email", "").strip() if not is_anonymous else None

    errors = []
    answers_to_save = []  # list of (question_id, answer_text, rating_value)

    for q in questions:
        qid = q["id"]
        qtype = q["question_type"]
        required = q["is_required"]
        key = f"q_{qid}"

        if qtype == "rating":
            raw = request.form.get(key)
            val = None
            if raw is not None and raw.isdigit():
                v = int(raw)
                if 1 <= v <= 5:
                    val = v
            if required and val is None:
                errors.append(f"Question '{q['question_text'][:50]}...' must be answered (rating 1-5).")
            else:
                answers_to_save.append((qid, None, val))
        else:
            # text or multiple choice
            text_val = request.form.get(key, "").strip()
            if required and not text_val:
                errors.append(f"Question '{q['question_text'][:50]}...' is required.")
            else:
                answers_to_save.append((qid, text_val, None))

    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("form_submit.html", form=form, questions=questions)

    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO responses (form_id, is_anonymous, respondent_name, respondent_email)
               VALUES (?, ?, ?, ?)""",
            (form_id, 1 if is_anonymous else 0, respondent_name, respondent_email),
        )
        response_id = cur.lastrowid
        for qid, answer_text, rating_value in answers_to_save:
            cur.execute(
                """INSERT INTO answers (response_id, question_id, answer_text, rating_value)
                   VALUES (?, ?, ?, ?)""",
                (response_id, qid, answer_text, rating_value),
            )

    flash("Thank you! Your feedback has been submitted.", "success")
    return redirect(url_for("form_submit_page", form_id=form_id))


# -----------------------------------------------------------------------------
# Route: Summary for a form
# -----------------------------------------------------------------------------

@app.route("/form/<int:form_id>/summary")
def form_summary(form_id):
    """Show summary: total responses, counts per option, average rating, text list."""
    with db_cursor() as cur:
        cur.execute("SELECT id, title, description FROM forms WHERE id = ?", (form_id,))
        row = cur.fetchone()
        if not row:
            flash("Form not found.", "error")
            return redirect(url_for("index"))
        form = dict(row)

        cur.execute("SELECT COUNT(*) AS total FROM responses WHERE form_id = ?", (form_id,))
        total_responses = cur.fetchone()["total"]

        cur.execute(
            """SELECT id, question_text, question_type, options, is_required, sort_order
               FROM questions WHERE form_id = ? ORDER BY sort_order""",
            (form_id,),
        )
        questions = [dict(r) for r in cur.fetchall()]

    # For each question, compute summary data (use one connection for all queries)
    summaries = []
    conn = get_db()
    try:
        cur = conn.cursor()
        for q in questions:
            qid = q["id"]
            qtype = q["question_type"]
            summary = {
                "question": q,
                "count": 0,
                "choice_counts": {},
                "avg_rating": None,
                "text_responses": [],
            }
            if qtype == "rating":
                cur.execute(
                    "SELECT rating_value FROM answers WHERE question_id = ? AND rating_value IS NOT NULL",
                    (qid,),
                )
                ratings = [r["rating_value"] for r in cur.fetchall()]
                summary["count"] = len(ratings)
                if ratings:
                    summary["avg_rating"] = round(sum(ratings) / len(ratings), 2)
            elif qtype == "multiple_choice":
                cur.execute(
                    "SELECT answer_text FROM answers WHERE question_id = ? AND answer_text IS NOT NULL AND answer_text != ''",
                    (qid,),
                )
                options_answered = [r["answer_text"] for r in cur.fetchall()]
                summary["count"] = len(options_answered)
                for opt in options_answered:
                    summary["choice_counts"][opt] = summary["choice_counts"].get(opt, 0) + 1
            else:
                # short_text / long_text
                cur.execute(
                    "SELECT answer_text FROM answers WHERE question_id = ? AND answer_text IS NOT NULL AND answer_text != ''",
                    (qid,),
                )
                texts = [r["answer_text"] for r in cur.fetchall()]
                summary["count"] = len(texts)
                summary["text_responses"] = texts
            summaries.append(summary)
    finally:
        conn.close()

    return render_template(
        "form_summary.html",
        form=form,
        total_responses=total_responses,
        summaries=summaries,
    )


# -----------------------------------------------------------------------------
# Run app and init DB on first run
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    get_instance_path()
    init_db()
    app.run(debug=True, port=5000)
