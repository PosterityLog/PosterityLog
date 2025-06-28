import os
import uuid
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, g, render_template, redirect
from werkzeug.utils import secure_filename
import boto3
from botocore.exceptions import NoCredentialsError
from dotenv import load_dotenv

# ─── Load Config ───────────────────────────────────────────────────────────────
load_dotenv()
app = Flask(__name__)
DB_PATH = 'posteritylog.db'
S3_BUCKET = "posteritylog-screenshots"

os.makedirs('tmp', exist_ok=True)

# ─── AWS S3 Uploader ───────────────────────────────────────────────────────────
def upload_to_s3(local_path, s3_filename):
    s3 = boto3.client('s3',
                      aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                      aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"))
    try:
        s3.upload_file(local_path, S3_BUCKET, s3_filename)
        return f"https://{S3_BUCKET}.s3.amazonaws.com/{s3_filename}"
    except FileNotFoundError:
        raise Exception("Local file not found")
    except NoCredentialsError:
        raise Exception("AWS credentials missing")

# ─── Database Connection ───────────────────────────────────────────────────────
def get_db():
    db = getattr(g, '_db', None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.execute('''
            CREATE TABLE IF NOT EXISTS submissions (
              id TEXT PRIMARY KEY,
              report_type TEXT,
              subtype TEXT,
              narrative TEXT,
              name TEXT,
              email TEXT,
              consent_contact INTEGER,
              consent_public INTEGER,
              file_urls TEXT,
              submitted_at TEXT
            )
        ''')
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, '_db', None)
    if db is not None:
        db.close()

# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route('/report')
def form():
    return render_template("report.html")

@app.route('/submit', methods=['POST'])
def submit():
    uid = str(uuid.uuid4())
    db = get_db()

    # Core fields
    report_type     = request.form.get('report_type', '')
    subtype         = request.form.get('subtype', '')
    narrative       = request.form.get('narrative', '')
    name            = request.form.get('name', '')
    email           = request.form.get('email', '')
    consent_contact = 1 if request.form.get('consent_contact') == 'on' else 0
    consent_public  = 1 if request.form.get('consent_public') == 'on' else 0

    # Handle multiple file uploads
    file_urls = []
    files = request.files.getlist('evidence')
    for file in files:
        if file and file.filename:
            safe_name = secure_filename(file.filename)
            temp_path = os.path.join('tmp', f"{uid}_{safe_name}")
            file.save(temp_path)
            try:
                url = upload_to_s3(temp_path, f"{uid}/{safe_name}")
                file_urls.append(url)
            finally:
                os.remove(temp_path)

    db.execute('''
        INSERT INTO submissions (
          id, report_type, subtype, narrative,
          name, email, consent_contact, consent_public,
          file_urls, submitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        uid, report_type, subtype, narrative,
        name, email, consent_contact, consent_public,
        json.dumps(file_urls), datetime.utcnow().isoformat()
    ))

    db.commit()
    return f"✅ Thank you for your submission. Your report ID is {uid}."

# ─── Launch ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(
        debug=True,
        port=5000,
        host='0.0.0.0'
    )
from flask import jsonify
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route('/redact', methods=['POST'])
def redact():
    data = request.get_json()
    user_text = data.get("text", "")

    prompt = (
        "You are a redaction assistant for a civic archive.\n"
        "Your job is to scan user-submitted text for personally identifying information "
        "such as names, locations, GPS coordinates, emails, and job titles, and redact them. "
        "Use the placeholder format [Redaction 1], [Redaction 2], etc. "
        "Keep the rest of the report intact. Do not add commentary.\n\n"
        f"Text to redact:\n{user_text}\n\nRedacted version:"
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",  # or "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "You redact sensitive information for archival reports."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        redacted_text = response.choices[0].message['content'].strip()
        return jsonify({"redacted": redacted_text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
