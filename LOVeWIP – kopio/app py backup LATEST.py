# app.py

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
from datetime import datetime, timedelta, timezone
from functools import wraps
from io import BytesIO
from logging.handlers import RotatingFileHandler
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ============================================================================
# THIRD-PARTY KIRJASTOT
# ============================================================================
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session
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
# OMAT MODUULIT - TÄMÄ ON KORJATTU JA TÄRKEÄ OSA
# ============================================================================
from data_access.database_manager import DatabaseManager
from logic.stats_manager import EnhancedStatsManager
from logic.achievement_manager import EnhancedAchievementManager, ENHANCED_ACHIEVEMENTS
from logic.spaced_repetition import SpacedRepetitionManager
from logic import simulation_manager # Tuodaan simulation_manager
from models.models import User, Question
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
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://"
)

# ============================================================================
# TIETOKANTA JA MANAGERIT
# ============================================================================
# DatabaseManager havaitsee automaattisesti PostgreSQL (Railway) vs SQLite (local)
db_manager = DatabaseManager()
stats_manager = EnhancedStatsManager(db_manager)
achievement_manager = EnhancedAchievementManager(db_manager)
spaced_repetition_manager = SpacedRepetitionManager(db_manager)
bcrypt = Bcrypt(app)

# ============================================================================
# POSTGRESQL YHTEENSOPIVUUS - HELPER FUNKTIO
# ============================================================================

def execute_query(query, params=(), fetch='all'):
    """
    Helper-funktio joka toimii sekä SQLite:n että PostgreSQL:n kanssa.
    """
    return db_manager._execute(query, params, fetch)

# ============================================================================
# TIETOKANNAN ALUSTUSTOIMINNOT
# ============================================================================

def init_distractor_table():
    """
    Luo distractor_attempts-taulu jos sitä ei vielä ole.
    Toimii sekä PostgreSQL:n (Railway) että SQLite:n (local) kanssa.
    """
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        if db_manager.is_postgres:
            # PostgreSQL-syntaksi (Railway)
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
            # SQLite-syntaksi (paikallinen kehitys)
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
        cursor.close()
        conn.close()
        
    except Exception as e:
        app.logger.error(f"Virhe häiriötekijätaulun luomisessa: {e}")

# Kutsu taulun luontifunktio sovelluksen käynnistyessä
# init_distractor_table()

# HUOM: Sarakkeiden lisäysfunktiot (add_distractor_probability_column ja 
# add_user_expiration_column) on POISTETTU, koska DatabaseManager hoitaa 
# migraatiot automaattisesti migrate_database() metodissa!

# ============================================================================
# FLASK-LOGIN SETUP
# ============================================================================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_route'
login_manager.login_message = "Kirjaudu sisään nähdäksesi tämän sivun."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    """
    Lataa käyttäjän tiedot tietokannasta.
    Käyttää db_manager._execute() metodia joka toimii sekä PostgreSQL:n että SQLite:n kanssa.
    """
    try:
        # Käytä db_manager:in _execute metodia (toimii sekä PostgreSQL että SQLite)
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
        app.logger.error(f"Virhe käyttäjän lataamisessa: {e}")
    
    return None

# ============================================================================
# APUFUNKTIOT
# ============================================================================

def admin_required(f):
    """Dekoraattori joka vaatii admin-oikeudet."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash("Pääsy kielletty. Vaatii ylläpitäjän oikeudet.", "danger")
            return redirect(url_for('dashboard_route'))
        return f(*args, **kwargs)
    return decorated_function

def generate_secure_password(length=10):
    """
    Luo turvallisen satunnaisen salasanan.
    Sisältää: isoja kirjaimia, pieniä kirjaimia ja numeroita.
    """
    if length < 8:
        length = 8
    
    pienet = string.ascii_lowercase
    isot = string.ascii_uppercase
    numerot = string.digits
    
    # Varmista että salasanassa on vähintään yksi jokaisesta ryhmästä
    salasana = [
        random.choice(pienet),
        random.choice(isot),
        random.choice(numerot),
    ]
    
    # Täytä loput satunnaisilla merkeillä
    kaikki_merkit = pienet + isot + numerot
    for _ in range(length - len(salasana)):
        salasana.append(random.choice(kaikki_merkit))
    
    # Sekoita järjestys
    random.shuffle(salasana)
    return "".join(salasana)

# ============================================================================
# SALASANAN PALAUTUS
# ============================================================================

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
    """Lähettää salasanan palautusviestin Brevo:n kautta."""
    
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY')
    FROM_EMAIL = os.environ.get('FROM_EMAIL', 'noreply@example.com')
    
    if not BREVO_API_KEY:
        # Kehitysympäristössä printtaa linkki
        app.logger.warning(f"Brevo ei konfiguroitu. Palautuslinkki: {reset_url}")
        print(f"\n{'='*80}")
        print(f"SALASANAN PALAUTUSLINKKI:")
        print(f"{reset_url}")
        print(f"{'='*80}\n")
        return True
    
    import requests
    
    url = "https://api.brevo.com/v3/smtp/email"
    
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    
    payload = {
        "sender": {
            "name": "LOVe Enhanced",
            "email": FROM_EMAIL
        },
        "to": [
            {
                "email": user_email,
                "name": user_email.split('@')[0]
            }
        ],
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
    
@app.route('/api/simulation/question/<int:index>')
@login_required
def get_simulation_question_api(index):
    """Hakee yhden kysymyksen simulaatiota varten indeksin perusteella."""
    if 'simulation' not in session or session['simulation'].get('user_id') != current_user.id:
        return jsonify({'error': 'No active simulation found'}), 404

    sim_session = session['simulation']
    question_ids = sim_session.get('question_ids', [])

    if 0 <= index < len(question_ids):
        question_id = question_ids[index]
        question = db_manager.get_question_by_id(question_id, current_user.id)
        if question:
            # Päivitä sessioon nykyinen indeksi
            session['simulation']['current_index'] = index
            session.modified = True
            
            # Rakenna JSON-vastaus oikeilla kentillä
            return jsonify({
                'id': question.id,
                'question': question.question,
                'options': question.options,
                'correct': question.correct,
                'explanation': question.explanation,
                'category': question.category,
                'difficulty': question.difficulty,
                'times_shown': getattr(question, 'times_shown', 0),
                'times_correct': getattr(question, 'times_correct', 0)
            })
        else:
            return jsonify({'error': f'Question with id {question_id} not found'}), 404
    else:
        return jsonify({'error': 'Invalid question index'}), 400

@app.route('/api/csrf-token')
def get_csrf_token():
    return jsonify({'csrf_token': generate_csrf()})

# app.py

@app.route("/api/incorrect_questions")
@login_required
@limiter.limit("60 per minute")
def get_incorrect_questions_api():
    """Hakee kysymykset joihin käyttäjä on vastannut väärin, piilottaen kuitatut."""
    try:
        incorrect_questions = execute_query("""
            SELECT 
                q.id, q.question, q.category, q.difficulty, q.explanation,
                p.times_shown, p.times_correct, p.last_shown,
                ROUND((p.times_correct * 100.0) / NULLIF(p.times_shown, 0), 1) as success_rate
            FROM questions q
            INNER JOIN user_question_progress p ON q.id = p.question_id
            WHERE p.user_id = ?
                AND p.times_correct < p.times_shown
                AND (p.mistake_acknowledged IS NULL OR p.mistake_acknowledged = ?) -- LISÄTTY TÄMÄ RIVI
            ORDER BY success_rate ASC NULLS FIRST, p.times_shown DESC
        """, (current_user.id, False), fetch='all') # LISÄTTY 'False' PARAMETRI
        
        return jsonify({'questions': [dict(q) for q in incorrect_questions] if incorrect_questions else []})
            
    except Exception as e:
        app.logger.error(f"Virhe väärien vastausten haussa: {e}")
        return jsonify({'error': str(e)}), 500

#
# --- TÄMÄ ON UUSI REITTI ---
#
@app.route("/api/mistakes/acknowledge", methods=['POST'])
@login_required
def acknowledge_mistakes_api():
    """Merkitsee yhden tai useamman kehityskohteen kuitatuksi."""
    data = request.get_json()
    question_ids = data.get('question_ids')

    if not isinstance(question_ids, list) or not question_ids:
        return jsonify({'success': False, 'error': 'question_ids-lista puuttuu'}), 400

    try:
        # Muutettu boolean-arvo Postgre-yhteensopivaksi
        true_val = True if db_manager.is_postgres else 1
        
        placeholders = ','.join('?' * len(question_ids))
        query = f"""
            UPDATE user_question_progress
            SET mistake_acknowledged = ?
            WHERE user_id = ? AND question_id IN ({placeholders})
        """
        params = [true_val, current_user.id] + question_ids
        
        execute_query(query, tuple(params), fetch='none')
        
        app.logger.info(f"User {current_user.id} acknowledged {len(question_ids)} mistakes.")
        return jsonify({'success': True, 'acknowledged_count': len(question_ids)})

    except Exception as e:
        app.logger.error(f"Virhe kehityskohteiden kuittauksessa: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/question_progress/<int:question_id>")
@login_required
@limiter.limit("60 per minute")
def get_question_progress_api(question_id):
    """Hakee käyttäjän edistymisen tietyssä kysymyksessä."""
    try:
        progress = execute_query("""
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
            return jsonify(dict(progress))
        else:
            return jsonify({
                'times_shown': 0,
                'times_correct': 0,
                'success_rate': 0,
                'last_shown': None
            })
            
    except Exception as e:
        app.logger.error(f"Virhe kysymyksen edistymisen haussa: {e}")
        return jsonify({'error': str(e)}), 500


@app.route("/api/settings/toggle_distractors", methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def toggle_distractors_api():
    data = request.get_json()
    is_enabled = data.get('enabled', False)
    
    try:
        execute_query("UPDATE users SET distractors_enabled = ? WHERE id = ?", (is_enabled, current_user.id), fetch='none')
        app.logger.info(f"User {current_user.username} toggled distractors: {is_enabled}")
        return jsonify({'success': True, 'distractors_enabled': is_enabled})
    except Exception as e:
        app.logger.error(f"Virhe häiriötekijöiden togglessa: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/settings/update_distractor_probability", methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def update_distractor_probability_api():
    data = request.get_json()
    probability = data.get('probability', 25)
    probability = max(0, min(100, int(probability)))
    
    try:
        execute_query("UPDATE users SET distractor_probability = ? WHERE id = ?", (probability, current_user.id), fetch='none')
        app.logger.info(f"User {current_user.username} updated distractor probability: {probability}%")
        return jsonify({'success': True, 'probability': probability})
    except Exception as e:
        app.logger.error(f"Virhe todennäköisyyden päivityksessä: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/question_counts")
@login_required
@limiter.limit("60 per minute")
def get_question_counts_api():
    """Hakee kysymysmäärät kategorioittain ja vaikeustasoittain."""
    try:
        category_counts = execute_query("""
            SELECT category, COUNT(*) as count
            FROM questions
            GROUP BY category
            ORDER BY category
        """, fetch='all')
        
        difficulty_counts = execute_query("""
            SELECT difficulty, COUNT(*) as count
            FROM questions
            GROUP BY difficulty
        """, fetch='all')
        
        category_difficulty_counts = execute_query("""
            SELECT category, difficulty, COUNT(*) as count
            FROM questions
            GROUP BY category, difficulty
        """, fetch='all')
        
        total_result = execute_query("SELECT COUNT(*) as count FROM questions", fetch='one')
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
        
        return jsonify({
            'categories': {row['category']: row['count'] for row in category_counts} if category_counts else {},
            'difficulties': {row['difficulty']: row['count'] for row in difficulty_counts} if difficulty_counts else {},
            'category_difficulty_map': cat_diff_map,
            'total': total_count
        })
    except Exception as e:
        app.logger.error(f"Virhe kysymysmäärien haussa: {e}")
        return jsonify({'error': str(e)}), 500



# KORJATTU OSA: Lisätään uusi API-reitti häiriötekijöille
@app.route("/api/distractors")
@login_required
def get_distractors_api():
    """Palauttaa listan kaikista häiriötekijöistä."""
    return jsonify(DISTRACTORS)


@app.route("/api/submit_distractor", methods=['POST'])
@login_required
@limiter.limit("100 per minute")
def submit_distractor_api():
    try:
        data = request.get_json()
        scenario = data.get('scenario')
        user_choice = data.get('user_choice')
        response_time = data.get('response_time', 0)
        
        if scenario is None:
            return jsonify({'error': 'scenario is required'}), 400
        if user_choice is None:
            return jsonify({'error': 'user_choice is required'}), 400
        
        correct_choice = 0
        for distractor in DISTRACTORS:
            if distractor['scenario'] == scenario:
                correct_choice = distractor.get('correct', 0)
                break
        
        is_correct = user_choice == correct_choice
        
        execute_query("""
            INSERT INTO distractor_attempts
            (user_id, distractor_scenario, user_choice, correct_choice, is_correct, response_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (current_user.id, scenario, user_choice, correct_choice, is_correct, response_time, datetime.now()), fetch='none')
        
        app.logger.info(f"User {current_user.username} submitted distractor: correct={is_correct}")
        
        return jsonify({
            'success': True,
            'is_correct': is_correct,
            'correct_choice': correct_choice
        })
    except Exception as e:
        app.logger.error(f"Virhe distractor submitissa: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/user_preferences', methods=['POST'])
@login_required
def save_user_preferences():
    data = request.get_json()
    categories = data.get('categories', [])
    difficulties = data.get('difficulties', [])
    
    success, error = db_manager.update_user_practice_preferences(current_user.id, categories, difficulties)
    
    if success:
        return jsonify({'status': 'success', 'message': 'Asetukset tallennettu.'}), 200
    else:
        return jsonify({'status': 'error', 'message': error}), 500

@app.route("/api/submit_answer", methods=['POST'])
@login_required
@limiter.limit("100 per minute")
def submit_answer_api():
    data = request.get_json()
    question_id = data.get('question_id')
    selected_option_text = data.get('selected_option_text')
    time_taken = data.get('time_taken', 0)
    
    question = db_manager.get_question_by_id(question_id, current_user.id)
    
    if not question:
        app.logger.warning(f"Kysymystä {question_id} ei löytynyt käyttäjälle {current_user.username}")
        return jsonify({'error': 'Question not found'}), 404
    
    is_correct = (selected_option_text == question.options[question.correct])
    
    # Päivitä normaalit tilastot
    db_manager.update_question_stats(question_id, is_correct, time_taken, current_user.id)
    
    # --- KORJATTU OSA: Päivitä spaced repetition -järjestelmä oikein ---
    try:
        # 1. Määritä suorituksen laatu (0-5 asteikolla)
        # 5 = täydellinen, 2 = väärä vastaus
        quality = 5 if is_correct else 2
        
        # 2. Laske uusi kertausväli ja vaikeuskerroin
        # (question-objekti on jo haettu aiemmin ja sisältää vanhat `interval` ja `ease_factor` arvot)
        new_interval, new_ease_factor = spaced_repetition_manager.calculate_next_review(
            question=question, 
            performance_rating=quality
        )
        
        # 3. Tallenna päivitetyt tiedot tietokantaan
        spaced_repetition_manager.record_review(
            user_id=current_user.id,
            question_id=question_id,
            interval=new_interval,
            ease_factor=new_ease_factor
        )
        app.logger.info(f"Spaced repetition päivitetty: user={current_user.id}, q={question_id}, quality={quality}, new_interval={new_interval}")
    except Exception as e:
        app.logger.error(f"Virhe spaced repetition päivityksessä: {e}")
        # Ei estetä vastauksen tallentamista vaikka SR epäonnistuisi
    # --- KORJAUKSEN LOPPU ---

    # Tarkista saavutukset
    new_achievement_ids = achievement_manager.check_achievements(current_user.id)
    new_achievements = []
    
    for ach_id in new_achievement_ids:
        try:
            if ach_id in ENHANCED_ACHIEVEMENTS:
                ach_obj = ENHANCED_ACHIEVEMENTS[ach_id]
                if hasattr(ach_obj, '__dataclass_fields__'):
                    new_achievements.append(asdict(ach_obj))
                else:
                    new_achievements.append({
                        'id': getattr(ach_obj, 'id', ach_id),
                        'name': getattr(ach_obj, 'name', ''),
                        'description': getattr(ach_obj, 'description', ''),
                        'icon': getattr(ach_obj, 'icon', ''),
                        'unlocked': True,
                        'unlocked_at': getattr(ach_obj, 'unlocked_at', None)
                    })
        except Exception as e:
            app.logger.error(f"Virhe saavutuksen {ach_id} käsittelyssä: {e}")
            continue
    
    if new_achievements:
        app.logger.info(f"User {current_user.username} unlocked {len(new_achievements)} achievements")
    
    return jsonify({
        'correct': is_correct,
        'correct_answer_index': question.correct,
        'explanation': question.explanation,
        'new_achievements': new_achievements
    })

@app.route('/api/submit_simulation', methods=['POST'])
@login_required
def submit_simulation():
    """Palauta koe ja laske tulos."""
    try:
        if 'simulation' not in session:
            return jsonify({'error': 'No active simulation found'}), 404
        
        sim = session['simulation']
        app.logger.info(f"🎯 Submit simulation - User: {current_user.username}")
        
        user_answers = sim.get('answers', [])
        question_ids = sim.get('question_ids', [])
        
        app.logger.info(f"📊 Questions: {len(question_ids)}, Answers: {len(user_answers)}")
        
        # Laske tulos JA tallenna vastaukset
        score = 0
        total = len(question_ids)
        detailed_results = []
        
        for i, question_id in enumerate(question_ids):
            question = db_manager.get_question_by_id(question_id, current_user.id)
            
            if not question:
                app.logger.warning(f"⚠️ Question {question_id} not found")
                continue
            
            user_answer_index = user_answers[i] if i < len(user_answers) and user_answers[i] is not None else None
            is_correct = user_answer_index == question.correct
            
            if is_correct:
                score += 1
            
            # ✅ UUSI: Tallenna vastaus tietokantaan
            try:
                # Laske vastausaika (oletetaan keskiarvo 30s per kysymys)
                time_taken = 30
                
                # Tallenna question_attempts tauluun
                db_manager.update_question_stats(
                    question_id=question_id,
                    is_correct=is_correct,
                    time_taken=time_taken,
                    user_id=current_user.id
                )
                
                app.logger.info(f"💾 Saved answer: Q{question_id} - {'✓' if is_correct else '✗'}")
                
            except Exception as e:
                app.logger.error(f"❌ Error saving answer for Q{question_id}: {e}")
                # Jatka silti muiden tallentamista
            
            # Hae vastaukset tulossivulle
            user_answer_text = question.options[user_answer_index] if user_answer_index is not None and user_answer_index < len(question.options) else None
            correct_answer_text = question.options[question.correct] if question.correct < len(question.options) else None
            
            detailed_results.append({
                'question': question.question,
                'user_answer_text': user_answer_text,
                'correct_answer_text': correct_answer_text,
                'is_correct': is_correct,
                'explanation': question.explanation or 'Ei selitystä saatavilla'
            })
        
        percentage = (score / total * 100) if total > 0 else 0
        
        app.logger.info(f"✅ Score: {score}/{total} = {percentage:.1f}%")
        app.logger.info(f"💾 Saved {total} answers to database")
        
        # Poista sessio
        session.pop('simulation', None)
        session.modified = True
        
        return jsonify({
            'score': score,
            'total': total,
            'percentage': percentage,
            'detailed_results': detailed_results
        })
        
    except Exception as e:
        app.logger.error(f"❌ ERROR in submit_simulation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route("/api/questions")
@login_required
@limiter.limit("60 per minute")
def get_questions_api():
    """Hakee harjoituskysymyksiä valintojen mukaan, tukee myös simulaatiota."""
    try:
        # Käytä getlist() hakemaan kaikki valinnat listoina
        categories = request.args.getlist('categories')
        difficulties = request.args.getlist('difficulties')
        limit = int(request.args.get('count', 10))
        simulation = request.args.get('simulation') == 'true'

        app.logger.info(f"API call: user={current_user.id}, simulation={simulation}, categories={categories}, difficulties={difficulties}, limit={limit}")

        # Varmista, että tyhjät listat käsitellään oikein
        if not categories:
            categories = None
            app.logger.info("No categories provided - using all categories")
        if not difficulties:
            difficulties = None
            app.logger.info("No difficulties provided - using all difficulties")

        # Hae kysymykset
        if simulation:
            app.logger.info("Simulation mode: Fetching 50 random questions")
            questions = db_manager.get_questions(current_user.id, limit=50)  # Ei suodatus
        else:
            app.logger.info("Normal mode: Fetching with filters")
            questions = db_manager.get_questions(
                user_id=current_user.id,
                categories=categories,
                difficulties=difficulties,
                limit=limit
            )

        app.logger.info(f"Raw questions fetched: {len(questions)}")

        # Prosessoi kysymykset
        questions_list = []
        for q in questions:
            if q.options and 0 <= q.correct < len(q.options):
                original_correct_text = q.options[q.correct]
                random.shuffle(q.options)
                q.correct = q.options.index(original_correct_text)
            q_dict = asdict(q)
            questions_list.append(q_dict)

        if not questions_list:
            app.logger.warning("No questions returned - returning empty list")
            return jsonify({'questions': [], 'message': 'Ei kysymyksiä valituilla kriteereillä.'}), 200

        app.logger.info(f"Returning {len(questions_list)} processed questions")
        return jsonify({'questions': questions_list})

    except ValueError as ve:
        app.logger.error(f"Invalid parameter: {str(ve)}")
        return jsonify({'error': 'Virheellinen parametri (esim. count).', 'details': str(ve)}), 400
    except Exception as e:
        app.logger.error(f"Virhe /api/questions haussa: {str(e)}")
        if app.config['DEBUG']:
            import traceback
            traceback.print_exc()
        return jsonify({'error': 'Palvelinvirhe.', 'details': str(e)}), 500

@app.route('/api/simulation/update', methods=['POST'])
@login_required
def update_simulation():
    """Päivitä simulaation tilanne sessioniin."""
    try:
        data = request.json
        
        if 'simulation' not in session:
            return jsonify({'error': 'No active simulation'}), 404
        
        sim = session['simulation']
        
        # ✅ KRIITTINEN: Tallenna time_remaining
        if 'time_remaining' in data:
            sim['time_remaining'] = int(data['time_remaining'])
            app.logger.info(f"💾 Tallennetaan time_remaining: {sim['time_remaining']} sek")
        
        # Päivitä muut kentät
        if 'answers' in data:
            sim['answers'] = data['answers']
        
        if 'current_index' in data:
            sim['current_index'] = data['current_index']
        
        session.modified = True
        
        return jsonify({
            'success': True,
            'time_remaining': sim.get('time_remaining', 3600)
        })
        
    except Exception as e:
        app.logger.error(f"❌ ERROR in update_simulation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
@app.route("/api/stats")
@login_required
@limiter.limit("60 per minute")
def get_stats_api():
    return jsonify(stats_manager.get_learning_analytics(current_user.id))

@app.route("/api/distractor_stats")
@login_required
@limiter.limit("60 per minute")
def get_distractor_stats_api():
    """Palauta häiriötekijätilastot käyttäjälle."""
    try:
        # Hae häiriötekijätilastot tietokannasta
        query = """
            SELECT 
                COUNT(*) as total_attempts,
                SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) as correct_attempts,
                AVG(response_time) as avg_response_time
            FROM distractor_attempts 
            WHERE user_id = ?
        """
        result = db_manager._execute(query, (current_user.id,), fetch='one')
        
        if not result or result['total_attempts'] == 0:
            return jsonify({
                'total_attempts': 0,
                'success_rate': 0,
                'avg_response_time': 0,
                'category_stats': [],
                'recent_attempts': []
            })
        
        total = result['total_attempts'] or 0
        correct = result['correct_attempts'] or 0
        success_rate = round((correct / total * 100) if total > 0 else 0, 1)
        
        # Hae viimeisimmät häiriötilanteet
        recent_query = """
            SELECT distractor_scenario, is_correct, response_time, created_at
            FROM distractor_attempts
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 5
        """
        recent = db_manager._execute(recent_query, (current_user.id,), fetch='all')
        
        return jsonify({
            'total_attempts': total,
            'success_rate': success_rate,
            'avg_response_time': result['avg_response_time'] or 0,
            'category_stats': [],
            'recent_attempts': [dict(r) for r in (recent or [])]
        })
        
    except Exception as e:
        app.logger.error(f"Virhe häiriötekijätilastojen haussa: {e}")
        # Palauta tyhjä data virheen sijaan
        return jsonify({
            'total_attempts': 0,
            'success_rate': 0,
            'avg_response_time': 0,
            'category_stats': [],
            'recent_attempts': []
        })

@app.route("/api/achievements")
@login_required
@limiter.limit("60 per minute")
def get_achievements_api():
    try:
        # Hae käyttäjän avaamat saavutus-OLIOT
        unlocked_objects = achievement_manager.get_unlocked_achievements(current_user.id)
        
        # Käytä olioviittausta (.id) hakasulkeiden sijaan
        unlocked_ids = {ach.id for ach in unlocked_objects}
        
        all_achievements = []
        for ach_id, ach_obj in ENHANCED_ACHIEVEMENTS.items():
            try:
                ach_data = asdict(ach_obj)
                ach_data['unlocked'] = ach_id in unlocked_ids
                if ach_data['unlocked']:
                    # Etsi oikea avattu olio listalta
                    unlocked_data = next((item for item in unlocked_objects if item.id == ach_id), None)
                    if unlocked_data:
                        # Käytä olioviittausta (.unlocked_at) .get()-metodin sijaan
                        ach_data['unlocked_at'] = unlocked_data.unlocked_at
                all_achievements.append(ach_data)

            except Exception as e:
                logger.error(f"Virhe saavutuksen {ach_id} käsittelyssä: {e}")
                continue
        
        return jsonify(all_achievements)
    except Exception as e:
        # Lisätään tarkempi lokitus koko funktion virheelle
        logger.error(f"Koko /api/achievements-reitin suoritus epäonnistui: {e}", exc_info=True)
        return jsonify([])

@app.route("/api/review-questions")
@login_required
@limiter.limit("60 per minute")
def get_review_questions_api():
    due_questions = spaced_repetition_manager.get_due_questions(current_user.id, limit=1)
    
    if not due_questions:
        return jsonify({'question': None, 'distractor': None})
        
    question = due_questions[0]
    distractor = None
    
    try:
        # Muunna dataclass-objekti sanakirjaksi
        question_data = asdict(question)
    except Exception as e:
        app.logger.error(f"Virhe review-kysymyksen käsittelyssä: {e}")
        return jsonify({'question': None, 'distractor': None})
    
    # KORJATTU OSA: Käytä käyttäjän tallennettua todennäköisyyttä
    if hasattr(current_user, 'distractors_enabled') and current_user.distractors_enabled:
        # Muunna prosentti (0-100) desimaaliluvuksi (0.0-1.0)
        probability = current_user.distractor_probability / 100.0
        if random.random() < probability:
            distractor = random.choice(DISTRACTORS)
            app.logger.info(f"Näytetään häiriötekijä käyttäjälle {current_user.id} todennäköisyydellä {probability*100}%")

    return jsonify({'question': question_data, 'distractor': distractor})


@app.route("/api/recommendations")
@login_required
@limiter.limit("30 per minute")
def get_recommendations_api():
    return jsonify(stats_manager.get_recommendations(current_user.id))



#==============================================================================
# --- SIVUJEN REITIT ---
#==============================================================================

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
    # Hae kaikki käyttäjän tilastot kerralla
    analytics = stats_manager.get_learning_analytics(current_user.id)
    
    # Etsi valmentajan valinta (heikoin kategoria)
    coach_pick = None
    weak_categories = [
        cat for cat in analytics.get('categories', []) 
        if cat.get('success_rate') is not None and cat.get('attempts', 0) >= 5
    ]
    if weak_categories:
        coach_pick = min(weak_categories, key=lambda x: x['success_rate'])

    # Etsi vahvin kategoria
    strength_pick = None
    strong_categories = [
        cat for cat in analytics.get('categories', []) 
        if cat.get('success_rate') is not None and cat.get('attempts', 0) >= 10
    ]
    if strong_categories:
        strength_pick = max(strong_categories, key=lambda x: x['success_rate'])

    # KYSYMYSTEN HAKU MISTAKES KORJATTU
    try:
        false_val = False if db_manager.is_postgres else 0
        result = execute_query("""
            SELECT COUNT(*) as count 
            FROM user_question_progress
            WHERE user_id = ? 
              AND times_correct < times_shown 
              AND (mistake_acknowledged IS NULL OR mistake_acknowledged = ?)
        """, (current_user.id, false_val), fetch='one')
        mistake_count = result['count'] if result else 0
    except Exception as e:
        app.logger.error(f"Virhe kehityskohteiden määrän haussa: {e}")
        mistake_count = 0

    # Vanhat toiminnot säilyvät ennallaan
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
    # Välitetään constants.py:n DISTRACTORS-lista templatelle
    return render_template("practice.html", category="Kaikki kategoriat", constants={'DISTRACTORS': DISTRACTORS})

@app.route("/practice/<category>")
@login_required
def practice_category_route(category):
    # Välitetään constants.py:n DISTRACTORS-lista templatelle
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

# TÄMÄ KORVAA VANHAN simulation_routen

@app.route('/simulation')
@login_required
def simulation_route():
    """Renderöi koesimulaatiosivun session-pohjaisella mallilla."""
    has_existing_session = 'simulation' in session and session['simulation'].get('user_id') == current_user.id
    
    # ============================================
    # UUSI KOE
    # ============================================
    if request.args.get('new') == 'true':
        if has_existing_session:
            session.pop('simulation', None)
        
        # Hae satunnaiset kysymykset
        question_ids = db_manager.get_random_question_ids(50)
        
        if not question_ids or len(question_ids) < 50:
            flash(f"Simulaation luonti epäonnistui: tietokannassa ei ole tarpeeksi kysymyksiä (vaaditaan 50, löytyi {len(question_ids)}).", "danger")
            return redirect(url_for('dashboard_route'))

        # ✅ Luo uusi sessio
        session['simulation'] = {
            'user_id': current_user.id,
            'question_ids': question_ids,
            'answers': [None] * len(question_ids),
            'current_index': 0,
            'start_time': datetime.now(timezone.utc).isoformat(),
            'time_remaining': 3600  # ✅ Tallenna alkuperäinen aika
        }
        session.modified = True
        app.logger.info(f"✅ Uusi simulaatio luotu: {len(question_ids)} kysymystä, 60 min")
        return redirect(url_for('simulation_route', resume='true'))

    # ============================================
    # JATKA KOETTA
    # ============================================
    session_info = {}
    
    if has_existing_session:
        sim = session['simulation']
        
        if 'time_remaining' in sim and sim['time_remaining'] is not None:
            time_remaining = max(0, int(sim['time_remaining']))
        else:
            # ⚠️ UUSI: Jos ei ole tallennettua aikaa, laske oikein
            try:
                start_time = datetime.fromisoformat(sim.get('start_time'))
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                
                elapsed_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
                time_remaining = max(0, 3600 - int(elapsed_seconds))
            except Exception as e:
                app.logger.error(f"❌ Time calculation error: {e}")
                time_remaining = 3600

        # ✅ UUSI: Tallenna time_remaining AINA kun ladataan sessio
        sim['time_remaining'] = time_remaining
        session.modified = True
        
        # Rakenna session_info
        session_info = {
            'current_index': sim.get('current_index', 0) + 1,
            'total': len(sim.get('question_ids', [])),
            'answered': len([a for a in sim.get('answers', []) if a is not None]),
            'time_remaining_minutes': int(time_remaining // 60)
        }
        
        app.logger.info(f"📊 Sessio ladattu: Kysymys {session_info['current_index']}/{session_info['total']}, "
                       f"Vastattu: {session_info['answered']}, Aikaa: {session_info['time_remaining_minutes']} min")
    
    # ============================================
    # RENDERÖI TEMPLATE
    # ============================================
    if request.args.get('resume') == 'true' and has_existing_session:
        app.logger.info(f"▶️ Jatketaan simulaatiota")
        return render_template('simulation.html', 
                              session_data=session['simulation'], 
                              has_existing_session=True,
                              session_info=session_info)

    return render_template('simulation.html', 
                          session_data=session.get('simulation', {}), 
                          has_existing_session=has_existing_session,
                          session_info=session_info)

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
            user_data = execute_query("SELECT password FROM users WHERE id = ?", (current_user.id,), fetch='one')
            
            if not user_data or not bcrypt.check_password_hash(user_data['password'], current_password):
                flash('Nykyinen salasana on väärä.', 'danger')
                return redirect(url_for('settings_route'))
        except Exception as e:
            app.logger.error(f"Virhe salasanan tarkistuksessa: {e}")
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

#==============================================================================
# --- KIRJAUTUMISEN REITIT ---
#==============================================================================

@app.route("/login", methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login_route():
    """Kirjautumissivu"""
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
                # KORJATTU OSA: Luodaan User-olio KAIKILLA tarvittavilla tiedoilla
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
                app.logger.info(f"User {username} logged in successfully.")
                
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
        
        # ... (tähän väliin jäävät kaikki aiemmat tarkistukset, kuten salasanan pituus jne.) ...
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
                # KORJATTU OSA: Tarkempi virheilmoitus käyttäjälle
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

#==============================================================================
# --- SALASANAN PALAUTUS REITIT ---
#==============================================================================

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
    """Salasanan resetointi tokenilla."""
    try:
        email = verify_reset_token(token)
    except (SignatureExpired, BadSignature):
        flash('Palautuslinkki on vanhentunut tai virheellinen.', 'danger')
        return redirect(url_for('forgot_password_route'))

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

#==============================================================================
# --- YLLÄPITÄJÄN REITIT ---
#==============================================================================

@app.route("/admin/bulk_delete_duplicates", methods=['POST'])
@admin_required
def admin_bulk_delete_duplicates_route():
    """Poistaa useita duplikaattikysymyksiä kerralla."""
    
    question_ids_str = request.form.get('question_ids', '')
    
    if not question_ids_str:
        flash('⚠️ Ei kysymyksiä poistettavaksi.', 'warning')
        return redirect(url_for('admin_find_duplicates_route'))
    
    try:
        # Parsitaan ID:t
        question_ids = [int(qid.strip()) for qid in question_ids_str.split(',') if qid.strip()]
        
        if not question_ids:
            flash('⚠️ Ei kelvollisia kysymys-ID:itä.', 'warning')
            return redirect(url_for('admin_find_duplicates_route'))
        
        # Poistetaan kysymykset
        deleted_count = 0
        failed_count = 0
        
        for question_id in question_ids:
            success, error = db_manager.delete_question(question_id)
            if success:
                deleted_count += 1
            else:
                failed_count += 1
                app.logger.error(f"Failed to delete question {question_id}: {error}")
        
        # Näytä tulokset
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
            categories_for_template = db_manager.get_categories()
            return render_template("admin_add_question.html", categories=categories_for_template)

        if correct_answer_text not in options:
            flash('Oikea vastaus ei löydy vaihtoehdoista!', 'danger')
            categories_for_template = db_manager.get_categories()
            return render_template("admin_add_question.html", categories=categories_for_template)
        
        # UUSI: Tarkista duplikaatti
        is_duplicate, existing = db_manager.check_question_duplicate(question_text)
        
        if is_duplicate:
            flash(
                f'⚠️ Vastaava kysymys on jo kannassa!\n'
                f'ID: {existing["id"]} | Kategoria: {existing["category"]} | '
                f'Kysymys: "{existing["question"][:100]}..."',
                'warning'
            )
            categories_for_template = db_manager.get_categories()
            return render_template("admin_add_question.html", categories=categories_for_template)
            
        random.shuffle(options)
        correct = options.index(correct_answer_text)

        try:
            question_normalized = db_manager.normalize_question(question_text)
            execute_query('''
                INSERT INTO questions (question, question_normalized, options, correct, explanation, category, difficulty, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (question_text, question_normalized, json.dumps(options), correct, explanation, category, difficulty, datetime.now()), fetch='none')
            
            flash('Kysymys lisätty onnistuneesti!', 'success')
            app.logger.info(f"Admin {current_user.username} added new question in category {category}")
            return redirect(url_for('admin_route'))
        except Exception as e:
            flash(f'Virhe kysymyksen lisäämisessä: {e}', 'danger')
            app.logger.error(f"Question add error: {e}")

    try:
        categories = db_manager.get_categories()
    except Exception as e:
        app.logger.error(f"Could not fetch categories for add_question page: {e}")
        categories = ['laskut', 'turvallisuus', 'annosjakelu']

    return render_template("add_question.html", categories=categories)

@app.route("/admin/questions")
@admin_required
def admin_questions_route():
    """Näyttää kaikki kysymykset ylläpitäjälle."""
    try:
        # Hae kaikki kysymykset tietokannasta
        questions = db_manager._execute(
            """
            SELECT id, question, category, difficulty, status, created_at,
                   validated_by, validated_at, validation_comment
            FROM questions
            ORDER BY category, id
            """,
            fetch='all'
        )

        # Muunna options JSON-stringistä listaksi, jos tarpeen näyttää ne
        questions_list = []
        if questions:
            for q in questions:
                q_dict = dict(q)
                try:
                    # Käytä olemassa olevaa funktiota optionsin hakemiseen, jos tarvitaan
                    question_data = db_manager.get_single_question_for_edit(q['id'])
                    q_dict['options'] = json.loads(question_data['options']) if question_data and question_data['options'] else []
                except (json.JSONDecodeError, TypeError) as e:
                    app.logger.warning(f"Error parsing options for question {q['id']}: {e}")
                    q_dict['options'] = []
                questions_list.append(q_dict)

        return render_template(
            "admin_questions.html",
            questions=questions_list,
            question_count=len(questions_list)
        )
    except Exception as e:
        flash(f'Virhe kysymysten haussa: {str(e)}', 'danger')
        app.logger.error(f"Admin questions fetch error: {e}")
        return redirect(url_for('admin_route'))

# Tämä on korjattu versio admin_bulk_upload_route-funktiosta
# Lisää app.py tiedostoon rivi 1661 alkaen (korvaa vanha funktio)

@app.route("/admin/bulk_upload", methods=['POST'])
@admin_required
def admin_bulk_upload_route():
    """
    Bulk upload JSON questions with AJAX support.
    Returns JSON response for AJAX requests, redirects for normal form submissions.
    """
    # Tarkista onko AJAX-pyyntö
    is_ajax = request.headers.get('X-CSRFToken') is not None or \
              'application/json' in request.headers.get('Accept', '')
    
    if 'json_file' not in request.files:
        if is_ajax:
            return jsonify({'success': False, 'error': 'Tiedostoa ei valittu.'}), 400
        flash('Tiedostoa ei valittu.', 'danger')
        return redirect(url_for('admin_route'))
    
    file = request.files['json_file']
    
    if file.filename == '':
        if is_ajax:
            return jsonify({'success': False, 'error': 'Tiedostoa ei valittu.'}), 400
        flash('Tiedostoa ei valittu.', 'danger')
        return redirect(url_for('admin_route'))
    
    if not file.filename.endswith('.json'):
        if is_ajax:
            return jsonify({'success': False, 'error': 'Tiedoston tulee olla JSON-muotoinen (.json).'}), 400
        flash('Tiedoston tulee olla JSON-muotoinen (.json).', 'danger')
        return redirect(url_for('admin_route'))
    
    try:
        content = file.read().decode('utf-8')
        questions_data = json.loads(content)
        
        if not isinstance(questions_data, list):
            if is_ajax:
                return jsonify({'success': False, 'error': 'JSON-tiedoston tulee sisältää lista kysymyksiä.'}), 400
            flash('JSON-tiedoston tulee sisältää lista kysymyksiä.', 'danger')
            return redirect(url_for('admin_route'))
        
        if len(questions_data) == 0:
            if is_ajax:
                return jsonify({'success': False, 'error': 'JSON-tiedosto on tyhjä.'}), 400
            flash('JSON-tiedosto on tyhjä.', 'warning')
            return redirect(url_for('admin_route'))
        
        success, result = db_manager.bulk_add_questions(questions_data)
        
        if success:
            stats = result
            
            # Lokita onnistunut lataus
            app.logger.info(f"Admin {current_user.username} uploaded {stats['added']} questions from JSON")
            
            # Jos AJAX-pyyntö, palauta JSON
            if is_ajax:
                return jsonify({
                    'success': True,
                    'added': stats.get('added', 0),
                    'duplicates': stats.get('duplicates', 0),
                    'skipped': stats.get('skipped', 0),
                    'errors': stats.get('errors', [])
                }), 200
            
            # Muuten flash-viestit ja redirect (vanha tapa)
            if stats['added'] > 0:
                flash(f"✅ Lisättiin {stats['added']} kysymystä onnistuneesti!", 'success')
            if stats['duplicates'] > 0:
                flash(f"🔄 Ohitettiin {stats['duplicates']} duplikaattia", 'info')
            if stats['skipped'] > 0:
                flash(f"⚠️ Ohitettiin {stats['skipped']} kysymystä muiden virheiden vuoksi", 'warning')
            if stats['errors']:
                error_msg = "Virheet:\n" + "\n".join(stats['errors'][:10])
                if len(stats['errors']) > 10:
                    error_msg += f"\n... ja {len(stats['errors']) - 10} muuta"
                flash(error_msg, 'info')
        else:
            if is_ajax:
                return jsonify({'success': False, 'error': f'Virhe kysymysten lataamisessa: {result}'}), 500
            flash(f'Virhe kysymysten lataamisessa: {result}', 'danger')
            app.logger.error(f"Bulk upload error: {result}")
    
    except json.JSONDecodeError as e:
        error_msg = f'Virheellinen JSON-tiedosto: {str(e)}'
        app.logger.error(f"JSON decode error in bulk upload: {e}")
        if is_ajax:
            return jsonify({'success': False, 'error': error_msg}), 400
        flash(error_msg, 'danger')
        
    except Exception as e:
        error_msg = f'Odottamaton virhe: {str(e)}'
        app.logger.error(f"Unexpected error in bulk upload: {e}")
        if is_ajax:
            return jsonify({'success': False, 'error': error_msg}), 500
        flash(error_msg, 'danger')
    
    return redirect(url_for('admin_route'))


@app.route("/admin/find_duplicates", methods=['GET', 'POST'])
@admin_required
def admin_find_duplicates_route():
    """Etsii duplikaatit ja samankaltaiset kysymykset."""
    
    if request.method == 'POST':
        # Hae threshold lomakkeesta (oletuksena 95%)
        similarity_threshold = float(request.form.get('threshold', 95)) / 100
        
        try:
            similar_questions = db_manager.find_similar_questions(similarity_threshold)
            
            if not similar_questions:
                flash(f'✅ Ei löytynyt duplikaatteja tai samankaltaisuus {similarity_threshold*100:.0f}% kysymyksiä!', 'success')
            else:
                flash(f'🔍 Löydettiin {len(similar_questions)} samankaltaista kysymysparia (kynnys: {similarity_threshold*100:.0f}%)', 'info')
            
            return render_template('admin_duplicates.html', 
                                   similar_questions=similar_questions, 
                                   threshold=similarity_threshold*100)
        
        except Exception as e:
            flash(f'Virhe duplikaattien etsinnässä: {str(e)}', 'danger')
            app.logger.error(f"Duplicate search error: {e}")
            return redirect(url_for('admin_route'))
    
    # GET-pyyntö: näytä lomake
    return render_template('admin_duplicates.html', similar_questions=None, threshold=95)


@app.route("/admin/clear_database", methods=['POST'])
@admin_required
def admin_clear_database_route():
    """VAROITUS: Tyhjentää KAIKKI kysymykset tietokannasta!"""
    
    # Vaadi vahvistus lomakkeesta
    confirmation = request.form.get('confirmation', '')
    
    if confirmation != 'TYHJENNA KAIKKI':
        flash('⚠️ Vahvistus epäonnistui. Kirjoita "TYHJENNA KAIKKI" vahvistaaksesi toiminnon.', 'danger')
        return redirect(url_for('admin_route'))
    
    try:
        success, result = db_manager.clear_all_questions()
        
        if success:
            deleted_count = result['deleted_count']
            flash(f'🗑️ Tietokanta tyhjennetty! Poistettiin {deleted_count} kysymystä.', 'warning')
            app.logger.warning(f"Admin {current_user.username} cleared entire database ({deleted_count} questions)")
        else:
            flash(f'Virhe tietokannan tyhjentämisessä: {result}', 'danger')
            app.logger.error(f"Database clear error: {result}")
    
    except Exception as e:
        flash(f'Odottamaton virhe: {str(e)}', 'danger')
        app.logger.error(f"Unexpected error in database clear: {e}")
    
    return redirect(url_for('admin_route'))

@app.route("/admin")
@admin_required
def admin_route():
    """Admin-pääsivu - näyttää yleiskatsauksen ja toiminnot"""
    try:
        # Hae tilastot OIKEILLA NIMILLÄ vanhaa templateä varten
        total_questions_result = execute_query("SELECT COUNT(*) as count FROM questions", fetch='one')
        total_users_result = execute_query("SELECT COUNT(*) as count FROM users", fetch='one')
        total_categories_result = execute_query("SELECT COUNT(DISTINCT category) as count FROM questions", fetch='one')
        total_attempts_result = execute_query("SELECT COUNT(*) as count FROM question_attempts", fetch='one')
        
        question_count = total_questions_result['count'] if total_questions_result else 0
        user_count = total_users_result['count'] if total_users_result else 0
        category_count = total_categories_result['count'] if total_categories_result else 0
        attempt_count = total_attempts_result['count'] if total_attempts_result else 0
        
        # Hae kategoriat listana
        categories = db_manager.get_categories()
        
        return render_template("admin.html",
                             question_count=question_count,
                             user_count=user_count,
                             category_count=category_count,
                             attempt_count=attempt_count,
                             categories=categories)
                             
    except Exception as e:
        flash(f'Virhe admin-sivun lataamisessa: {e}', 'danger')
        app.logger.error(f"Admin page error: {e}")
        import traceback
        traceback.print_exc()

        return redirect(url_for('dashboard_route'))

@app.route("/admin/validation")
@admin_required
def admin_validation_route():
    """Näyttää kysymykset validointia varten - kaksi välilehteä."""
    try:
        # Hae odottavat kysymykset
        pending_questions = db_manager._execute(
            "SELECT * FROM questions WHERE status = ? ORDER BY category, id",
            ('needs_review',),
            fetch='all'
        )

        # Hae validoidut kysymykset
        validated_questions = db_manager._execute("""
            SELECT q.*, u.username as validator_name
            FROM questions q
            LEFT JOIN users u ON q.validated_by = u.id
            WHERE q.status = ?
            ORDER BY q.validated_at DESC
            LIMIT 100
        """, ('validated',), fetch='all')

        # Muunna options JSON-stringistä listaksi
        pending_list = []
        if pending_questions:
            for q in pending_questions:
                q_dict = dict(q)
                try:
                    q_dict['options'] = json.loads(q_dict['options'])
                except (json.JSONDecodeError, TypeError):
                    q_dict['options'] = []
                pending_list.append(q_dict)

        validated_list = []
        if validated_questions:
            for q in validated_questions:
                q_dict = dict(q)
                try:
                    q_dict['options'] = json.loads(q_dict['options'])
                except (json.JSONDecodeError, TypeError):
                    q_dict['options'] = []
                validated_list.append(q_dict)

        return render_template("admin_validation.html", 
                             pending_questions=pending_list,
                             validated_questions=validated_list,
                             pending_count=len(pending_list),
                             validated_count=len(validated_list))

    except Exception as e:
        flash(f'Virhe kysymysten haussa: {e}', 'danger')
        app.logger.error(f"Validation page error: {e}")
        return redirect(url_for('admin_route'))

@app.route("/admin/validate_question/<int:question_id>", methods=['POST'])
@admin_required
def admin_validate_question_route(question_id):
    """Validoi kysymys (yksittäin tai bulk)."""
    try:
        comment = request.form.get('comment', '').strip()
        
        db_manager._execute("""
            UPDATE questions 
            SET status = ?, 
                validated_by = ?, 
                validated_at = ?,
                validation_comment = ?
            WHERE id = ?
        """, ('validated', current_user.id, datetime.now(), comment if comment else None, question_id), 
        fetch='none')
        
        app.logger.info(f"Admin {current_user.username} validated question {question_id}")
        
        # Jos AJAX-pyyntö, palauta JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Kysymys validoitu!'})
        
        flash(f'Kysymys #{question_id} validoitu!', 'success')
        return redirect(url_for('admin_validation_route'))

    except Exception as e:
        app.logger.error(f"Question validation error for ID {question_id}: {e}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 500
        flash(f'Virhe validoinnissa: {e}', 'danger')
        return redirect(url_for('admin_validation_route'))

@app.route("/admin/bulk_validate", methods=['POST'])
@admin_required
def admin_bulk_validate_route():
    """Validoi useita kysymyksiä kerralla."""
    try:
        question_ids = request.form.get('question_ids', '').strip()
        comment = request.form.get('bulk_comment', '').strip()
        
        if not question_ids:
            flash('Ei kysymyksiä valittuna.', 'warning')
            return redirect(url_for('admin_validation_route'))
        
        # Parsitaan ID:t
        ids = [int(qid.strip()) for qid in question_ids.split(',') if qid.strip()]
        
        if not ids:
            flash('Virheelliset kysymys-ID:t.', 'danger')
            return redirect(url_for('admin_validation_route'))
        
        # Validoidaan kaikki
        validated_count = 0
        for question_id in ids:
            try:
                db_manager._execute("""
                    UPDATE questions 
                    SET status = ?, 
                        validated_by = ?, 
                        validated_at = ?,
                        validation_comment = ?
                    WHERE id = ?
                """, ('validated', current_user.id, datetime.now(), comment if comment else None, question_id), 
                fetch='none')
                validated_count += 1
            except Exception as e:
                app.logger.error(f"Bulk validate error for question {question_id}: {e}")
        
        flash(f'✅ Validoitu {validated_count} kysymystä onnistuneesti!', 'success')
        app.logger.info(f"Admin {current_user.username} bulk validated {validated_count} questions")
        
        return redirect(url_for('admin_validation_route'))
        
    except Exception as e:
        flash(f'Virhe bulk-validoinnissa: {str(e)}', 'danger')
        app.logger.error(f"Bulk validation error: {e}")
        return redirect(url_for('admin_validation_route'))

@app.route("/admin/unvalidate/<int:question_id>", methods=['POST'])
@admin_required
def admin_unvalidate_question_route(question_id):
    """Poista validointi kysymykseltä."""
    try:
        db_manager._execute("""
            UPDATE questions 
            SET status = ?, 
                validated_by = NULL, 
                validated_at = NULL,
                validation_comment = NULL
            WHERE id = ?
        """, ('needs_review', question_id), fetch='none')
        
        flash(f'Validointi poistettu kysymykseltä #{question_id}', 'info')
        app.logger.info(f"Admin {current_user.username} removed validation from question {question_id}")
        
        return redirect(url_for('admin_validation_route'))
        
    except Exception as e:
        flash(f'Virhe validoinnin poistossa: {e}', 'danger')
        app.logger.error(f"Unvalidate error for ID {question_id}: {e}")
        return redirect(url_for('admin_validation_route'))    

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
    
@app.route('/admin/create_test_users', methods=['POST'])
@login_required
@limiter.limit("10 per minute")

def admin_create_test_users_route():
    """Luo useita testikäyttäjiä kerralla."""
    if current_user.role != 'admin':
        flash('Sinulla ei ole oikeuksia tähän toimintoon.', 'danger')
        return redirect(url_for('dashboard_route'))
    
    try:
        user_count = int(request.form.get('user_count', 10))
        expiration_days = int(request.form.get('expiration_days', 30))
        
        # Validoi syötteet
        if user_count < 1 or user_count > 200:
            flash('Käyttäjien määrän tulee olla 1-200 välillä.', 'warning')
            return redirect(url_for('admin_users_route'))
        
        if expiration_days < 1 or expiration_days > 365:
            flash('Voimassaoloajan tulee olla 1-365 päivää.', 'warning')
            return redirect(url_for('admin_users_route'))
        
        # Hae seuraava vapaa testuser-numero
        start_number = db_manager.get_next_test_user_number()
        
        # Laske vanhenemispäivä
        expires_at = datetime.now() + timedelta(days=expiration_days)
        
        # Luo käyttäjät
        created_count = 0
        failed_count = 0
        
        for i in range(user_count):
            username = f"testuser{start_number + i}"
            email = f"test{start_number + i}@example.com"
            # Yksinkertainen salasana testausta varten
            password = "test1234"
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            
            success, error = db_manager.create_user(
                username=username,
                email=email,
                hashed_password=hashed_password,
                expires_at=expires_at
            )
            
            if success:
                created_count += 1
            else:
                failed_count += 1
                app.logger.warning(f"Käyttäjän {username} luonti epäonnistui: {error}")
        
        # Näytä tulos käyttäjälle
        if created_count > 0:
            flash(
                f'✅ Testikäyttäjät luotu onnistuneesti! '
                f'Luotiin {created_count} käyttäjää (nimet olivat ehkä jo varattuja). '
                f'Käyttäjänimet: testuser{start_number} - testuser{start_number + created_count - 1}. '
                f'Salasana kaikille: test1234. '
                f'Voimassaoloaika: {expiration_days} päivää.',
                'success'
            )
        
        if failed_count > 0:
            flash(
                f'⚠️ {failed_count} käyttäjän luonti epäonnistui (nimet olivat ehkä jo varattuja).',
                'warning'
            )
        
        if created_count == 0:
            flash('❌ Ei uusia käyttäjiä luotu. Tämä voi johtua siitä, että kaikki ehdotetut käyttäjänimet olivat jo olemassa.', 'danger')
        
    except ValueError:
        flash('Virheellinen syöte. Tarkista että syötit numeroita.', 'danger')
    except Exception as e:
        app.logger.error(f"Virhe testikäyttäjien luonnissa: {e}")
        flash(f'Virhe testikäyttäjien luonnissa: {str(e)}', 'danger')
    
    return redirect(url_for('admin_users_route'))    

@app.route('/admin/create_single_user', methods=['POST'])
@admin_required
def admin_create_single_user_route():
    """Luo yhden personoidun käyttäjän admin-paneelista."""
    try:
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        role = request.form.get('role', 'user')
        expiration_days = request.form.get('expiration_days')

        if not username or not email:
            flash('Käyttäjänimi ja sähköposti ovat pakollisia.', 'danger')
            return redirect(url_for('admin_users_route'))

        # Luo turvallinen, satunnainen salasana
        password = generate_secure_password(12)
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Käsittele vanhenemispäivä
        expires_at = None
        if expiration_days and expiration_days.isdigit() and int(expiration_days) > 0:
            expires_at = datetime.now() + timedelta(days=int(expiration_days))

        # Luo käyttäjä (rooli on aluksi 'user')
        success, error = db_manager.create_user(
            username=username,
            email=email,
            hashed_password=hashed_password,
            expires_at=expires_at
        )

        if not success:
            flash(f'Käyttäjän luonti epäonnistui: {error}', 'danger')
            return redirect(url_for('admin_users_route'))

        # Jos rooliksi valittiin admin, päivitä se erikseen
        if role == 'admin':
            user = db_manager.get_user_by_username(username)
            if user:
                db_manager.update_user_role(user['id'], 'admin')

        # Näytä onnistumisilmoitus, jossa on luotu salasana
        flash(f"""
            Käyttäjä '{username}' luotu onnistuneesti!
            <br><strong>Salasana:</strong> <code>{password}</code>
            <button
                onclick="copyPasswordFromToast(this)"
                data-password="{password}"
                style="margin-left: 10px; padding: 2px 8px; border-radius: 5px; border: 1px solid white; background: rgba(255,255,255,0.2); color: white; cursor: pointer;">
                Kopioi
            </button>
        """, 'success')

    except Exception as e:
        app.logger.error(f"Virhe yksittäisen käyttäjän luonnissa: {e}")
        flash(f'Odottamaton virhe käyttäjän luonnissa: {str(e)}', 'danger')
    
    return redirect(url_for('admin_users_route'))

@app.route("/admin/stats")
@admin_required
def admin_stats_route():
    try:
        correct_value = 'true' if db_manager.is_postgres else '1'
        
        general_stats = execute_query(f"""
            SELECT
                COUNT(DISTINCT u.id) as total_users,
                COUNT(qa.id) as total_attempts,
                AVG(CASE WHEN qa.correct = {correct_value} THEN 100.0 ELSE 0.0 END) as avg_success_rate
            FROM users u
            LEFT JOIN question_attempts qa ON u.id = qa.user_id
        """, fetch='one')
        
        category_stats = execute_query(f"""
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
    """Poistaa kysymyksen."""
    print(f"DEBUG: Delete route called with question_id={question_id}")
    app.logger.info(f"DELETE ROUTE REACHED: question_id={question_id}")
    
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
    """Poistaa käyttäjän ja kaikki hänen tietonsa."""
    if user_id == 1: # Suojaus pääkäyttäjän poistoa vastaan
        flash('Pääkäyttäjää ei voi poistaa.', 'danger')
        return redirect(url_for('admin_users_route'))

    success, error = db_manager.delete_user(user_id)
    
    if success:
        flash(f'Käyttäjä #{user_id} ja kaikki hänen tietonsa on poistettu onnistuneesti.', 'success')
        app.logger.info(f"Admin {current_user.username} deleted user {user_id}")
    else:
        flash(f'Virhe käyttäjän poistossa: {error}', 'danger')
        app.logger.error(f"User delete error for ID {user_id}: {error}")
    
    return redirect(url_for('admin_users_route'))

@app.route("/admin/export_questions_document", methods=['GET', 'POST'])
@admin_required
def admin_export_questions_document_route():
    """Vie kysymykset PDF- tai Word-dokumenttiin ammattimaisessa muodossa."""
    
    if request.method == 'POST':
        export_format = request.form.get('format', 'pdf')
        include_answers = request.form.get('include_answers') == 'on'
        sort_by = request.form.get('sort_by', 'id')
        check_duplicates = request.form.get('check_duplicates') == 'on'
        selected_categories = request.form.getlist('categories')
        selected_difficulties = request.form.getlist('difficulties')
        
        try:
            # Rakenna kysely suodattimilla
            query = "SELECT * FROM questions WHERE 1=1"
            params = []
            
            if selected_categories:
                placeholders = ','.join('?' * len(selected_categories))
                query += f" AND category IN ({placeholders})"
                params.extend(selected_categories)
            
            if selected_difficulties:
                placeholders = ','.join('?' * len(selected_difficulties))
                query += f" AND difficulty IN ({placeholders})"
                params.extend(selected_difficulties)
            
            # Järjestys
            sort_mapping = {
                'id': 'id ASC',
                'id_desc': 'id DESC',
                'category': 'category ASC, id ASC',
                'difficulty': 'CASE difficulty WHEN "helppo" THEN 1 WHEN "keskivaikea" THEN 2 WHEN "vaikea" THEN 3 END, id ASC',
                'alphabetical': 'question ASC'
            }
            query += f" ORDER BY {sort_mapping.get(sort_by, 'id ASC')}"
            
            questions = execute_query(query, tuple(params), fetch='all')
                    
            if not questions:
                flash('Ei kysymyksiä vietäväksi valituilla suodattimilla.', 'warning')
                return redirect(url_for('admin_export_questions_document_route'))
            
            # Tarkista duplikaatit jos pyydetty
            duplicate_info = None
            if check_duplicates:
                similar = db_manager.find_similar_questions(0.95)
                if similar:
                    duplicate_info = f"⚠️ Löydettiin {len(similar)} mahdollista duplikaattia!"
            
            # Muunna kysymykset listaksi
            questions_list = []
            for q in questions:
                questions_list.append({
                    'id': q['id'],
                    'question': q['question'],
                    'options': json.loads(q['options']),
                    'correct': q['correct'],
                    'explanation': q['explanation'],
                    'category': q['category'],
                    'difficulty': q['difficulty']
                })
            
            # Luo dokumentti
            if export_format == 'pdf':
                pdf_buffer = create_pdf_document(questions_list, include_answers, duplicate_info)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'LOVe_Kysymykset_{timestamp}.pdf'
                
                from flask import make_response
                response = make_response(pdf_buffer.getvalue())
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = f'attachment; filename={filename}'
                
                app.logger.info(f"Admin {current_user.username} exported {len(questions_list)} questions to PDF")
                return response
            
            else:  # Word
                doc_buffer = create_word_document(questions_list, include_answers, duplicate_info)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f'LOVe_Kysymykset_{timestamp}.docx'
                
                from flask import make_response
                response = make_response(doc_buffer.getvalue())
                response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                response.headers['Content-Disposition'] = f'attachment; filename={filename}'
                
                app.logger.info(f"Admin {current_user.username} exported {len(questions_list)} questions to Word")
                return response
            
        except Exception as e:
            flash(f'Virhe dokumentin luomisessa: {str(e)}', 'danger')
            app.logger.error(f"Document export error: {e}")
            import traceback
            traceback.print_exc()
            return redirect(url_for('admin_export_questions_document_route'))
    
    # GET - Näytä lomake
    try:
        categories = db_manager.get_categories()
        
        total_result = execute_query("SELECT COUNT(*) as count FROM questions", fetch='one')
        total_questions = total_result['count'] if total_result else 0
        
        return render_template('admin_export_document.html', 
                               categories=categories,
                               total_questions=total_questions)
    except Exception as e:
        flash(f'Virhe sivun lataamisessa: {str(e)}', 'danger')
        app.logger.error(f"Export page load error: {e}")
        return redirect(url_for('admin_route'))


def create_pdf_document(questions, include_answers, duplicate_info=None):
    """Luo ammattimaisen PDF-dokumentin kysymyksistä."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                            topMargin=0.75*inch, 
                            bottomMargin=0.75*inch,
                            leftMargin=0.75*inch,
                            rightMargin=0.75*inch)
    
    # Tyylit
    styles = getSampleStyleSheet()
    
    # Otsikkotyyli
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#5A67D8'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    # Alaotsikkotyyli
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#718096'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    # Kysymystyyli
    question_style = ParagraphStyle(
        'Question',
        parent=styles['Normal'],
        fontSize=11,
        fontName='Helvetica-Bold',
        spaceAfter=8,
        textColor=colors.HexColor('#2D3748')
    )
    
    # Vastausvaihtoehtotyyli
    option_style = ParagraphStyle(
        'Option',
        parent=styles['Normal'],
        fontSize=10,
        leftIndent=20,
        spaceAfter=4
    )
    
    # Selitystyyli
    explanation_style = ParagraphStyle(
        'Explanation',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#4A5568'),
        leftIndent=10,
        rightIndent=10,
        spaceAfter=6,
        borderWidth=1,
        borderColor=colors.HexColor('#E2E8F0'),
        borderPadding=8,
        backColor=colors.HexColor('#F7FAFC')
    )
    
    # Metatietotyyli
    meta_style = ParagraphStyle(
        'Meta',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#A0AEC0'),
        spaceAfter=12
    )
    
    # Rakenna dokumentti
    story = []
    
    # Otsikko
    story.append(Paragraph("LOVe Enhanced", title_style))
    story.append(Paragraph("Kysymyspankki", subtitle_style))
    story.append(Paragraph(f"Luotu: {datetime.now().strftime('%d.%m.%Y %H:%M')}", meta_style))
    story.append(Paragraph(f"Kysymyksiä yhteensä: {len(questions)}", meta_style))
    
    if duplicate_info:
        warning_style = ParagraphStyle('Warning', parent=styles['Normal'], fontSize=10, 
                                       textColor=colors.HexColor('#F59E0B'))
        story.append(Paragraph(duplicate_info, warning_style))
    
    story.append(Spacer(1, 0.3*inch))
    
    # Sisällysluettelo
    story.append(Paragraph("Sisällysluettelo", styles['Heading2']))
    
    category_counts = {}
    for q in questions:
        cat = q['category']
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    toc_data = [['Kategoria', 'Kysymyksiä']]
    for cat, count in sorted(category_counts.items()):
        toc_data.append([cat.title(), str(count)])
    
    toc_table = Table(toc_data, colWidths=[4*inch, 1.5*inch])
    toc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5A67D8')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F7FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7FAFC')])
    ]))
    
    story.append(toc_table)
    story.append(PageBreak())
    
    # Kysymykset
    current_category = None
    
    for idx, q in enumerate(questions, 1):
        # Kategorian otsikko
        if q['category'] != current_category:
            current_category = q['category']
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph(f"Kategoria: {current_category.title()}", styles['Heading2']))
            story.append(Spacer(1, 0.1*inch))
        
        # Kysymyksen numero ja teksti
        question_text = f"<b>{idx}.</b> {q['question']}"
        story.append(Paragraph(question_text, question_style))
        
        # Metatiedot
        difficulty_map = {'helppo': 'Helppo', 'keskivaikea': 'Keskivaikea', 'vaikea': 'Vaikea'}
        meta_text = f"Vaikeustaso: {difficulty_map.get(q['difficulty'], q['difficulty'])} | ID: {q['id']}"
        story.append(Paragraph(meta_text, meta_style))
        
        # Vastausvaihtoehdot
        letters = ['A', 'B', 'C', 'D']
        for i, option in enumerate(q['options']):
            if include_answers and i == q['correct']:
                option_text = f"<b>{letters[i]}. {option} ✓</b>"
                option_para = Paragraph(option_text, option_style)
            else:
                option_text = f"{letters[i]}. {option}"
                option_para = Paragraph(option_text, option_style)
            story.append(option_para)
        
        story.append(Spacer(1, 0.1*inch))
        
        # Selitys (jos vastaukset sisällytetään)
        if include_answers:
            correct_answer = letters[q['correct']]
            explanation_text = f"<b>Oikea vastaus: {correct_answer}</b><br/>{q['explanation']}"
            story.append(Paragraph(explanation_text, explanation_style))
        
        story.append(Spacer(1, 0.15*inch))
        
        # Sivunvaihto joka 5. kysymyksen jälkeen (vain jos ei ole viimeinen)
        if idx % 5 == 0 and idx < len(questions):
            story.append(PageBreak())
    
    # Rakenna PDF
    doc.build(story)
    buffer.seek(0)
    return buffer


def create_word_document(questions, include_answers, duplicate_info=None):
    """Luo ammattimaisen Word-dokumentin kysymyksistä."""
    doc = Document()
    
    # Aseta marginaalit
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)
    
    # Otsikko
    title = doc.add_heading('LOVe Enhanced', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.runs[0]
    title_run.font.color.rgb = RGBColor(90, 103, 216)
    
    subtitle = doc.add_heading('Kysymyspankki', level=2)
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Metatiedot
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta_run = meta.add_run(f'Luotu: {datetime.now().strftime("%d.%m.%Y %H:%M")}\n')
    meta_run.font.size = Pt(10)
    meta_run.font.color.rgb = RGBColor(160, 174, 192)
    
    meta_run2 = meta.add_run(f'Kysymyksiä yhteensä: {len(questions)}')
    meta_run2.font.size = Pt(10)
    meta_run2.font.color.rgb = RGBColor(160, 174, 192)
    
    if duplicate_info:
        warning = doc.add_paragraph(duplicate_info)
        warning_run = warning.runs[0]
        warning_run.font.color.rgb = RGBColor(245, 158, 11)
        warning_run.font.bold = True
    
    doc.add_paragraph()  # Tyhjä rivi
    
    # Sisällysluettelo
    doc.add_heading('Sisällysluettelo', level=1)
    
    category_counts = {}
    for q in questions:
        cat = q['category']
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    # Luo taulukko sisällysluettelosta
    table = doc.add_table(rows=1, cols=2)
    table.style = 'Light Grid Accent 1'
    
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Kategoria'
    hdr_cells[1].text = 'Kysymyksiä'
    
    for cat, count in sorted(category_counts.items()):
        row_cells = table.add_row().cells
        row_cells[0].text = cat.title()
        row_cells[1].text = str(count)
    
    doc.add_page_break()
    
    # Kysymykset
    current_category = None
    letters = ['A', 'B', 'C', 'D']
    
    for idx, q in enumerate(questions, 1):
        # Kategorian otsikko
        if q['category'] != current_category:
            current_category = q['category']
            doc.add_paragraph()  # Tyhjä rivi
            cat_heading = doc.add_heading(f'Kategoria: {current_category.title()}', level=1)
            cat_heading.runs[0].font.color.rgb = RGBColor(90, 103, 216)
        
        # Kysymys
        question_para = doc.add_paragraph()
        q_run = question_para.add_run(f'{idx}. ')
        q_run.bold = True
        q_run.font.size = Pt(11)
        
        q_text_run = question_para.add_run(q['question'])
        q_text_run.font.size = Pt(11)
        
        # Metatiedot
        difficulty_map = {'helppo': 'Helppo', 'keskivaikea': 'Keskivaikea', 'vaikea': 'Vaikea'}
        meta_para = doc.add_paragraph()
        meta_para_run = meta_para.add_run(
            f'Vaikeustaso: {difficulty_map.get(q["difficulty"], q["difficulty"])} | ID: {q["id"]}'
        )
        meta_para_run.font.size = Pt(8)
        meta_para_run.font.color.rgb = RGBColor(160, 174, 192)
        
        # Vastausvaihtoehdot
        for i, option in enumerate(q['options']):
            option_para = doc.add_paragraph(style='List Bullet')
            option_para.paragraph_format.left_indent = Inches(0.25)
            
            if include_answers and i == q['correct']:
                opt_run = option_para.add_run(f'{letters[i]}. {option} ✓')
                opt_run.bold = True
                opt_run.font.color.rgb = RGBColor(72, 187, 120)
            else:
                opt_run = option_para.add_run(f'{letters[i]}. {option}')
            opt_run.font.size = Pt(10)
        
        # Selitys
        if include_answers:
            explanation_para = doc.add_paragraph()
            explanation_para.paragraph_format.left_indent = Inches(0.15)
            explanation_para.paragraph_format.right_indent = Inches(0.15)
            
            exp_header = explanation_para.add_run(f'Oikea vastaus: {letters[q["correct"]]}\n')
            exp_header.bold = True
            exp_header.font.size = Pt(9)
            
            exp_text = explanation_para.add_run(q['explanation'])
            exp_text.font.size = Pt(9)
            exp_text.font.color.rgb = RGBColor(74, 85, 104)
        
        # Erotin
        doc.add_paragraph('_' * 80)
        
        # Sivunvaihto joka 5. kysymyksen jälkeen
        if idx % 5 == 0 and idx < len(questions):
            doc.add_page_break()
    
    # Tallenna muistiin
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer  

@app.route("/admin/merge_categories", methods=['POST'])
@admin_required
def admin_merge_categories_route():
    """Yhdistää kategoriat kuuteen pääkategoriaan."""
    try:
        success, result = db_manager.merge_categories_to_standard()
        
        if success:
            stats = result
            flash(f"✅ Kategoriat yhdistetty onnistuneesti! Päivitettiin {stats['updated']} kysymystä.", 'success')
            
            category_summary = ", ".join([f"{cat}: {count}" for cat, count in stats['categories'].items()])
            flash(f"📊 Lopulliset kategoriat: {category_summary}", 'info')
            
            app.logger.info(f"Admin {current_user.username} merged categories")
        else:
            flash(f'Virhe kategorioiden yhdistämisessä: {result}', 'danger')
            app.logger.error(f"Category merge error: {result}")
    
    except Exception as e:
        flash(f'Odottamaton virhe: {str(e)}', 'danger')
        app.logger.error(f"Unexpected error in category merge: {e}")
    
    return redirect(url_for('admin_route'))

@app.route("/admin/export_questions")
@admin_required
def admin_export_questions_route():
    """Vie kaikki kysymykset JSON-tiedostoon."""
    try:
        questions = execute_query("""
            SELECT id, question, explanation, options, correct, category, difficulty, created_at
            FROM questions
            ORDER BY category, id
        """, fetch='all')
        
        questions_list = []
        for q in questions:
            questions_list.append({
                'id': q['id'],
                'question': q['question'],
                'explanation': q['explanation'],
                'options': json.loads(q['options']),
                'correct': q['correct'],
                'category': q['category'],
                'difficulty': q['difficulty'],
                'created_at': q['created_at'].isoformat() if q['created_at'] else None
            })
        
        json_data = json.dumps(questions_list, ensure_ascii=False, indent=2)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'love_questions_backup_{timestamp}.json'
        
        app.logger.info(f"Admin {current_user.username} exported {len(questions_list)} questions")
        
        from flask import make_response
        response = make_response(json_data)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        flash(f'Virhe kysymysten viennissä: {str(e)}', 'danger')
        app.logger.error(f"Export error: {e}")
        return redirect(url_for('admin_route'))

@app.route('/admin/edit_user_settings/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def edit_user_settings(user_id):
    if request.form.get('confirm') == 'true':
        data = {
            'distractors_enabled': bool(int(request.form.get('distractors_enabled'))),
            'distractor_probability': int(request.form.get('distractor_probability'))
        }
        success, error = db_manager.update_user(user_id, data)
        if success:
            flash('Asetukset päivitetty onnistuneesti!', 'success')
            return redirect(url_for('admin_users_route'))
        flash(f'Virhe päivitettäessä asetuksia: {error}', 'error')
    return redirect(url_for('admin_users_route'))

#==============================================================================
# --- YKSINKERTAISET EXPORT-REITIT (PDF, WORD, JSON) ---
#==============================================================================

@app.route("/admin/export_pdf", methods=['GET'])
@admin_required
def admin_export_pdf_quick():
    """Vie kaikki kysymykset PDF-tiedostoon."""
    try:
        questions = execute_query("""
            SELECT id, question, explanation, options, correct, category, difficulty
            FROM questions
            ORDER BY category, id
        """, fetch='all')
        
        if not questions:
            flash('Ei kysymyksiä vietäväksi.', 'warning')
            return redirect(url_for('admin_route'))
        
        questions_list = []
        for q in questions:
            questions_list.append({
                'id': q['id'],
                'question': q['question'],
                'options': json.loads(q['options']),
                'correct': q['correct'],
                'explanation': q['explanation'],
                'category': q['category'],
                'difficulty': q['difficulty']
            })
        
        pdf_buffer = create_pdf_document(questions_list, include_answers=True, duplicate_info=None)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'LOVe_Kysymykset_{timestamp}.pdf'
        
        app.logger.info(f"Admin {current_user.username} exported {len(questions_list)} questions to PDF")
        
        from flask import make_response
        response = make_response(pdf_buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        flash(f'Virhe PDF-viennissä: {str(e)}', 'danger')
        app.logger.error(f"PDF export error: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('admin_route'))


@app.route("/admin/export_word", methods=['GET'])
@admin_required
def admin_export_word_quick():
    """Vie kaikki kysymykset Word-tiedostoon."""
    try:
        questions = execute_query("""
            SELECT id, question, explanation, options, correct, category, difficulty
            FROM questions
            ORDER BY category, id
        """, fetch='all')
        
        if not questions:
            flash('Ei kysymyksiä vietäväksi.', 'warning')
            return redirect(url_for('admin_route'))
        
        questions_list = []
        for q in questions:
            questions_list.append({
                'id': q['id'],
                'question': q['question'],
                'options': json.loads(q['options']),
                'correct': q['correct'],
                'explanation': q['explanation'],
                'category': q['category'],
                'difficulty': q['difficulty']
            })
        
        doc_buffer = create_word_document(questions_list, include_answers=True, duplicate_info=None)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'LOVe_Kysymykset_{timestamp}.docx'
        
        app.logger.info(f"Admin {current_user.username} exported {len(questions_list)} questions to Word")
        
        from flask import make_response
        response = make_response(doc_buffer.getvalue())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        flash(f'Virhe Word-viennissä: {str(e)}', 'danger')
        app.logger.error(f"Word export error: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('admin_route'))


@app.route("/admin/export_json", methods=['GET'])
@admin_required
def admin_export_json_quick():
    """Vie kaikki kysymykset JSON-tiedostoon."""
    try:
        questions = execute_query("""
            SELECT id, question, explanation, options, correct, category, difficulty
            FROM questions
            ORDER BY category, id
        """, fetch='all')
        
        if not questions:
            flash('Ei kysymyksiä vietäväksi.', 'warning')
            return redirect(url_for('admin_route'))
        
        questions_list = []
        for q in questions:
            questions_list.append({
                'id': q['id'],
                'question': q['question'],
                'options': json.loads(q['options']),
                'correct': q['correct'],
                'explanation': q['explanation'],
                'category': q['category'],
                'difficulty': q['difficulty']
            })
        
        # Luo JSON response
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'LOVe_Kysymykset_{timestamp}.json'
        
        app.logger.info(f"Admin {current_user.username} exported {len(questions_list)} questions to JSON")
        
        from flask import make_response
        response = make_response(json.dumps(questions_list, indent=2, ensure_ascii=False))
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        flash(f'Virhe JSON-viennissä: {str(e)}', 'danger')
        app.logger.error(f"JSON export error: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('admin_route'))
       
#==============================================================================
# --- VIRHEKÄSITTELY ---
#==============================================================================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Internal server error: {error}")
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden_error(error):
    app.logger.warning(f"Forbidden access attempt: {error}")
    return render_template('403.html'), 403

@app.errorhandler(429)
def ratelimit_error(error):
    app.logger.warning(f"Rate limit exceeded: {request.remote_addr}")
    return jsonify({
        'error': 'Liikaa pyyntöjä. Odota hetki ja yritä uudelleen.',
        'retry_after': error.description
    }), 429

#==============================================================================
# --- SOVELLUKSEN KÄYNNISTYS ---
#==============================================================================

@app.route('/init-database-now')
def init_database_now():
    """
    LUO KAIKKI TAULUT PostgreSQL:iin tai SQLite:en.
    KÄYTÄ VAIN KERRAN ENSIMMÄISELLÄ KERRALLA!
    """
    try:
        # Kutsu DatabaseManager:in omaa init_database metodia
        db_manager.init_database()
        
        app.logger.info("Tietokanta alustettu onnistuneesti")
        return "✅ Tietokannan taulut luotu onnistuneesti!<br><br><a href='/emergency-reset-admin'>Seuraavaksi: Luo admin-käyttäjä</a>"
        
    except Exception as e:
        app.logger.error(f"Virhe tietokannan alustuksessa: {e}")
        return f"❌ Virhe taulujen luomisessa: {str(e)}"


@app.route('/emergency-reset-admin')
def emergency_reset_admin():
    """
    VÄLIAIKAINEN: Luo taulut JA resetoi admin-salasana.
    ⚠️ POISTA TÄMÄ ROUTE KUN ADMIN ON LUOTU!
    """
    admin_username = "Jarno"
    admin_email = "tehostettuaoppimista@gmail.com"
    new_password = "TempPass123!"
    
    try:
        # VAIHE 1: Luo kaikki taulut DatabaseManager:in kautta
        app.logger.info("Luodaan tietokantataulut...")
        db_manager.init_database()
        app.logger.info("Taulut luotu onnistuneesti!")
        
        # VAIHE 2: Tarkista onko admin-käyttäjä jo olemassa
        user = db_manager._execute(
            "SELECT * FROM users WHERE username = ?",
            (admin_username,),
            fetch='one'
        )
        
        # Hashaa salasana
        hashed_pw = bcrypt.generate_password_hash(new_password).decode('utf-8')
        
        if user:
            # Admin löytyi - päivitä salasana
            db_manager._execute(
                "UPDATE users SET password = ? WHERE username = ?",
                (hashed_pw, admin_username),
                fetch='none'
            )
            
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Admin Päivitetty</title>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}
                    .success {{ background: #D4EDDA; border: 1px solid #C3E6CB; padding: 20px; border-radius: 5px; }}
                    .credential {{ background: #F8F9FA; padding: 10px; margin: 10px 0; border-left: 4px solid #5A67D8; }}
                    .btn {{ background: #5A67D8; color: white; padding: 12px 24px; text-decoration: none; 
                            border-radius: 5px; display: inline-block; margin-top: 20px; }}
                </style>
            </head>
            <body>
                <div class="success">
                    <h2>✅ TIETOKANTA ALUSTETTU!</h2>
                    <p>✅ Admin-käyttäjän '{admin_username}' salasana päivitetty!</p>
                    
                    <h3>📊 Luodut taulut:</h3>
                    <ul>
                        <li>users</li>
                        <li>questions</li>
                        <li>distractor_attempts</li>
                        <li>user_question_progress</li>
                        <li>question_attempts</li>
                        <li>user_achievements</li>
                        <li>active_sessions</li>
                        <li>study_sessions</li>
                    </ul>
                    
                    <h3>🔐 Kirjautumistiedot:</h3>
                    <div class="credential">
                        <strong>Käyttäjänimi:</strong> {admin_username}<br>
                        <strong>Salasana:</strong> {new_password}
                    </div>
                    
                    <a href='/login' class="btn">Kirjaudu sisään</a>
                    
                    <hr style="margin: 30px 0;">
                    <p style="color: #856404; background: #FFF3CD; padding: 10px; border-radius: 5px;">
                        ⚠️ <strong>TÄRKEÄÄ:</strong> Poista /emergency-reset-admin route 
                        app.py:stä välittömästi kun olet kirjautunut sisään!
                    </p>
                </div>
            </body>
            </html>
            """
        else:
            # Admin ei löytynyt - luo uusi
            success, error = db_manager.create_user(
                username=admin_username,
                email=admin_email,
                hashed_password=hashed_pw,
                expires_at=None  # Admin ei vanhene
            )
            
            if success:
                # Aseta rooli admin:ksi
                db_manager._execute(
                    "UPDATE users SET role = ? WHERE username = ?",
                    ('admin', admin_username),
                    fetch='none'
                )
                
                return f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Admin Luotu</title>
                    <meta charset="UTF-8">
                    <style>
                        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}
                        .success {{ background: #D4EDDA; border: 1px solid #C3E6CB; padding: 20px; border-radius: 5px; }}
                        .credential {{ background: #F8F9FA; padding: 10px; margin: 10px 0; border-left: 4px solid #5A67D8; }}
                        .btn {{ background: #5A67D8; color: white; padding: 12px 24px; text-decoration: none; 
                                border-radius: 5px; display: inline-block; margin-top: 20px; }}
                    </style>
                </head>
                <body>
                    <div class="success">
                        <h2>✅ TIETOKANTA ALUSTETTU!</h2>
                        <p>✅ Uusi admin-käyttäjä '{admin_username}' luotu!</p>
                        
                        <h3>📊 Luodut taulut:</h3>
                        <ul>
                            <li>users</li>
                            <li>questions</li>
                            <li>distractor_attempts</li>
                            <li>user_question_progress</li>
                            <li>question_attempts</li>
                            <li>user_achievements</li>
                            <li>active_sessions</li>
                            <li>study_sessions</li>
                        </ul>
                        
                        <h3>🔐 Kirjautumistiedot:</h3>
                        <div class="credential">
                            <strong>Käyttäjänimi:</strong> {admin_username}<br>
                            <strong>Sähköposti:</strong> {admin_email}<br>
                            <strong>Salasana:</strong> {new_password}
                        </div>
                        
                        <a href='/login' class="btn">Kirjaudu sisään</a>
                        
                        <hr style="margin: 30px 0;">
                        <p style="color: #856404; background: #FFF3CD; padding: 10px; border-radius: 5px;">
                            ⚠️ <strong>TÄRKEÄÄ:</strong> Poista /emergency-reset-admin route 
                            app.py:stä välittömästi kun olet kirjautunut sisään!
                        </p>
                    </div>
                </body>
                </html>
                """
            else:
                return f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Virhe</title>
                    <meta charset="UTF-8">
                    <style>
                        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}
                        .error {{ background: #F8D7DA; border: 1px solid #F5C6CB; padding: 20px; border-radius: 5px; }}
                    </style>
                </head>
                <body>
                    <div class="error">
                        <h2>❌ Virhe käyttäjän luomisessa</h2>
                        <p>{error}</p>
                    </div>
                </body>
                </html>
                """
                
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        app.logger.error(f"Emergency reset error: {error_details}")
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Kriittinen Virhe</title>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
                .error {{ background: #F8D7DA; border: 1px solid #F5C6CB; padding: 20px; border-radius: 5px; }}
                pre {{ background: #F8F9FA; padding: 15px; overflow-x: auto; border-radius: 3px; }}
            </style>
        </head>
        <body>
            <div class="error">
                <h2>❌ Kriittinen virhe</h2>
                <p><strong>Virheviesti:</strong> {str(e)}</p>
                <h3>Tekninen virheraportti:</h3>
                <pre>{error_details}</pre>
            </div>
        </body>
        </html>
        """