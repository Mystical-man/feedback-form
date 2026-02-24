# Feedback Collection for Events or Courses

A simple college-level web application to create feedback forms and collect responses. Built with Flask, SQLite, and plain HTML/CSS.

## Tech Stack

- **Backend:** Python + Flask
- **Database:** SQLite
- **Frontend:** HTML + CSS (Bootstrap via CDN)

## Project Structure

```
feedback-app/
├── app.py              # Main Flask application (routes + DB logic)
├── requirements.txt    # Python dependencies
├── README.md           # This file
├── instance/           # Created at runtime (SQLite DB stored here)
│   └── feedback.db
├── static/
│   └── style.css       # Minimal custom CSS
└── templates/
    ├── base.html       # Base layout
    ├── index.html      # Home / list forms
    ├── create_form.html    # Create new form + questions
    ├── form_submit.html    # Submit feedback (public URL)
    └── form_summary.html   # View response summary
```

## Setup Instructions

### 1. Install Dependencies

```bash
cd feedback-app
pip install -r requirements.txt
```

### 2. Initialize the Database

The database is created automatically when you run the app for the first time. No separate init script is needed.

### 3. Run the Application

```bash
python app.py
```

Then open your browser and go to: **http://127.0.0.1:5000**

## How to Use

1. **Create a form:** From the home page, click "Create New Form". Enter title and description, then add questions (Short Text, Long Text, Multiple Choice, or Rating 1–5). For multiple choice, enter options separated by commas.
2. **Share the form:** After creating, you get a link to share (e.g. `/form/1/submit`). Anyone with the link can submit feedback.
3. **Submit feedback:** Open the form link, fill answers, choose anonymous or enter name/email, then submit.
4. **View summary:** From the home page, open "View Summary" for a form to see total responses, choice counts, average ratings, and text responses.

## Database Schema

- **forms** – form title, description
- **questions** – linked to form; type (short_text, long_text, multiple_choice, rating), options (for multiple choice), required flag
- **responses** – one per submission; form_id, anonymous/name/email, timestamp
- **answers** – one per question per response; stores text or rating value

No login or password; sessions used only where needed for simple flow.
