# AI Resume Analyzer

A local Flask web application with individual user accounts, PDF/DOCX resume uploads, job-description matching, an explainable match score, and an SQLite database.

## Requirements
- Python 3.10 or newer (Python 3.11 or 3.12 recommended)
- Internet connection for installing dependencies and loading Bootstrap from its CDN
- VS Code or another editor

## Setup (Windows PowerShell)
1. Extract the ZIP file and open the `ai_resume_analyzer` folder in VS Code.
2. Open the VS Code terminal.
3. Create a virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation, use Command Prompt and run:
   ```bat
   .venv\Scripts\activate.bat
   ```
4. Install dependencies:
   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
5. Set a secret key in PowerShell for this terminal session:
   ```powershell
   $env:SECRET_KEY = "replace-with-a-long-random-secret"
   ```
   You can generate a random value with:
   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Copy the generated value into the `SECRET_KEY` environment variable. For local learning, the app has a development fallback if you skip this, but do not use that fallback for deployment.
6. Start the application:
   ```powershell
   python app.py
   ```
7. Open http://127.0.0.1:5000 in your browser and register an account.

## Features
- Registration, login, logout, and hashed passwords
- User-scoped resume and analysis records
- PDF and DOCX text extraction
- Skill overlap and TF-IDF/cosine similarity
- Explainable weighted score and practical suggestions
- Analysis history stored in SQLite

## Score calculation
The score is an explanatory heuristic, not a real ATS score:
- 70% job-skill coverage: number of detected job-description skills also detected in the resume divided by the number of detected job skills.
- 30% TF-IDF cosine similarity between resume text and job description.
- If the job description contains no skills from the built-in vocabulary, the score uses text similarity only.
Scores should be interpreted as a comparison aid, not a hiring prediction.

## Privacy and limitations
- Uploaded files and the SQLite database are stored locally in the `instance/` directory.
- Each signed-in user can only view their own records through the application.
- This starter project does not include email verification, password reset, rate limiting, cloud backup, or production deployment hardening.
- Scanned/image-only PDFs may not contain extractable text. OCR is not included.
- The built-in skill vocabulary is intentionally editable in `analyzer.py`; extend it for the job types you want to support.
- Bootstrap is loaded from a CDN, so the initial page styling requires an internet connection.

## Troubleshooting
- If a dependency fails to install, check that your Python version is 3.10+ and retry in the activated virtual environment.
- If upload says it could not extract text, try a text-based PDF or DOCX file.
- The app creates its database and upload folder on first run.
- To reset local demo data, stop the app and delete the `instance/` folder. This permanently deletes local accounts, analyses, and uploaded resumes.
