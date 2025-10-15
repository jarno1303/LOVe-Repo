# ============================================================================
# YMPÄRISTÖMUUTTUJIEN LATAUS - TÄYTYY OLLA ENSIMMÄISENÄ!
# ============================================================================
from dotenv import load_dotenv
load_dotenv()

# ============================================================================
# STANDARDIKIRJASTO-IMPORTIT
# ============================================================================
import os
import sqlite3
import random
import json
import re
import smtplib
import logging
import string
from dataclasses import asdict
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO
from logging.handlers import RotatingFileHandler
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ============================================================================
# THIRD-PARTY KIRJASTOT
# ============================================================================
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, make_response
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

# ReportLab (PDF-generointi)
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas

# python-docx (Word-dokumentit)
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

# ============================================================================
# OMAT MODUULIT
# ============================================================================
from data_access.database_manager import DatabaseManager
from logic.stats_manager import EnhancedStatsManager
from logic.achievement_manager import EnhancedAchievementManager, ENHANCED_ACHIEVEMENTS
from logic.spaced_repetition import SpacedRepetitionManager
from models.models import User
from constants import DISTRACTORS

# ============================================================================
# FLASK-SOVELLUKSEN ALUSTUS
# ============================================================================
app = Flask(__name__)

# Hae SECRET_KEY ympäristömuuttujasta (PAKOLLINEN tuotannossa!)
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    import sys
    if 'pytest' not in sys.modules:
        print("⚠️  VAROITUS: SECRET_KEY ympäristömuuttuja puuttuu!")
        print("⚠️  Käytetään oletusavainta - ÄLÄ käytä tuotannossa!")
    SECRET_KEY = 'kehityksenaikainen-oletusavain-VAIHDA-TÄMÄ'

app.config['SECRET_KEY'] = SECRET_KEY

# DEBUG-tila: päällä vain jos FLASK_ENV=development
DEBUG_MODE = os.environ.get('FLASK_ENV') == 'development'
app.config['DEBUG'] = DEBUG_MODE

# ProxyFix: Korjaa X-Forwarded-* headerit (Railway, Heroku, ym.)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# CSRF-suojaus
csrf = CSRFProtect(app)

# ============================================================================
# LOKITUS
# ============================================================================
if not os.path.exists('logs'):
    os.mkdir('logs')

file_handler = RotatingFileHandler('logs/love_enhanced.log', maxBytes=10240000, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)

app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('LOVe Enhanced startup')

# ============================================================================
# RATE LIMITING
# ============================================================================
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri=REDIS_URL if os.environ.get('FLASK_ENV') != 'development' else "memory://"
)

# ============================================================================
# TIETOKANTA JA MANAGERIT
# ============================================================================
db_manager = DatabaseManager()
stats_manager = EnhancedStatsManager(db_manager)
achievement_manager = EnhancedAchievementManager(db_manager)
spaced_repetition_manager = SpacedRepetitionManager(db_manager)
bcrypt = Bcrypt(app)

# ============================================================================
# APUFUNKTIOT JA DEKORAATTORIT
# ============================================================================

def json_response(data, status=200):
    """Helper function to serialize data to JSON with datetime conversion."""
    def convert_datetimes_to_isoformat(data):
        if isinstance(data, list):
            return [convert_datetimes_to_isoformat(item) for item in data]
        if isinstance(data, dict):
            return {key: convert_datetimes_to_isoformat(value) for key, value in data.items()}
        if isinstance(data, datetime):
            return data.isoformat()
        return data
    safe_data = convert_datetimes_to_isoformat(data)
    return jsonify(safe_data), status

def api_csrf_protect(f):
    """Decorator to enforce CSRF protection for API POST routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.is_json:
            token = request.headers.get('X-CSRF-Token') or request.get_json().get('csrf_token')
            if not token or not csrf._verify_csrf_token(token):
                return json_response({'error': 'Invalid or missing CSRF token'}, 403)
        return f(*args, **kwargs)
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    try:
        user_data = db_manager._execute(
            "SELECT id, username, email, role, distractors_enabled, distractor_probability, expires_at FROM users WHERE id = ?",
            (user_id,),
            fetch='one'
        )
        if user_data:
            return User(
                id=user_data['id'],
                username=user_data['username'],
                email=user_data['email'],
                role=user_data['role'],
                distractors_enabled=bool(user_data.get('distractors_enabled', False)),
                distractor_probability=user_data.get('distractor_probability', 25),
                expires_at=user_data.get('expires_at')
            )
    except Exception as e:
        app.logger.error(f"Error loading user {user_id}: {e}")
    return None

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash("Pääsy kielletty. Vaatii ylläpitäjän oikeudet.", "danger")
            return redirect(url_for('dashboard_route'))
        return f(*args, **kwargs)
    return decorated_function

def generate_secure_password(length=10):
    if length < 8:
        length = 8
    pienet = string.ascii_lowercase
    isot = string.ascii_uppercase
    numerot = string.digits
    salasana = [random.choice(pienet), random.choice(isot), random.choice(numerot)]
    kaikki_merkit = pienet + isot + numerot
    for _ in range(length - len(salasana)):
        salasana.append(random.choice(kaikki_merkit))
    random.shuffle(salasana)
    return "".join(salasana)

def generate_reset_token(email):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='password-reset-salt')

def verify_reset_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=expiration)
        return email
    except (SignatureExpired, BadSignature):
        return None

def send_reset_email(user_email, reset_url):
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY')
    FROM_EMAIL = os.environ.get('FROM_EMAIL', 'noreply@example.com')
    if not BREVO_API_KEY:
        app.logger.warning(f"Brevo not configured. Reset link: {reset_url}")
        print(f"\n{'='*80}\nSALASANAN PALAUTUSLINKKI:\n{reset_url}\n{'='*80}\n")
        return True
    
    import requests
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"accept": "application/json", "api-key": BREVO_API_KEY, "content-type": "application/json"}
    payload = {
        "sender": {"name": "LOVe Enhanced", "email": FROM_EMAIL},
        "to": [{"email": user_email, "name": user_email.split('@')[0]}],
        "subject": "LOVe Enhanced - Salasanan palautus",
        "htmlContent": f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f7fafc; border-radius: 10px;">
              <h2 style="color: #5A67D8; text-align: center;">LOVe Enhanced</h2>
              <h3>Salasanan palautuspyyntö</h3>
              <p>Hei,</p>
              <p>Saimme pyynnön palauttaa tilisi salasana.</p>
              <p>Klikkaa alla olevaa painiketta palauttaaksesi salasanasi:</p>
              <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_url}" style="background-color: #5A67D8; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                  Palauta salasana
                </a>
              </div>
              <p>Tai kopioi ja liitä tämä linkki selaimeesi:</p>
              <p style="background-color: #e2e8f0; padding: 10px; border-radius: 5px; word-break: break-all;">
                {reset_url}
              </p>
              <p><strong>Tämä linkki on voimassa 1 tunnin.</strong></p>
              <p>Jos et pyytänyt salasanan palautusta, voit jättää tämän viestin huomiotta.</p>
              <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
              <p style="font-size: 12px; color: #718096; text-align: center;">
                LOVe Enhanced - Lääkehoidon osaamisen vahvistaminen
              </p>
            </div>
          </body>
        </html>
        """
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        app.logger.info(f"Password reset email sent to {user_email}")
        return True
    except Exception as e:
        app.logger.error(f"Failed to send email via Brevo: {e}")
        return False

# ============================================================================
# TIETOKANNAN ALUSTUSTOIMINNOT
# ============================================================================

def init_distractor_table():
    try:
        conn = db_manager.get_connection()
        with conn:
            cursor = conn.cursor()
            if db_manager.is_postgres:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS distractor_attempts (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        distractor_scenario TEXT NOT NULL,
                        user_choice INTEGER NOT NULL,
                        correct_choice INTEGER NOT NULL,
                        is_correct BOOLEAN NOT NULL,
                        response_time INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                ''')
            else:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS distractor_attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        distractor_scenario TEXT NOT NULL,
                        user_choice INTEGER NOT NULL,
                        correct_choice INTEGER NOT NULL,
                        is_correct BOOLEAN NOT NULL,
                        response_time INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                ''')
            conn.commit()
    except Exception as e:
        app.logger.error(f"Error creating distractor table: {e}")

init_distractor_table()

# ============================================================================
# FLASK-LOGIN SETUP
# ============================================================================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_route'
login_manager.login_message = "Kirjaudu sisään nähdäksesi tämän sivun."
login_manager.login_message_category = "info"

# ============================================================================
# API-REITIT
# ============================================================================

@app.route("/api/csrf-token", methods=['GET'])
def get_csrf_token():
    return json_response({'csrf_token': generate_csrf()})

@app.route("/api/incorrect_questions")
@login_required
@limiter.limit("60 per minute")
def get_incorrect_questions_api():
    try:
        incorrect_questions = db_manager._execute("""
            SELECT 
                q.id,
                q.question,
                q.category,
                q.difficulty,
                q.explanation,
                p.times_shown,
                p.times_correct,
                p.last_shown,
                ROUND((p.times_correct * 100.0) / NULLIF(p.times_shown, 0), 1) as success_rate
            FROM questions q
            INNER JOIN user_question_progress p ON q.id = p.question_id
            WHERE p.user_id = ?
                AND p.times_correct < p.times_shown
            ORDER BY success_rate ASC NULLS FIRST, p.times_shown DESC
        """, (current_user.id,), fetch='all')
        return json_response({'questions': [dict(q) for q in incorrect_questions] if incorrect_questions else []})
    except Exception as e:
        app.logger.error(f"Error fetching incorrect questions: {e}")
        return json_response({'error': str(e)}, 500)

@app.route("/api/question_progress/<int:question_id>")
@login_required
@limiter.limit("60 per minute")
def get_question_progress_api(question_id):
    try:
        progress = db_manager._execute("""
            SELECT 
                times_shown,
                times_correct,
                last_shown,
                CASE 
                    WHEN times_shown > 0 THEN ROUND((times_correct * 100.0) / times_shown, 1)
                    ELSE 0 
                END as success_rate
            FROM user_question_progress
            WHERE user_id = ? AND question_id = ?
        """, (current_user.id, question_id), fetch='one')
        if progress:
            return json_response(dict(progress))
        return json_response({
            'times_shown': 0,
            'times_correct': 0,
            'success_rate': 0,
            'last_shown': None
        })
    except Exception as e:
        app.logger.error(f"Error fetching question progress: {e}")
        return json_response({'error': str(e)}, 500)

@app.route("/api/settings/toggle_distractors", methods=['POST'])
@login_required
@limiter.limit("30 per minute")
@api_csrf_protect
def toggle_distractors_api():
    data = request.get_json()
    is_enabled = data.get('enabled', False)
    try:
        db_manager._execute("UPDATE users SET distractors_enabled = ? WHERE id = ?", (is_enabled, current_user.id), fetch='none')
        app.logger.info(f"User {current_user.username} toggled distractors: {is_enabled}")
        return json_response({'success': True, 'distractors_enabled': is_enabled})
    except Exception as e:
        app.logger.error(f"Error toggling distractors: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route("/api/settings/update_distractor_probability", methods=['POST'])
@login_required
@limiter.limit("30 per minute")
@api_csrf_protect
def update_distractor_probability_api():
    data = request.get_json()
    probability = data.get('probability', 25)
    probability = max(0, min(100, int(probability)))
    try:
        db_manager._execute("UPDATE users SET distractor_probability = ? WHERE id = ?", (probability, current_user.id), fetch='none')
        app.logger.info(f"User {current_user.username} updated distractor probability: {probability}%")
        return json_response({'success': True, 'probability': probability})
    except Exception as e:
        app.logger.error(f"Error updating distractor probability: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route("/api/question_counts")
@login_required
@limiter.limit("60 per minute")
def get_question_counts_api():
    try:
        category_counts = db_manager._execute("""
            SELECT category, COUNT(*) as count
            FROM questions
            GROUP BY category
            ORDER BY category
        """, fetch='all')
        difficulty_counts = db_manager._execute("""
            SELECT difficulty, COUNT(*) as count
            FROM questions
            GROUP BY difficulty
        """, fetch='all')
        category_difficulty_counts = db_manager._execute("""
            SELECT category, difficulty, COUNT(*) as count
            FROM questions
            GROUP BY category, difficulty
        """, fetch='all')
        total_result = db_manager._execute("SELECT COUNT(*) as count FROM questions", fetch='one')
        total_count = total_result['count'] if total_result else 0
        cat_diff_map = {}
        if category_difficulty_counts:
            for row in category_difficulty_counts:
                cat = row['category']
                diff = row['difficulty']
                count = row['count']
                if cat not in cat_diff_map:
                    cat_diff_map[cat] = {}
                cat_diff_map[cat][diff] = count
        return json_response({
            'categories': {row['category']: row['count'] for row in category_counts} if category_counts else {},
            'difficulties': {row['difficulty']: row['count'] for row in difficulty_counts} if difficulty_counts else {},
            'category_difficulty_map': cat_diff_map,
            'total': total_count
        })
    except Exception as e:
        app.logger.error(f"Error fetching question counts: {e}")
        return json_response({'error': str(e)}, 500)

@app.route("/api/distractors")
@login_required
def get_distractors_api():
    return json_response(DISTRACTORS)

@app.route("/api/submit_distractor", methods=['POST'])
@login_required
@limiter.limit("100 per minute")
@api_csrf_protect
def submit_distractor_api():
    try:
        data = request.get_json()
        if not data:
            return json_response({'error': 'No data provided'}, 400)
        scenario = data.get('scenario')
        user_choice = data.get('user_choice')
        response_time = data.get('response_time', 0)
        
        if scenario is None or user_choice is None:
            return json_response({'error': 'scenario and user_choice are required'}, 400)
        
        correct_choice = next((d['correct'] for d in DISTRACTORS if d['scenario'] == scenario), 0)
        is_correct = user_choice == correct_choice
        
        try:
            db_manager._execute("""
                INSERT INTO distractor_attempts
                (user_id, distractor_scenario, user_choice, correct_choice, is_correct, response_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (current_user.id, scenario, user_choice, correct_choice, is_correct, response_time, datetime.now()), fetch='none')
            app.logger.info(f"User {current_user.username} submitted distractor: correct={is_correct}")
            return json_response({
                'success': True,
                'is_correct': is_correct,
                'correct_choice': correct_choice
            })
        except Exception as e:
            app.logger.error(f"Error submitting distractor: {e}")
            return json_response({'success': False, 'error': str(e)}, 500)
    except Exception as e:
        app.logger.error(f"Error in submit_distractor_api: {e}")
        return json_response({'error': str(e)}, 500)

@app.route("/api/user_preferences", methods=['POST'])
@login_required
@api_csrf_protect
def save_user_preferences():
    data = request.get_json()
    categories = data.get('categories', [])
    difficulties = data.get('difficulties', [])
    success, error = db_manager.update_user_practice_preferences(current_user.id, categories, difficulties)
    if success:
        return json_response({'status': 'success', 'message': 'Asetukset tallennettu.'})
    return json_response({'status': 'error', 'message': error}, 500)

@app.route("/api/submit_answer", methods=['POST'])
@login_required
@limiter.limit("100 per minute")
@api_csrf_protect
def submit_answer_api():
    data = request.get_json()
    question_id = data.get('question_id')
    selected_option_text = data.get('selected_option_text')
    time_taken = data.get('time_taken', 0)
    
    question = db_manager.get_question_by_id(question_id, current_user.id)
    if not question:
        app.logger.warning(f"Question {question_id} not found for user {current_user.username}")
        return json_response({'error': 'Question not found'}, 404)
    
    is_correct = (selected_option_text == question.options[question.correct])
    db_manager.update_question_stats(question_id, is_correct, time_taken, current_user.id)
    
    try:
        quality = 5 if is_correct else 2
        new_interval, new_ease_factor = spaced_repetition_manager.calculate_next_review(
            question=question, 
            performance_rating=quality
        )
        spaced_repetition_manager.record_review(
            user_id=current_user.id,
            question_id=question_id,
            interval=new_interval,
            ease_factor=new_ease_factor
        )
        app.logger.info(f"Spaced repetition updated: user={current_user.id}, q={question_id}, quality={quality}, new_interval={new_interval}")
    except Exception as e:
        app.logger.error(f"Error updating spaced repetition: {e}")
    
    new_achievement_ids = achievement_manager.check_achievements(current_user.id)
    new_achievements = []
    for ach_id in new_achievement_ids:
        try:
            if ach_id in ENHANCED_ACHIEVEMENTS:
                ach_obj = ENHANCED_ACHIEVEMENTS[ach_id]
                ach_data = asdict(ach_obj) if hasattr(ach_obj, '__dataclass_fields__') else {
                    'id': getattr(ach_obj, 'id', ach_id),
                    'name': getattr(ach_obj, 'name', ''),
                    'description': getattr(ach_obj, 'description', ''),
                    'icon': getattr(ach_obj, 'icon', ''),
                    'unlocked': True,
                    'unlocked_at': getattr(ach_obj, 'unlocked_at', None)
                }
                new_achievements.append(ach_data)
        except Exception as e:
            app.logger.error(f"Error processing achievement {ach_id}: {e}")
            continue
    
    if new_achievements:
        app.logger.info(f"User {current_user.username} unlocked {len(new_achievements)} achievements")
    
    return json_response({
        'correct': is_correct,
        'correct_answer_index': question.correct,
        'explanation': question.explanation,
        'new_achievements': new_achievements
    })

@app.route("/api/submit_simulation", methods=['POST'])
@login_required
@limiter.limit("20 per minute")
@api_csrf_protect
def submit_simulation_api():
    data = request.get_json()
    answers = data.get('answers')
    questions_ids = data.get('questions')
    
    if not answers or not questions_ids or len(answers) != len(questions_ids):
        return json_response({'error': 'Invalid data provided'}, 400)
    
    correct_answers_count = 0
    detailed_results = []
    for i, q_id in enumerate(questions_ids):
        question_obj = db_manager.get_question_by_id(q_id, current_user.id)
        if question_obj and answers[i] is not None and answers[i] == question_obj.correct:
            correct_answers_count += 1
        detailed_results.append({
            'question': question_obj.question if question_obj else "Unknown",
            'options': question_obj.options if question_obj else [],
            'explanation': question_obj.explanation if question_obj else "",
            'user_answer': answers[i],
            'correct_answer': question_obj.correct if question_obj else None,
            'is_correct': (answers[i] == question_obj.correct) if question_obj else False
        })
    
    percentage = (correct_answers_count / len(questions_ids)) * 100 if questions_ids else 0
    app.logger.info(f"User {current_user.username} completed simulation: {correct_answers_count}/{len(questions_ids)} ({percentage:.1f}%)")
    
    return json_response({
        'score': correct_answers_count,
        'total': len(questions_ids),
        'percentage': percentage,
        'detailed_results': detailed_results
    })

@app.route("/api/questions")
@login_required
@limiter.limit("60 per minute")
def get_questions_api():
    try:
        categories = request.args.getlist('categories')
        difficulties = request.args.getlist('difficulties')
        limit = int(request.args.get('count', 10))
        simulation = request.args.get('simulation') == 'true'
        app.logger.info(f"API call: user={current_user.id}, simulation={simulation}, categories={categories}, difficulties={difficulties}, limit={limit}")
        categories = None if not categories else categories
        difficulties = None if not difficulties else difficulties
        questions = db_manager.get_questions(
            user_id=current_user.id,
            categories=categories,
            difficulties=difficulties,
            limit=50 if simulation else limit
        )
        questions_list = []
        for q in questions:
            if q.options and 0 <= q.correct < len(q.options):
                original_correct_text = q.options[q.correct]
                random.shuffle(q.options)
                q.correct = q.options.index(original_correct_text)
            questions_list.append(asdict(q))
        if not questions_list:
            return json_response({'questions': [], 'message': 'Ei kysymyksiä valituilla kriteereillä.'})
        return json_response({'questions': questions_list})
    except ValueError as ve:
        app.logger.error(f"Invalid parameter: {ve}")
        return json_response({'error': 'Virheellinen parametri.', 'details': str(ve)}, 400)
    except Exception as e:
        app.logger.error(f"Error in /api/questions: {e}")
        return json_response({'error': 'Palvelinvirhe.', 'details': str(e)}, 500)

@app.route("/api/simulation/update", methods=['POST'])
@login_required
@limiter.limit("60 per minute")
@api_csrf_protect
def update_simulation_api():
    try:
        data = request.get_json()
        active_session = db_manager.get_active_session(current_user.id)
        if not active_session or active_session.get('session_type') != 'simulation':
            return json_response({'success': False, 'error': 'No active simulation found.'}, 404)
        current_index = data.get('current_index', active_session['current_index'])
        answers = data.get('answers', active_session['answers'])
        time_remaining = data.get('time_remaining', active_session['time_remaining'])
        db_manager.save_or_update_session(
            user_id=current_user.id,
            session_type='simulation',
            question_ids=active_session['question_ids'],
            answers=answers,
            current_index=current_index,
            time_remaining=time_remaining
        )
        app.logger.info(f"Updated simulation for user {current_user.username}")
        return json_response({'success': True})
    except Exception as e:
        app.logger.error(f"Error updating simulation: {e}")
        return json_response({'success': False, 'error': str(e)}, 500)

@app.route("/api/simulation/delete", methods=['POST'])
@login_required
@api_csrf_protect
def delete_active_session_route():
    success, error = db_manager.delete_active_session(current_user.id)
    if success:
        app.logger.info(f"Deleted active simulation for user {current_user.id}")
        return json_response({'success': True})
    app.logger.error(f"Error deleting active session for user {current_user.id}: {error}")
    return json_response({'success': False, 'error': str(error)}, 500)

@app.route("/api/stats")
@login_required
@limiter.limit("60 per minute")
def get_stats_api():
    return json_response(stats_manager.get_learning_analytics(current_user.id))

@app.route("/api/achievements")
@login_required
@limiter.limit("60 per minute")
def get_achievements_api():
    try:
        unlocked_objects = achievement_manager.get_unlocked_achievements(current_user.id)
        unlocked_ids = {ach.id for ach in unlocked_objects}
        all

# ============================================================================
# SIVUJEN REITIT
# ============================================================================

@app.route("/")
def index_route():
    return redirect(url_for('login_route')) if not current_user.is_authenticated else redirect(url_for('dashboard_route'))

@app.route("/privacy")
def privacy_route():
    return render_template("privacy.html")

@app.route("/terms")
def terms_route():
    return render_template("terms.html")

@app.route("/dashboard")
@login_required
def dashboard_route():
    analytics = stats_manager.get_learning_analytics(current_user.id)
    coach_pick = None
    weak_categories = [
        cat for cat in analytics.get('categories', []) 
        if cat.get('success_rate') is not None and cat.get('attempts', 0) >= 5
    ]
    if weak_categories:
        coach_pick = min(weak_categories, key=lambda x: x['success_rate'])
    strength_pick = None
    strong_categories = [
        cat for cat in analytics.get('categories', []) 
        if cat.get('success_rate') is not None and cat.get('attempts', 0) >= 10
    ]
    if strong_categories:
        strength_pick = max(strong_categories, key=lambda x: x['success_rate'])
    try:
        result = db_manager._execute("""
            SELECT COUNT(DISTINCT question_id) as count FROM question_attempts 
            WHERE user_id = ? AND correct = ?
        """, (current_user.id, False if db_manager.is_postgres else 0), fetch='one')
        mistake_count = result['count'] if result else 0
    except Exception as e:
        app.logger.error(f"Error fetching mistake count: {e}")
        mistake_count = 0
    user_data_row = db_manager.get_user_by_id(current_user.id)
    user_data = dict(user_data_row) if user_data_row else {}
    categories_json = user_data.get('last_practice_categories') or '[]'
    difficulties_json = user_data.get('last_practice_difficulties') or '[]'
    last_categories = json.loads(categories_json)
    last_difficulties = json.loads(difficulties_json)
    all_categories_from_db = db_manager.get_categories()
    active_session = db_manager.get_active_session(current_user.id)
    has_active_simulation = (active_session is not None and active_session.get('session_type') == 'simulation')
    return render_template(
        'dashboard.html', 
        categories=all_categories_from_db,
        last_categories=last_categories,
        last_difficulties=last_difficulties,
        has_active_simulation=has_active_simulation,
        coach_pick=coach_pick,
        strength_pick=strength_pick,
        mistake_count=mistake_count
    )

@app.route("/practice")
@login_required
def practice_route():
    return render_template("practice.html", category="Kaikki kategoriat", constants={'DISTRACTORS': DISTRACTORS})

@app.route("/practice/<category>")
@login_required
def practice_category_route(category):
    return render_template("practice.html", category=category, constants={'DISTRACTORS': DISTRACTORS})

@app.route("/review")
@login_required
def review_route():
    return render_template("review.html")

@app.route("/stats")
@login_required
def stats_route():
    return render_template("stats.html")

@app.route("/achievements")
@login_required
def achievements_route():
    return render_template("achievements.html")

@app.route("/mistakes")
@login_required
def mistakes_route():
    return render_template("mistakes.html")

@app.route("/calculator")
@login_required
def calculator_route():
    return render_template("calculator.html")

@app.route("/simulation")
@login_required
def simulation_route():
    force_new = request.args.get('new', 'false').lower() == 'true'
    resume = request.args.get('resume', 'false').lower() == 'true'
    active_session = db_manager.get_active_session(current_user.id)
    has_active = active_session is not None and active_session.get('session_type') == 'simulation'
    
    if resume and has_active:
        app.logger.info(f"Resuming simulation for user {current_user.username}")
        try:
            question_ids = active_session['question_ids']
            if isinstance(question_ids, str):
                question_ids = json.loads(question_ids)
            answers = active_session['answers']
            if isinstance(answers, str):
                answers = json.loads(answers)
            if len(answers) != len(question_ids):
                answers = [None] * len(question_ids)
                active_session['answers'] = answers
            if 'last_updated' in active_session and isinstance(active_session['last_updated'], datetime):
                active_session['last_updated'] = active_session['last_updated'].isoformat()
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            app.logger.error(f"Error parsing session data: {e}")
            flash("Kesken eräisen simulaation lataus epäonnistui. Aloita uusi.", "warning")
            db_manager.delete_active_session(current_user.id)
            return redirect(url_for('dashboard_route'))
        
        questions = [db_manager.get_question_by_id(qid, current_user.id) for qid in question_ids]
        questions = [q for q in questions if q is not None]
        if len(questions) != len(question_ids):
            app.logger.error(f"Question count mismatch: {len(questions)} vs {len(question_ids)}")
            flash("Virhe kysymysten lataamisessa. Aloita uusi simulaatio.", "danger")
            db_manager.delete_active_session(current_user.id)
            return redirect(url_for('dashboard_route'))
        
        questions_data = [asdict(q) for q in questions]
        for q_dict in questions_data:
            for key, value in q_dict.items():
                if isinstance(value, datetime):
                    q_dict[key] = value.isoformat()
        
        return render_template("simulation.html", 
                               session_data=active_session, 
                               questions_data=questions_data,
                               has_existing_session=False,
                               constants={'DISTRACTORS': DISTRACTORS})
    
    elif has_active and not force_new:
        try:
            question_ids = active_session['question_ids']
            if isinstance(question_ids, str):
                question_ids = json.loads(question_ids)
            answers = active_session['answers']
            if isinstance(answers, str):
                answers = json.loads(answers)
            session_info = {
                'answered': len([a for a in answers if a is not None]),
                'total': len(question_ids),
                'time_remaining_minutes': active_session.get('time_remaining', 3600) // 60,
                'current_index': active_session.get('current_index', 0) + 1
            }
            return render_template("simulation.html",
                                   session_data={},
                                   questions_data=[],
                                   has_existing_session=True,
                                   session_info=session_info,
                                   constants={'DISTRACTORS': DISTRACTORS})
        except Exception as e:
            app.logger.error(f"Error parsing session info: {e}")
            db_manager.delete_active_session(current_user.id)
    
    app.logger.info(f"Starting new simulation for user {current_user.username}")
    if has_active:
        db_manager.delete_active_session(current_user.id)
        app.logger.info(f"Deleted old session before starting new")
    
    questions = db_manager.get_questions(user_id=current_user.id, limit=50)
    if len(questions) < 50:
        flash("Tietokannassa ei ole tarpeeksi kysymyksiä (50) koesimulaation suorittamiseen.", "warning")
        return redirect(url_for('dashboard_route'))
    
    question_ids = [q.id for q in questions]
    questions_data = [asdict(q) for q in questions]
    for q_dict in questions_data:
        for key, value in q_dict.items():
            if isinstance(value, datetime):
                q_dict[key] = value.isoformat()
    
    new_session = {
        "user_id": current_user.id,
        "session_type": "simulation",
        "question_ids": question_ids,
        "answers": [None] * len(questions),
        "current_index": 0,
        "time_remaining": 3600
    }
    
    db_manager.save_or_update_session(**new_session)
    app.logger.info(f"New simulation created: {len(questions)} questions")
    
    return render_template("simulation.html", 
                           session_data=new_session, 
                           questions_data=questions_data,
                           has_existing_session=False,
                           constants={'DISTRACTORS': DISTRACTORS})

@app.route("/profile")
@login_required
def profile_route():
    return render_template("profile.html", stats=stats_manager.get_learning_analytics(current_user.id))

@app.route("/settings", methods=['GET', 'POST'])
@login_required
def settings_route():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('Uusi salasana ja sen vahvistus eivät täsmää.', 'danger')
            return redirect(url_for('settings_route'))
        
        try:
            user_data = db_manager._execute("SELECT password FROM users WHERE id = ?", (current_user.id,), fetch='one')
            if not user_data or not bcrypt.check_password_hash(user_data['password'], current_password):
                flash('Nykyinen salasana on väärä.', 'danger')
                return redirect(url_for('settings_route'))
        except Exception as e:
            app.logger.error(f"Error checking password: {e}")
            flash('Salasanan vaihdossa tapahtui virhe.', 'danger')
            return redirect(url_for('settings_route'))
        
        new_hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        success, error = db_manager.update_user_password(current_user.id, new_hashed_password)
        if success:
            flash('Salasana vaihdettu onnistuneesti!', 'success')
            app.logger.info(f"User {current_user.username} changed password")
        else:
            flash(f'Salasanan vaihdossa tapahtui virhe: {error}', 'danger')
            app.logger.error(f"Password change failed for user {current_user.username}: {error}")
        
        return redirect(url_for('settings_route'))
    
    return render_template("settings.html")    

# ============================================================================
# KIRJAUTUMISEN REITIT
# ============================================================================

@app.route("/login", methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login_route():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard_route'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('Syötä käyttäjänimi ja salasana.', 'danger')
            return render_template("login.html")
        
        try:
            user_data = db_manager._execute(
                "SELECT * FROM users WHERE username = ?", 
                (username,),
                fetch='one'
            )
            if user_data and bcrypt.check_password_hash(user_data['password'], password):
                user = User(
                    id=user_data['id'],
                    username=user_data['username'],
                    email=user_data['email'],
                    role=user_data['role'],
                    distractors_enabled=bool(user_data.get('distractors_enabled', False)),
                    distractor_probability=user_data.get('distractor_probability', 25),
                    expires_at=user_data.get('expires_at')
                )
                login_user(user)
                app.logger.info(f"User {username} logged in successfully")
                next_page = request.args.get('next')
                return redirect(next_page or url_for('dashboard_route'))
            else:
                flash('Virheellinen käyttäjänimi tai salasana.', 'danger')
        except Exception as e:
            app.logger.error(f"Login error: {e}", exc_info=True)
            flash('Kirjautumisessa tapahtui odottamaton virhe.', 'danger')
    
    return render_template("login.html")

@app.route("/register", methods=['GET', 'POST'])
def register_route():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not all([username, email, password]):
            flash('Kaikki kentät ovat pakollisia.', 'danger')
            return render_template("register.html")
        
        if not re.match(r'^[a-zA-Z0-9_]{3,30}$', username):
            flash('Käyttäjänimen tulee olla 3-30 merkkiä pitkä ja sisältää vain kirjaimia, numeroita ja alaviivoja.', 'danger')
            return render_template("register.html")
        
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            flash('Virheellinen sähköpostiosoite.', 'danger')
            return render_template("register.html")
        
        if len(password) < 8:
            flash('Salasanan tulee olla vähintään 8 merkkiä pitkä.', 'danger')
            return render_template("register.html")
        
        if not re.search(r'[A-Z]', password):
            flash('Salasanan tulee sisältää vähintään yksi iso kirjain.', 'danger')
            return render_template("register.html")
        
        if not re.search(r'[a-z]', password):
            flash('Salasanan tulee sisältää vähintään yksi pieni kirjain.', 'danger')
            return render_template("register.html")
        
        if not re.search(r'[0-9]', password):
            flash('Salasanan tulee sisältää vähintään yksi numero.', 'danger')
            return render_template("register.html")
        
        try:
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            success, error_msg = db_manager.create_user(username, email, hashed_password)
            if success:
                flash('Rekisteröityminen onnistui! Voit nyt kirjautua sisään.', 'success')
                app.logger.info(f"New user registered: {username}")
                return redirect(url_for('login_route'))
            else:
                if error_msg and 'users.username' in error_msg:
                    flash('Käyttäjänimi on jo käytössä.', 'danger')
                elif error_msg and 'users.email' in error_msg:
                    flash('Sähköpostiosoite on jo käytössä.', 'danger')
                else:
                    flash(f'Rekisteröitymisessä tapahtui odottamaton virhe: {error_msg}', 'danger')
                app.logger.error(f"Registration failed for {username}: {error_msg}")
        except Exception as e:
            flash('Rekisteröitymisessä tapahtui kriittinen virhe.', 'danger')
            app.logger.error(f"Critical registration error: {e}")
    
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout_route():
    username = current_user.username
    logout_user()
    flash('Olet kirjautunut ulos.', 'info')
    app.logger.info(f"User {username} logged out")
    return redirect(url_for('login_route'))

# ============================================================================
# SALASANAN PALAUTUS REITIT
# ============================================================================

@app.route("/forgot-password", methods=['GET', 'POST'])
def forgot_password_route():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            flash('Sähköpostiosoite on pakollinen.', 'danger')
            return render_template("forgot_password.html")
        try:
            user = db_manager._execute(
                "SELECT id, username, email FROM users WHERE email = ?", 
                (email,), 
                fetch='one'
            )
        except Exception as e:
            app.logger.error(f"Error fetching user by email: {e}")
            user = None
        if user:
            token = generate_reset_token(email)
            reset_url = url_for('reset_password_route', token=token, _external=True)
            if send_reset_email(email, reset_url):
                flash('Salasanan palautuslinkki on lähetetty sähköpostiisi.', 'success')
            else:
                flash('Sähköpostin lähetys epäonnistui.', 'danger')
        else:
            flash('Jos sähköpostiosoite löytyy järjestelmästä, siihen on lähetetty palautuslinkki.', 'info')
        return redirect(url_for('login_route'))
    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=['GET', 'POST'])
def reset_password_route(token):
    email = verify_reset_token(token)
    if not email:
        flash('Palautuslinkki on vanhentunut tai virheellinen.', 'danger')
        return redirect(url_for('forgot_password_route'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        if not new_password or not confirm_password:
            flash('Täytä molemmat kentät.', 'danger')
            return render_template("reset_password.html", token=token, email=email)
        if new_password != confirm_password:
            flash('Salasanat eivät täsmää.', 'danger')
            return render_template("reset_password.html", token=token, email=email)
        if len(new_password) < 8:
            flash('Salasanan tulee olla vähintään 8 merkkiä pitkä.', 'danger')
            return render_template("reset_password.html", token=token, email=email)
        try:
            user = db_manager.get_user_by_email(email)
            if user:
                hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
                success, error = db_manager.update_user_password(user['id'], hashed_password)
                if success:
                    flash('Salasana vaihdettu onnistuneesti! Voit nyt kirjautua sisään.', 'success')
                    app.logger.info(f"Password reset successful for user: {user['username']}")
                    return redirect(url_for('login_route'))
                else:
                    flash(f'Virhe salasanan vaihdossa: {error}', 'danger')
            else:
                flash('Käyttäjää ei löytynyt.', 'danger')
        except Exception as e:
            flash('Salasanan vaihdossa tapahtui virhe.', 'danger')
            app.logger.error(f"Password reset error: {e}")
    return render_template("reset_password.html", token=token, email=email)

# ============================================================================
# YLLÄPITÄJÄN REITIT
# ============================================================================

@app.route("/admin")
@admin_required
def admin_route():
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '')
    difficulty_filter = request.args.get('difficulty', '')
    try:
        query = "SELECT id, question, category, difficulty FROM questions WHERE 1=1"
        params = []
        if search_query:
            query += " AND (question LIKE ? OR explanation LIKE ?)"
            search_param = f"%{search_query}%"
            params.extend([search_param, search_param])
        if category_filter:
            query += " AND category = ?"
            params.append(category_filter)
        if difficulty_filter:
            query += " AND difficulty = ?"
            params.append(difficulty_filter)
        query += " ORDER BY id DESC"
        questions = db_manager._execute(query, tuple(params), fetch='all')
        categories = db_manager.get_categories()
        difficulties_result = db_manager._execute("SELECT DISTINCT difficulty FROM questions ORDER BY difficulty", fetch='all')
        difficulties = [row['difficulty'] for row in difficulties_result] if difficulties_result else []
        return render_template("admin.html", 
                               questions=[dict(row) for row in questions] if questions else [],
                               categories=categories,
                               difficulties=difficulties,
                               search_query=search_query,
                               category_filter=category_filter,
                               difficulty_filter=difficulty_filter,
                               total_count=len(questions) if questions else 0)
    except Exception as e:
        flash(f'Virhe kysymysten haussa: {e}', 'danger')
        app.logger.error(f"Admin questions fetch error: {e}")
        return render_template("admin.html", questions=[], categories=[], difficulties=[])

@app.route("/admin/users")
@admin_required
def admin_users_route():
    try:
        users = db_manager.get_all_users_for_admin()
        return render_template("admin_users.html", users=users)
    except Exception as e:
        flash(f'Virhe käyttäjien haussa: {e}', 'danger')
        app.logger.error(f"Admin users fetch error: {e}")
        return redirect(url_for('admin_route'))

@app.route("/admin/stats")
@admin_required
def admin_stats_route():
    try:
        correct_value = 'true' if db_manager.is_postgres else '1'
        general_stats = db_manager._execute(f"""
            SELECT
                COUNT(DISTINCT u.id) as total_users,
                COUNT(qa.id) as total_attempts,
                AVG(CASE WHEN qa.correct = {correct_value} THEN 100.0 ELSE 0.0 END) as avg_success_rate
            FROM users u
            LEFT JOIN question_attempts qa ON u.id = qa.user_id
        """, fetch='one')
        category_stats = db_manager._execute(f"""
            SELECT
                q.category,
                COUNT(qa.id) as attempts,
                AVG(CASE WHEN qa.correct = {correct_value} THEN 100.0 ELSE 0.0 END) as success_rate
            FROM questions q
            LEFT JOIN question_attempts qa ON q.id = qa.question_id
            GROUP BY q.category
            ORDER BY attempts DESC
        """, fetch='all')
        return render_template("admin_stats.html",
                               general_stats=dict(general_stats) if general_stats else {},
                               category_stats=[dict(row) for row in category_stats] if category_stats else [])
    except Exception as e:
        flash(f'Virhe tilastojen haussa: {e}', 'danger')
        app.logger.error(f"Admin stats fetch error: {e}")
        return redirect(url_for('admin_route'))

@app.route("/admin/edit_question/<int:question_id>", methods=['GET', 'POST'])
@admin_required
def admin_edit_question_route(question_id):
    if request.method == 'POST':
        data = {
            'question': request.form.get('question'),
            'explanation': request.form.get('explanation'),
            'options': [
                request.form.get('option_0'),
                request.form.get('option_1'),
                request.form.get('option_2'),
                request.form.get('option_3')
            ],
            'correct': int(request.form.get('correct')),
            'category': request.form.get('new_category') if request.form.get('category') == 'new_category' else request.form.get('category'),
            'difficulty': request.form.get('difficulty')
        }
        if not all(data.values()) or not all(data['options']):
            flash('Kaikki kentät ovat pakollisia.', 'danger')
            question_data = db_manager.get_single_question_for_edit(question_id)
            categories = db_manager.get_categories()
            return render_template("admin_edit_question.html", question=question_data, categories=categories)
        success, error = db_manager.update_question(question_id, data)
        if success:
            flash('Kysymys päivitetty onnistuneesti!', 'success')
            app.logger.info(f"Admin {current_user.username} edited question {question_id}")
            return redirect(url_for('admin_route'))
        else:
            flash(f'Virhe kysymyksen päivityksessä: {error}', 'danger')
            app.logger.error(f"Question update error for ID {question_id}: {error}")
            question_data = db_manager.get_single_question_for_edit(question_id)
            categories = db_manager.get_categories()
            return render_template("admin_edit_question.html", question=question_data, categories=categories)
    
    question_data = db_manager.get_single_question_for_edit(question_id)
    if not question_data:
        flash('Kysymystä ei löytynyt.', 'danger')
        return redirect(url_for('admin_route'))
    categories = db_manager.get_categories()
    return render_template("admin_edit_question.html", question=question_data, categories=categories)

@app.route("/admin/delete_question/<int:question_id>", methods=['POST'])
@admin_required
def admin_delete_question_route(question_id):
    success, error = db_manager.delete_question(question_id)
    if success:
        flash(f'Kysymys #{question_id} poistettu onnistuneesti.', 'success')
        app.logger.info(f"Admin {current_user.username} deleted question {question_id}")
    else:
        flash(f'Virhe kysymyksen poistossa: {error}', 'danger')
        app.logger.error(f"Question delete error for ID {question_id}: {error}")
    return redirect(url_for('admin_route'))

@app.route("/admin/toggle_user/<int:user_id>", methods=['POST'])
@admin_required
def admin_toggle_user_route(user_id):
    if user_id == 1:
        flash('Pääkäyttäjän tilaa ei voi muuttaa.', 'danger')
        return redirect(url_for('admin_users_route'))
    success, error = db_manager.toggle_user_status(user_id)
    if success:
        flash('Käyttäjän tila vaihdettu onnistuneesti.', 'success')
        app.logger.info(f"Admin {current_user.username} toggled status for user ID {user_id}")
    else:
        flash(f'Virhe tilan vaihdossa: {error}', 'danger')
        app.logger.error(f"User status toggle error for ID {user_id}: {error}")
    return redirect(url_for('admin_users_route'))

@app.route("/admin/toggle_role/<int:user_id>", methods=['POST'])
@admin_required
def admin_toggle_role_route(user_id):
    if user_id == 1:
        flash('Pääkäyttäjän roolia ei voi muuttaa.', 'danger')
        return redirect(url_for('admin_users_route'))
    user = db_manager.get_user_by_id(user_id)
    if not user:
        flash('Käyttäjää ei löytynyt.', 'danger')
        return redirect(url_for('admin_users_route'))
    new_role = 'admin' if user['role'] == 'user' else 'user'
    success, error = db_manager.update_user_role(user_id, new_role)
    if success:
        flash('Käyttäjän rooli vaihdettu onnistuneesti.', 'success')
        app.logger.info(f"Admin {current_user.username} changed role for user ID {user_id} to {new_role}")
    else:
        flash(f'Virhe roolin vaihdossa: {error}', 'danger')
        app.logger.error(f"User role toggle error for ID {user_id}: {error}")
    return redirect(url_for('admin_users_route'))

@app.route("/admin/delete_user/<int:user_id>", methods=['POST'])
@admin_required
def admin_delete_user_route(user_id):
    if user_id == 1:
        flash('Pääkäyttäjää ei voi poistaa.', 'danger')
        return redirect(url_for('admin_users_route'))
    success, error = db_manager.delete_user_by_id(user_id)
    if success:
        flash(f'Käyttäjä #{user_id} ja kaikki hänen tietonsa on poistettu onnistuneesti.', 'success')
        app.logger.info(f"Admin {current_user.username} deleted user {user_id}")
    else:
        flash(f'Virhe käyttäjän poistossa: {error}', 'danger')
        app.logger.error(f"User delete error for ID {user_id}: {error}")
    return redirect(url_for('admin_users_route'))

@app.route("/admin/bulk_delete_duplicates", methods=['POST'])
@admin_required
def admin_bulk_delete_duplicates_route():
    question_ids_str = request.form.get('question_ids', '')
    if not question_ids_str:
        flash('⚠️ Ei kysymyksiä poistettavaksi.', 'warning')
        return redirect(url_for('admin_find_duplicates_route'))
    try:
        question_ids = [int(qid.strip()) for qid in question_ids_str.split(',') if qid.strip()]
        if not question_ids:
            flash('⚠️ Ei kelvollisia kysymys-ID:itä.', 'warning')
            return redirect(url_for('admin_find_duplicates_route'))
        deleted_count = 0
        failed_count = 0
        for question_id in question_ids:
            success, error = db_manager.delete_question(question_id)
            if success:
                deleted_count += 1
            else:
                failed_count += 1
                app.logger.error(f"Failed to delete question {question_id}: {error}")
        if deleted_count > 0:
            flash(f'✅ Poistettiin {deleted_count} duplikaattikysymystä onnistuneesti!', 'success')
            app.logger.info(f"Admin {current_user.username} bulk deleted {deleted_count} duplicate questions")
        if failed_count > 0:
            flash(f'⚠️ {failed_count} kysymyksen poisto epäonnistui.', 'warning')
    except ValueError as e:
        flash(f'❌ Virheelliset kysymys-ID:t: {str(e)}', 'danger')
        app.logger.error(f"Bulk delete parsing error: {e}")
    except Exception as e:
        flash(f'❌ Odottamaton virhe: {str(e)}', 'danger')
        app.logger.error(f"Bulk delete error: {e}")
    return redirect(url_for('admin_find_duplicates_route'))

@app.route("/admin/add_question", methods=['GET', 'POST'])
@admin_required
def admin_add_question_route():
    if request.method == 'POST':
        question_text = request.form.get('question', '').strip()
        explanation = request.form.get('explanation', '').strip()
        category = request.form.get('new_category') if request.form.get('category') == '__add_new__' else request.form.get('category')
        difficulty = request.form.get('difficulty')
        options = [
            request.form.get('option_0', '').strip(),
            request.form.get('option_1', '').strip(),
            request.form.get('option_2', '').strip(),
            request.form.get('option_3', '').strip()
        ]
        correct_answer_text = request.form.get('correct_answer', '').strip()
        if not all([question_text, explanation, category, difficulty]) or not all(options) or not correct_answer_text:
            flash('Kaikki kentät ovat pakollisia.', 'danger')
            categories = db_manager.get_categories()
            return render_template("admin_add_question.html", categories=categories)
        if correct_answer_text not in options:
            flash('Oikea vastaus ei löydy vaihtoehdoista!', 'danger')
            categories = db_manager.get_categories()
            return render_template("admin_add_question.html", categories=categories)
        is_duplicate, existing = db_manager.check_question_duplicate(question_text)
        if is_duplicate:
            flash(
                f'⚠️ Vastaava kysymys on jo kannassa!\n'
                f'ID: {existing["id"]} | Kategoria: {existing["category"]} | '
                f'Kysymys: "{existing["question"][:100]}..."',
                'warning'
            )
            categories = db_manager.get_categories()
            return render_template("admin_add_question.html", categories=categories)
        random.shuffle(options)
        correct = options.index(correct_answer_text)
        try:
            question_normalized = db_manager.normalize_question(question_text)
            db_manager._execute('''
                INSERT INTO questions (question, question_normalized, options, correct, explanation, category, difficulty, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (question_text, question_normalized, json.dumps(options), correct, explanation, category, difficulty, datetime.now()), fetch='none')
            flash('Kysymys lisätty onnistuneesti!', 'success')
            app.logger.info(f"Admin {current_user.username} added new question in category {category}")
            return redirect(url_for('admin_route'))
        except Exception as e:
            flash(f'Virhe kysymyksen lisäämisessä: {e}', 'danger')
            app.logger.error(f"Question add error: {e}")
    categories = db_manager.get_categories()
    return render_template("admin_add_question.html", categories=categories)

# ============================================================================
# DOKUMENTTIEN LUONTIFUNKTIOT - OSA 1: PDF
# ============================================================================

def create_pdf_document(questions, include_answers, duplicate_info=None):
    # Jatka tästä: story.append(Spacer(1, 0.3*inch))
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                            topMargin=0.75*inch, 
                            bottomMargin=0.75*inch,
                            leftMargin=0.75*inch,
                            rightMargin=0.75*inch)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Question', fontSize=12, leading=14, spaceAfter=8))
    styles.add(ParagraphStyle(name='Option', fontSize=10, leading=12, leftIndent=20, spaceAfter=4))
    styles.add(ParagraphStyle(name='Answer', fontSize=10, leading=12, textColor=colors.green, spaceBefore=8, spaceAfter=8))
    styles.add(ParagraphStyle(name='Explanation', fontSize=10, leading=12, textColor=colors.blue, spaceBefore=8, spaceAfter=12))
    story = []

    # Otsikko
    story.append(Paragraph("LOVe Enhanced - Kysymykset", styles['Title']))
    story.append(Spacer(1, 0.5*inch))

    # Duplikaattitiedot, jos annettu
    if duplicate_info:
        story.append(Paragraph(duplicate_info, styles['Normal']))
        story.append(Spacer(1, 0.3*inch))

    # Sisällysluettelo
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("Sisällysluettelo", styles['Heading2']))
    category_counts = {}
    for q in questions:
        cat = q['category']
        category_counts[cat] = category_counts.get(cat, 0) + 1

    toc_data = [[Paragraph(f"{cat}: {count} kysymystä", styles['Normal'])] for cat, count in sorted(category_counts.items())]
    toc_table = Table(toc_data, colWidths=[6.5*inch])
    toc_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(toc_table)
    story.append(Spacer(1, 0.5*inch))
    story.append(PageBreak())

    # Kysymykset kategorioittain
    current_category = None
    for i, q in enumerate(questions, 1):
        if q['category'] != current_category:
            current_category = q['category']
            story.append(Paragraph(f"Kategoria: {current_category}", styles['Heading2']))
            story.append(Spacer(1, 0.2*inch))
        
        # Kysymys
        story.append(Paragraph(f"{i}. {q['question']}", styles['Question']))
        
        # Vaihtoehdot
        for j, opt in enumerate(q['options'], 1):
            story.append(Paragraph(f"{j}. {opt}", styles['Option']))
        
        # Oikea vastaus ja selitys, jos include_answers on True
        if include_answers:
            correct_answer = q['options'][q['correct']]
            story.append(Paragraph(f"Oikea vastaus: {correct_answer}", styles['Answer']))
            story.append(Paragraph(f"Selitys: {q['explanation']}", styles['Explanation']))
        
        story.append(Spacer(1, 0.3*inch))
    
    # Footer jokaiselle sivulle
    def add_page_number(canvas, doc):
        page_num = canvas.getPageNumber()
        text = f"Sivu {page_num}"
        canvas.setFont('Helvetica', 9)
        canvas.drawRightString(7.5*inch, 0.5*inch, text)
    
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    buffer.seek(0)
    return buffer

# ============================================================================
# DOKUMENTTIEN LUONTIFUNKTIOT - OSA 2: WORD
# ============================================================================

def create_word_document(questions, include_answers, duplicate_info=None):
    buffer = BytesIO()
    doc = Document()
    
    # Otsikko
    heading = doc.add_heading('LOVe Enhanced - Kysymykset', level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Duplikaattitiedot, jos annettu
    if duplicate_info:
        p = doc.add_paragraph(duplicate_info)
        p.runs[0].font.color.rgb = RGBColor(255, 0, 0)  # Punainen väri varoitukselle
        doc.add_paragraph()  # Väli
    
    # Sisällysluettelo
    doc.add_heading('Sisällysluettelo', level=2)
    category_counts = {}
    for q in questions:
        cat = q['category']
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    for cat, count in sorted(category_counts.items()):
        doc.add_paragraph(f"{cat}: {count} kysymystä", style='ListBullet')
    
    doc.add_page_break()
    
    # Kysymykset kategorioittain
    current_category = None
    for i, q in enumerate(questions, 1):
        if q['category'] != current_category:
            current_category = q['category']
            heading = doc.add_heading(f"Kategoria: {current_category}", level=2)
        
        # Kysymys
        p = doc.add_paragraph(f"{i}. {q['question']}", style='Normal')
        p.runs[0].font.bold = True
        
        # Vaihtoehdot
        for j, opt in enumerate(q['options'], 1):
            doc.add_paragraph(f"{j}. {opt}", style='ListNumber')
        
        # Oikea vastaus ja selitys
        if include_answers:
            correct_answer = q['options'][q['correct']]
            p = doc.add_paragraph(f"Oikea vastaus: {correct_answer}")
            p.runs[0].font.color.rgb = RGBColor(0, 128, 0)  # Vihreä väri
            p = doc.add_paragraph(f"Selitys: {q['explanation']}")
            p.runs[0].font.color.rgb = RGBColor(0, 0, 255)  # Sininen väri
        
        doc.add_paragraph()  # Väli seuraavaan kysymykseen
    
    # Tallenna dokumentti bufferiin
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# ============================================================================
# SOVELLUKSEN KÄYNNISTYS
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=DEBUG_MODE)

