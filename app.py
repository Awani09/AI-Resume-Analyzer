import json
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Flask, abort, flash, redirect, render_template, request, url_for
)
from flask_login import (
    LoginManager, UserMixin, current_user, login_required, login_user, logout_user
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from analyzer import analyze_resume, extract_text

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = INSTANCE_DIR / "uploads"
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB

INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, instance_path=str(INSTANCE_DIR))
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or "dev-only-change-this-secret-key",
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{(INSTANCE_DIR / 'resume_analyzer.db').as_posix()}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=MAX_FILE_BYTES,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to continue."
csrf = CSRFProtect(app)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    resumes = db.relationship("Resume", backref="owner", cascade="all, delete-orphan")
    analyses = db.relationship("Analysis", backref="owner", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Resume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    extracted_text = db.Column(db.Text, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    analyses = db.relationship("Analysis", backref="resume", cascade="all, delete-orphan")


class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resume.id"), nullable=False)
    job_title = db.Column(db.String(160), nullable=False)
    job_description = db.Column(db.Text, nullable=False)
    match_score = db.Column(db.Integer, nullable=False)
    similarity_percent = db.Column(db.Integer, nullable=False)
    skill_coverage_percent = db.Column(db.Integer, nullable=True)
    matched_skills_json = db.Column(db.Text, nullable=False, default="[]")
    missing_skills_json = db.Column(db.Text, nullable=False, default="[]")
    suggestions_json = db.Column(db.Text, nullable=False, default="[]")
    score_method = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    @property
    def matched_skills(self):
        return json.loads(self.matched_skills_json)

    @property
    def missing_skills(self):
        return json.loads(self.missing_skills_json)

    @property
    def suggestions(self):
        return json.loads(self.suggestions_json)


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


@app.context_processor
def inject_helpers():
    return {"csrf_token": __import__("flask_wtf.csrf", fromlist=["generate_csrf"]).generate_csrf}


@app.errorhandler(413)
def file_too_large(_error):
    flash("That upload is too large. The maximum file size is 10 MB.", "danger")
    return redirect(url_for("upload_resume"))


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username):
            flash("Username must be 3–40 characters and use letters, numbers, dot, underscore, or hyphen.", "danger")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
            flash("Enter a valid email address.", "danger")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
        elif password != confirm_password:
            flash("Passwords do not match.", "danger")
        elif User.query.filter((User.username.ilike(username)) | (User.email == email)).first():
            flash("That username or email is already registered.", "danger")
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created. Welcome to your dashboard!", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter(
            (User.username.ilike(identifier)) | (User.email == identifier.lower())
        ).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Welcome back!", "success")
            next_url = request.args.get("next", "")
            # Only allow local relative redirects to avoid open redirects.
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("dashboard"))
        flash("Invalid username/email or password.", "danger")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    resumes = Resume.query.filter_by(user_id=current_user.id).order_by(Resume.uploaded_at.desc()).all()
    analyses = Analysis.query.filter_by(user_id=current_user.id).order_by(Analysis.created_at.desc()).limit(8).all()
    return render_template("dashboard.html", resumes=resumes, analyses=analyses)


@app.route("/resumes/upload", methods=["GET", "POST"])
@login_required
def upload_resume():
    if request.method == "POST":
        uploaded = request.files.get("resume")
        if not uploaded or not uploaded.filename:
            flash("Choose a PDF or DOCX file first.", "danger")
            return redirect(url_for("upload_resume"))

        original_name = secure_filename(uploaded.filename)
        extension = Path(original_name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            flash("Only PDF and DOCX files are supported.", "danger")
            return redirect(url_for("upload_resume"))

        # Save to a user-specific folder with a random name, never the submitted path.
        user_folder = UPLOAD_DIR / str(current_user.id)
        user_folder.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}{extension}"
        absolute_path = user_folder / stored_name
        uploaded.save(absolute_path)

        try:
            extracted = extract_text(str(absolute_path), extension)
        except (ValueError, RuntimeError, OSError) as exc:
            absolute_path.unlink(missing_ok=True)
            flash(str(exc) if isinstance(exc, ValueError) else "Could not read that file. Try another PDF or DOCX.", "danger")
            return redirect(url_for("upload_resume"))

        relative_name = f"{current_user.id}/{stored_name}"
        resume = Resume(
            user_id=current_user.id,
            original_name=original_name[:255],
            stored_name=relative_name,
            extracted_text=extracted,
        )
        db.session.add(resume)
        db.session.commit()
        flash("Resume uploaded and text extracted successfully.", "success")
        return redirect(url_for("dashboard"))
    return render_template("upload_resume.html")


@app.route("/analyze", methods=["GET", "POST"])
@login_required
def analyze():
    resumes = Resume.query.filter_by(user_id=current_user.id).order_by(Resume.uploaded_at.desc()).all()
    if not resumes:
        flash("Upload a resume before starting an analysis.", "warning")
        return redirect(url_for("upload_resume"))

    if request.method == "POST":
        resume_id = request.form.get("resume_id", type=int)
        job_title = request.form.get("job_title", "").strip()
        job_description = request.form.get("job_description", "").strip()
        resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first()

        if not resume:
            flash("Choose one of your own uploaded resumes.", "danger")
        elif not job_title or len(job_title) > 160:
            flash("Enter a job title (up to 160 characters).", "danger")
        elif len(job_description) < 40:
            flash("Paste a fuller job description (at least 40 characters).", "danger")
        elif len(job_description) > 30000:
            flash("Job description is too long (maximum 30,000 characters).", "danger")
        else:
            result = analyze_resume(resume.extracted_text, job_description)
            analysis = Analysis(
                user_id=current_user.id,
                resume_id=resume.id,
                job_title=job_title,
                job_description=job_description,
                match_score=result["score"],
                similarity_percent=result["similarity_percent"],
                skill_coverage_percent=result["skill_coverage_percent"],
                matched_skills_json=json.dumps(result["matched_skills"]),
                missing_skills_json=json.dumps(result["missing_skills"]),
                suggestions_json=json.dumps(result["suggestions"]),
                score_method=result["score_method"],
            )
            db.session.add(analysis)
            db.session.commit()
            return redirect(url_for("analysis_detail", analysis_id=analysis.id))
    return render_template("analyze.html", resumes=resumes)


@app.route("/analysis/<int:analysis_id>")
@login_required
def analysis_detail(analysis_id):
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=current_user.id).first_or_404()
    return render_template("analysis_detail.html", analysis=analysis)


@app.route("/analysis/<int:analysis_id>/delete", methods=["POST"])
@login_required
def delete_analysis(analysis_id):
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=current_user.id).first_or_404()
    db.session.delete(analysis)
    db.session.commit()
    flash("Analysis deleted.", "success")
    return redirect(url_for("dashboard"))


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    # Local development only. Do not expose Flask's debug server to the internet.
    app.run(host="127.0.0.1", port=5000, debug=True)
