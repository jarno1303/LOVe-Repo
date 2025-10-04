from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
import sqlite3
import random
import json
from dataclasses import asdict
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import re
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Omien moduulien importit
from data_access.database_manager import DatabaseManager
from logic.stats_manager import EnhancedStatsManager
from logic.achievement_manager import EnhancedAchievementManager, ENHANCED_ACHIEVEMENTS
from logic.spaced_repetition import SpacedRepetitionManager
from models.models import User
from constants import DISTRACTORS

#==============================================================================
# --- SOVELLUKSEN ALUSTUS ---
#==============================================================================

app = Flask(__name__)

# Vaadi SECRET_KEY ympäristömuuttujana tuotannossa
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    import sys
    if 'pytest' not in sys.modules:
        print("⚠️  VAROITUS: SECRET_KEY ympäristömuuttuja puuttuu!")
        print("⚠️  Käytetään oletusavainta - ÄLÄ käytä tuotannossa!")
    SECRET_KEY = 'kehityksenaikainen-oletusavain-VAIHDA-TÄMÄ'

app.config['SECRET_KEY'] = SECRET_KEY
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

csrf = CSRFProtect(app)

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

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://"
)

db_manager = DatabaseManager()
stats_manager = EnhancedStatsManager(db_manager)
achievement_manager = EnhancedAchievementManager(db_manager)
spaced_repetition_manager = SpacedRepetitionManager(db_manager)
bcrypt = Bcrypt(app)

def init_distractor_table():
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.execute('''
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
    except sqlite3.Error as e:
        app.logger.error(f"Virhe häiriötekijätaulun luomisessa: {e}")

def add_distractor_probability_column():
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            cursor = conn.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'distractor_probability' not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN distractor_probability INTEGER DEFAULT 25")
                conn.commit()
                app.logger.info("Lisätty distractor_probability sarake")
    except sqlite3.Error as e:
        app.logger.error(f"Virhe sarakkeen lisäämisessä: {e}")

init_distractor_table()
add_distractor_probability_column()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_route'
login_manager.login_message = "Kirjaudu sisään nähdäksesi tämän sivun."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            try:
                user_data = conn.execute(
                    "SELECT id, username, email, role, distractors_enabled, distractor_probability FROM users WHERE id = ?",
                    (user_id,)
                ).fetchone()
                
                if user_data:
                    return User(
                        id=user_data['id'],
                        username=user_data['username'],
                        email=user_data['email'],
                        role=user_data['role'],
                        distractors_enabled=bool(user_data['distractors_enabled']),
                        distractor_probability=user_data['distractor_probability'] or 25
                    )
            except sqlite3.OperationalError:
                user_data = conn.execute(
                    "SELECT id, username, email, role FROM users WHERE id = ?",
                    (user_id,)
                ).fetchone()
                
                if user_data:
                    return User(
                        id=user_data['id'],
                        username=user_data['username'],
                        email=user_data['email'],
                        role=user_data['role'],
                        distractors_enabled=False,
                        distractor_probability=25
                    )
    except sqlite3.Error as e:
        app.logger.error(f"Virhe käyttäjän lataamisessa: {e}")
    return None

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash("Pääsy kielletty. Vaatii ylläpitäjän oikeudet.", "danger")
            return redirect(url_for('dashboard_route'))
        return f(*args, **kwargs)
    return decorated_function

#==============================================================================
# --- SALASANAN PALAUTUS ---
#==============================================================================

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
    SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    FROM_EMAIL = os.environ.get('FROM_EMAIL', 'noreply@loveenhanced.fi')
    
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        app.logger.warning(f"SMTP ei konfiguroitu. Salasanan palautuslinkki: {reset_url}")
        print(f"\n{'='*80}")
        print(f"SALASANAN PALAUTUSLINKKI (kopioi selaimeen):")
        print(f"{reset_url}")
        print(f"{'='*80}\n")
        return True
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'LOVe Enhanced - Salasanan palautus'
    msg['From'] = FROM_EMAIL
    msg['To'] = user_email
    
    html = f"""
    <html>
      <head></head>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f7fafc; border-radius: 10px;">
          <h2 style="color: #5A67D8; text-align: center;">LOVe Enhanced</h2>
          <h3>Salasanan palautuspyyntö</h3>
          <p>Hei,</p>
          <p>Saimme pyynnön palauttaa tilisi salasana. Jos et tehnyt tätä pyyntöä, voit jättää tämän viestin huomiotta.</p>
          <p>Palauttaaksesi salasanasi, klikkaa alla olevaa nappia:</p>
          <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}" style="background-color: #5A67D8; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
              Palauta salasana
            </a>
          </div>
          <p>Tai kopioi ja liitä tämä linkki selaimeesi:</p>
          <p style="word-break: break-all; background-color: #e2e8f0; padding: 10px; border-radius: 5px;">
            {reset_url}
          </p>
          <p style="color: #718096; font-size: 12px;">Tämä linkki on voimassa 1 tunnin.</p>
          <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
          <p style="color: #718096; font-size: 12px; text-align: center;">
            © 2024 LOVe Enhanced. Kaikki oikeudet pidätetään.
          </p>
        </div>
      </body>
    </html>
    """
    
    text = f"""
    LOVe Enhanced - Salasanan palautus
    
    Hei,
    
    Saimme pyynnön palauttaa tilisi salasana. Jos et tehnyt tätä pyyntöä, voit jättää tämän viestin huomiotta.
    
    Palauttaaksesi salasanasi, kopioi ja liitä tämä linkki selaimeesi:
    
    {reset_url}
    
    Tämä linkki on voimassa 1 tunnin.
    
    © 2024 LOVe Enhanced
    """
    
    part1 = MIMEText(text, 'plain')
    part2 = MIMEText(html, 'html')
    
    msg.attach(part1)
    msg.attach(part2)
    
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        app.logger.info(f"Salasanan palautuslinkki lähetetty osoitteeseen: {user_email}")
        return True
    except Exception as e:
        app.logger.error(f"Virhe sähköpostin lähetyksessä: {e}")
        return False

#==============================================================================
# --- API-REITIT ---
#==============================================================================

@app.route("/api/incorrect_questions")
@login_required
@limiter.limit("60 per minute")
def get_incorrect_questions_api():
    """Hakee kysymykset joihin käyttäjä on vastannut väärin."""
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            incorrect_questions = conn.execute("""
                SELECT 
                    q.id,
                    q.question,
                    q.category,
                    q.difficulty,
                    q.explanation,
                    p.times_shown,
                    p.times_correct,
                    p.last_shown,
                    ROUND((p.times_correct * 100.0) / p.times_shown, 1) as success_rate
                FROM questions q
                INNER JOIN user_question_progress p ON q.id = p.question_id
                WHERE p.user_id = ?
                    AND p.times_shown > 0
                    AND p.times_correct < p.times_shown
                ORDER BY 
                    (p.times_correct * 1.0 / p.times_shown) ASC,
                    p.last_shown DESC
                LIMIT 50
            """, (current_user.id,)).fetchall()
            
            questions_list = []
            for row in incorrect_questions:
                questions_list.append({
                    'id': row['id'],
                    'question': row['question'],
                    'category': row['category'],
                    'difficulty': row['difficulty'],
                    'explanation': row['explanation'],
                    'times_shown': row['times_shown'],
                    'times_correct': row['times_correct'],
                    'success_rate': row['success_rate'],
                    'last_shown': row['last_shown']
                })
            
            return jsonify({
                'total_count': len(questions_list),
                'questions': questions_list
            })
            
    except Exception as e:
        app.logger.error(f"Virhe väärien vastausten haussa: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/question_progress/<int:question_id>")
@login_required
@limiter.limit("60 per minute")
def get_question_progress_api(question_id):
    """Hakee käyttäjän edistymisen tietyssä kysymyksessä."""
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            progress = conn.execute("""
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
            """, (current_user.id, question_id)).fetchone()
            
            if progress:
                return jsonify({
                    'times_shown': progress['times_shown'],
                    'times_correct': progress['times_correct'],
                    'success_rate': progress['success_rate'],
                    'last_shown': progress['last_shown']
                })
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
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.execute("UPDATE users SET distractors_enabled = ? WHERE id = ?", (is_enabled, current_user.id))
            conn.commit()
        app.logger.info(f"User {current_user.username} toggled distractors: {is_enabled}")
        return jsonify({'success': True, 'distractors_enabled': is_enabled})
    except sqlite3.Error as e:
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
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.execute("UPDATE users SET distractor_probability = ? WHERE id = ?", (probability, current_user.id))
            conn.commit()
        app.logger.info(f"User {current_user.username} updated distractor probability: {probability}%")
        return jsonify({'success': True, 'probability': probability})
    except sqlite3.Error as e:
        app.logger.error(f"Virhe todennäköisyyden päivityksessä: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/questions")
@login_required
@limiter.limit("60 per minute")
def get_questions_api():
    categories_str = request.args.get('category')
    difficulties_str = request.args.get('difficulties')
    limit = request.args.get('limit', type=int)
    
    categories = categories_str.split(',') if categories_str else None
    difficulties = difficulties_str.split(',') if difficulties_str else None
    
    questions = db_manager.get_questions(user_id=current_user.id, categories=categories, difficulties=difficulties, limit=limit)
    
    processed_questions = []
    for q in questions:
        try:
            if hasattr(q, '__dataclass_fields__'):
                if q.options and q.correct < len(q.options):
                    original_correct_text = q.options[q.correct]
                    random.shuffle(q.options)
                    q.correct = q.options.index(original_correct_text)
                processed_questions.append(asdict(q))
            else:
                question_dict = {
                    'id': getattr(q, 'id', 0),
                    'question': getattr(q, 'question', ''),
                    'options': getattr(q, 'options', []),
                    'correct': getattr(q, 'correct', 0),
                    'explanation': getattr(q, 'explanation', ''),
                    'category': getattr(q, 'category', ''),
                    'difficulty': getattr(q, 'difficulty', 1)
                }
                
                if question_dict['options'] and question_dict['correct'] < len(question_dict['options']):
                    original_correct_text = question_dict['options'][question_dict['correct']]
                    random.shuffle(question_dict['options'])
                    question_dict['correct'] = question_dict['options'].index(original_correct_text)
                
                processed_questions.append(question_dict)
        except Exception as e:
            app.logger.error(f"Virhe kysymyksen käsittelyssä: {e}")
            continue
    
    random.shuffle(processed_questions)
    return jsonify({'questions': processed_questions})

@app.route("/api/question_counts")
@login_required
@limiter.limit("60 per minute")
def get_question_counts_api():
    """Hakee kysymysmäärät kategorioittain ja vaikeustasoittain."""
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            category_counts = conn.execute("""
                SELECT category, COUNT(*) as count
                FROM questions
                GROUP BY category
                ORDER BY category
            """).fetchall()
            
            difficulty_counts = conn.execute("""
                SELECT difficulty, COUNT(*) as count
                FROM questions
                GROUP BY difficulty
            """).fetchall()
            
            category_difficulty_counts = conn.execute("""
                SELECT category, difficulty, COUNT(*) as count
                FROM questions
                GROUP BY category, difficulty
            """).fetchall()
            
            total_count = conn.execute("SELECT COUNT(*) as count FROM questions").fetchone()['count']
            
            cat_diff_map = {}
            for row in category_difficulty_counts:
                cat = row['category']
                diff = row['difficulty']
                count = row['count']
                if cat not in cat_diff_map:
                    cat_diff_map[cat] = {}
                cat_diff_map[cat][diff] = count
            
            return jsonify({
                'categories': {row['category']: row['count'] for row in category_counts},
                'difficulties': {row['difficulty']: row['count'] for row in difficulty_counts},
                'category_difficulty_map': cat_diff_map,
                'total': total_count
            })
    except Exception as e:
        app.logger.error(f"Virhe kysymysmäärien haussa: {e}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/check_distractor")
@login_required
@limiter.limit("120 per minute")
def check_distractor_api():
    distractors_enabled = hasattr(current_user, 'distractors_enabled') and current_user.distractors_enabled
    probability = getattr(current_user, 'distractor_probability', 25) / 100.0
    random_value = random.random()
    
    if distractors_enabled and random_value < probability:
        return jsonify({'distractor': random.choice(DISTRACTORS), 'success': True})
    else:
        return jsonify({'distractor': None, 'success': True})

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
        
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.execute('''
                INSERT INTO distractor_attempts
                (user_id, distractor_scenario, user_choice, correct_choice, is_correct, response_time, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (current_user.id, scenario, user_choice, correct_choice, is_correct, response_time, datetime.now()))
            conn.commit()
        
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

@app.route("/api/submit_simulation", methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def submit_simulation_api():
    data = request.get_json()
    answers = data.get('answers')
    questions_ids = data.get('questions')
    
    if not answers or not questions_ids or len(answers) != len(questions_ids):
        return jsonify({'error': 'Invalid data provided'}), 400
    
    correct_answers_count = 0
    detailed_results = []
    
    for i, q_id in enumerate(questions_ids):
        question_obj = db_manager.get_question_by_id(q_id, current_user.id)
        
        if question_obj and answers[i] is not None and answers[i] == question_obj.correct:
            correct_answers_count += 1
        
        detailed_results.append({
            'question': question_obj.question,
            'options': question_obj.options,
            'explanation': question_obj.explanation,
            'user_answer': answers[i],
            'correct_answer': question_obj.correct,
            'is_correct': (answers[i] == question_obj.correct)
        })
    
    percentage = (correct_answers_count / len(questions_ids)) * 100 if questions_ids else 0
    
    app.logger.info(f"User {current_user.username} completed simulation: {correct_answers_count}/{len(questions_ids)} ({percentage:.1f}%)")
    
    return jsonify({
        'score': correct_answers_count,
        'total': len(questions_ids),
        'percentage': percentage,
        'detailed_results': detailed_results
    })

@app.route("/api/simulation/update", methods=['POST'])
@login_required
@limiter.limit("60 per minute")
def update_simulation_api():
    try:
        data = request.get_json()
        active_session = db_manager.get_active_session(current_user.id)

        if not active_session or active_session.get('session_type') != 'simulation':
            return jsonify({'success': False, 'error': 'No active simulation found.'}), 404

        # Päivitetään selaimen lähettämät tiedot
        current_index = data.get('current_index', active_session['current_index'])
        answers = data.get('answers', active_session['answers'])
        time_remaining = data.get('time_remaining', active_session['time_remaining'])

        # Tallennetaan päivitetty tila tietokantaan
        db_manager.save_or_update_session(
            user_id=current_user.id,
            session_type='simulation',
            question_ids=active_session['question_ids'],
            answers=answers,
            current_index=current_index,
            time_remaining=time_remaining
        )
        app.logger.info(f"Päivitettiin simulaation tila käyttäjälle {current_user.username}")
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Virhe simulaation päivityksessä: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route("/api/simulation/delete", methods=['POST'])
@login_required
def delete_active_session_route():
    success, error = db_manager.delete_active_session(current_user.id)
    if success:
        app.logger.info(f"Poistettiin aktiivinen simulaatio käyttäjältä {current_user.id}")
        return jsonify({'success': True})
    else:
        app.logger.error(f"Virhe aktiivisen session poistossa käyttäjälle {current_user.id}: {error}")
        return jsonify({'success': False, 'error': str(error)}), 500    

@app.route("/api/stats")
@login_required
@limiter.limit("60 per minute")
def get_stats_api():
    return jsonify(stats_manager.get_learning_analytics(current_user.id))

@app.route("/api/achievements")
@login_required
@limiter.limit("60 per minute")
def get_achievements_api():
    try:
        unlocked = achievement_manager.get_unlocked_achievements(current_user.id)
        unlocked_ids = {ach.id for ach in unlocked}
        
        all_achievements = []
        for ach_id, ach_obj in ENHANCED_ACHIEVEMENTS.items():
            try:
                if hasattr(ach_obj, '__dataclass_fields__'):
                    ach_data = asdict(ach_obj)
                else:
                    ach_data = {
                        'id': getattr(ach_obj, 'id', ach_id),
                        'name': getattr(ach_obj, 'name', ''),
                        'description': getattr(ach_obj, 'description', ''),
                        'icon': getattr(ach_obj, 'icon', ''),
                        'unlocked': getattr(ach_obj, 'unlocked', False),
                        'unlocked_at': getattr(ach_obj, 'unlocked_at', None)
                    }
                
                ach_data['unlocked'] = ach_id in unlocked_ids
                all_achievements.append(ach_data)
            except Exception as e:
                app.logger.error(f"Virhe saavutuksen {ach_id} käsittelyssä: {e}")
                continue
        
        return jsonify(all_achievements)
    except Exception as e:
        app.logger.error(f"Virhe saavutusten haussa: {e}")
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
        if hasattr(question, '__dataclass_fields__'):
            question_data = asdict(question)
        else:
            question_data = {
                'id': getattr(question, 'id', 0),
                'question': getattr(question, 'question', ''),
                'options': getattr(question, 'options', []),
                'correct': getattr(question, 'correct', 0),
                'explanation': getattr(question, 'explanation', ''),
                'category': getattr(question, 'category', ''),
                'difficulty': getattr(question, 'difficulty', 1)
            }
    except Exception as e:
        app.logger.error(f"Virhe review-kysymyksen käsittelyssä: {e}")
        return jsonify({'question': None, 'distractor': None})
    
    if hasattr(current_user, 'distractors_enabled') and current_user.distractors_enabled and random.random() < 0.3:
        distractor = random.choice(DISTRACTORS)
    
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

    # Hae virheiden määrä
    with sqlite3.connect(db_manager.db_path) as conn:
        mistake_count = conn.execute("""
            SELECT COUNT(DISTINCT question_id) FROM question_attempts 
            WHERE user_id = ? AND correct = 0
        """, (current_user.id,)).fetchone()[0]

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
    return render_template("practice.html", category="Kaikki kategoriat")

@app.route("/practice/<category>")
@login_required
def practice_category_route(category):
    return render_template("practice.html", category=category)

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
    
    # Tarkista onko aktiivista sessiota
    active_session = db_manager.get_active_session(current_user.id)
    has_active = active_session is not None and active_session.get('session_type') == 'simulation'
    
    # Jos pyydetään jatkamaan JA on aktiivinen sessio
    if resume and has_active:
        app.logger.info(f"Jatketaan simulaatiota käyttäjälle {current_user.username}")
        
        try:
            question_ids = active_session['question_ids']
            if isinstance(question_ids, str):
                question_ids = json.loads(question_ids)
            
            answers = active_session['answers']
            if isinstance(answers, str):
                answers = json.loads(answers)
            
            active_session['question_ids'] = question_ids
            active_session['answers'] = answers
            
            if len(answers) != len(question_ids):
                answers = [None] * len(question_ids)
                active_session['answers'] = answers
            
            app.logger.info(f"Session ladattu: index={active_session['current_index']}, "
                          f"time={active_session['time_remaining']}s, "
                          f"answered={len([a for a in answers if a is not None])}/{len(question_ids)}")
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            app.logger.error(f"Virhe session datan parsinnassa: {e}")
            flash("Kesken­eräisen simulaation lataus epäonnistui. Aloita uusi.", "warning")
            return redirect(url_for('dashboard_route'))
        
        questions = [db_manager.get_question_by_id(qid, current_user.id) for qid in question_ids]
        questions = [q for q in questions if q is not None]
        
        if len(questions) != len(question_ids):
            app.logger.error(f"Kysymysten määrä ei täsmää: {len(questions)} vs {len(question_ids)}")
            flash("Virhe kysymysten lataamisessa. Aloita uusi simulaatio.", "danger")
            return redirect(url_for('dashboard_route'))
        
        questions_data = [asdict(q) for q in questions]
        return render_template("simulation.html", 
                             session_data=active_session, 
                             questions_data=questions_data,
                             has_existing_session=False)
    
    # Jos on aktiivinen sessio MUTTA ei pyydetty jatkamaan eikä pakoteta uutta
    elif has_active and not force_new:
        # Näytä aloitussivu valinnan kanssa
        try:
            question_ids = active_session['question_ids']
            if isinstance(question_ids, str):
                question_ids = json.loads(question_ids)
            
            answers = active_session['answers']
            if isinstance(answers, str):
                answers = json.loads(answers)
            
            answered_count = len([a for a in answers if a is not None])
            time_remaining = active_session.get('time_remaining', 3600)
            minutes_left = time_remaining // 60
            
            session_info = {
                'answered': answered_count,
                'total': len(question_ids),
                'time_remaining_minutes': minutes_left,
                'current_index': active_session.get('current_index', 0) + 1
            }
            
            return render_template("simulation.html",
                                 session_data={},
                                 questions_data=[],
                                 has_existing_session=True,
                                 session_info=session_info)
        except Exception as e:
            app.logger.error(f"Virhe session infon parsinnassa: {e}")
            # Jos virhe, poista viallinen sessio ja jatka normaalisti uuteen
            db_manager.delete_active_session(current_user.id)
    
    # Aloita uusi simulaatio (force_new=True TAI ei aktiivista sessiota)
    app.logger.info(f"Aloitetaan uusi simulaatio käyttäjälle {current_user.username}")
    
    if has_active:
        db_manager.delete_active_session(current_user.id)
        app.logger.info(f"Poistettiin vanha sessio ennen uuden aloittamista")
    
    questions = db_manager.get_questions(user_id=current_user.id, limit=50)
    
    if len(questions) < 50:
        flash("Tietokannassa ei ole tarpeeksi kysymyksiä (50) koesimulaation suorittamiseen.", "warning")
        return redirect(url_for('dashboard_route'))
    
    question_ids = [q.id for q in questions]
    questions_data = [asdict(q) for q in questions]

    new_session = {
        "user_id": current_user.id,
        "session_type": "simulation",
        "question_ids": question_ids,
        "answers": [None] * len(questions),
        "current_index": 0,
        "time_remaining": 3600
    }
    
    db_manager.save_or_update_session(
        user_id=current_user.id,
        session_type=new_session["session_type"],
        question_ids=new_session["question_ids"],
        answers=new_session["answers"],
        current_index=new_session["current_index"],
        time_remaining=new_session["time_remaining"]
    )
    
    app.logger.info(f"Uusi simulaatio luotu: {len(questions)} kysymystä")
    
    return render_template("simulation.html", 
                         session_data=new_session, 
                         questions_data=questions_data,
                         has_existing_session=False)

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
        
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            user_data = conn.execute("SELECT password FROM users WHERE id = ?", (current_user.id,)).fetchone()
            
            if not user_data or not bcrypt.check_password_hash(user_data['password'], current_password):
                flash('Nykyinen salasana on väärä.', 'danger')
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
def login_route():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Käyttäjänimi ja salasana ovat pakollisia.', 'danger')
            return render_template("login.html")
        
        if len(username) > 100 or len(password) > 100:
            flash('Virheelliset kirjautumistiedot.', 'danger')
            app.logger.warning(f"Login attempt with oversized credentials")
            return render_template("login.html")
        
        try:
            with sqlite3.connect(db_manager.db_path) as conn:
                conn.row_factory = sqlite3.Row
                user_data = conn.execute(
                    "SELECT id, username, email, password, role, status FROM users WHERE username = ?",
                    (username,)
                ).fetchone()
                
                if not user_data:
                    flash('Virheellinen käyttäjänimi tai salasana.', 'danger')
                    app.logger.warning(f"Failed login attempt for username: {username} (user not found)")
                    return render_template("login.html")
                
                if user_data['status'] != 'active':
                    flash('Käyttäjätilisi on estetty. Ota yhteyttä ylläpitoon.', 'danger')
                    app.logger.warning(f"Blocked user tried to login: {username}")
                    return render_template("login.html")
                
                if bcrypt.check_password_hash(user_data['password'], password):
                    user = User(
                        id=user_data['id'],
                        username=user_data['username'],
                        email=user_data['email'],
                        role=user_data['role']
                    )
                    login_user(user)
                    flash(f'Tervetuloa takaisin, {user.username}!', 'success')
                    app.logger.info(f"User {user.username} logged in successfully")
                    
                    next_page = request.args.get('next')
                    if next_page:
                        return redirect(next_page)
                    return redirect(url_for('dashboard_route'))
                else:
                    flash('Virheellinen käyttäjänimi tai salasana.', 'danger')
                    app.logger.warning(f"Failed login attempt for username: {username} (wrong password)")
        except sqlite3.Error as e:
            flash('Kirjautumisessa tapahtui virhe. Yritä uudelleen.', 'danger')
            app.logger.error(f"Login error: {e}")
    
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
            success, error = db_manager.create_user(username, email, hashed_password)
            
            if success:
                flash('Rekisteröityminen onnistui! Voit nyt kirjautua sisään.', 'success')
                app.logger.info(f"New user registered: {username}")
                return redirect(url_for('login_route'))
            else:
                if 'UNIQUE constraint failed' in str(error):
                    if 'username' in str(error):
                        flash('Käyttäjänimi on jo käytössä.', 'danger')
                    else:
                        flash('Sähköpostiosoite on jo käytössä.', 'danger')
                else:
                    flash(f'Rekisteröitymisessä tapahtui virhe: {error}', 'danger')
                app.logger.warning(f"Registration failed for username {username}: {error}")
        except Exception as e:
            flash('Rekisteröitymisessä tapahtui odottamaton virhe.', 'danger')
            app.logger.error(f"Registration error: {e}")
    
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
        
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            user = conn.execute("SELECT id, username, email FROM users WHERE email = ?", (email,)).fetchone()
        
        if user:
            token = generate_reset_token(email)
            reset_url = url_for('reset_password_route', token=token, _external=True)
            
            if send_reset_email(email, reset_url):
                flash('Salasanan palautuslinkki on lähetetty sähköpostiisi.', 'success')
                app.logger.info(f"Password reset requested for: {email}")
            else:
                flash('Sähköpostin lähetys epäonnistui. Yritä myöhemmin uudelleen.', 'danger')
        else:
            flash('Jos sähköpostiosoite on rekisteröity, saat palautuslinkin sähköpostiisi.', 'info')
            app.logger.warning(f"Password reset requested for non-existent email: {email}")
        
        return redirect(url_for('login_route'))
    
    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=['GET', 'POST'])
def reset_password_route(token):
    email = verify_reset_token(token)
    
    if not email:
        flash('Virheellinen tai vanhentunut palautuslinkki. Pyydä uusi linkki.', 'danger')
        return redirect(url_for('forgot_password_route'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not new_password or not confirm_password:
            flash('Molemmat kentät ovat pakollisia.', 'danger')
            return render_template("reset_password.html", token=token, email=email)
        
        if new_password != confirm_password:
            flash('Salasanat eivät täsmää.', 'danger')
            return render_template("reset_password.html", token=token, email=email)
        
        if len(new_password) < 8:
            flash('Salasanan tulee olla vähintään 8 merkkiä pitkä.', 'danger')
            return render_template("reset_password.html", token=token, email=email)
        
        if not re.search(r'[A-Z]', new_password):
            flash('Salasanan tulee sisältää vähintään yksi iso kirjain.', 'danger')
            return render_template("reset_password.html", token=token, email=email)
        
        if not re.search(r'[a-z]', new_password):
            flash('Salasanan tulee sisältää vähintään yksi pieni kirjain.', 'danger')
            return render_template("reset_password.html", token=token, email=email)
        
        if not re.search(r'[0-9]', new_password):
            flash('Salasanan tulee sisältää vähintään yksi numero.', 'danger')
            return render_template("reset_password.html", token=token, email=email)
        
        try:
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            
            with sqlite3.connect(db_manager.db_path) as conn:
                conn.execute("UPDATE users SET password = ? WHERE email = ?", (hashed_password, email))
                conn.commit()
            
            flash('Salasana vaihdettu onnistuneesti! Voit nyt kirjautua sisään.', 'success')
            app.logger.info(f"Password reset successful for: {email}")
            return redirect(url_for('login_route'))
            
        except Exception as e:
            flash('Salasanan vaihto epäonnistui. Yritä uudelleen.', 'danger')
            app.logger.error(f"Password reset error: {e}")
            return render_template("reset_password.html", token=token, email=email)
    
    return render_template("reset_password.html", token=token, email=email)

#==============================================================================
# --- YLLÄPITÄJÄN REITIT ---
#==============================================================================

@app.route("/admin")
@admin_required
def admin_route():
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            questions = conn.execute("SELECT id, question, category FROM questions ORDER BY id DESC").fetchall()
            return render_template("admin.html", questions=[dict(row) for row in questions])
    except sqlite3.Error as e:
        flash(f'Virhe kysymysten haussa: {e}', 'danger')
        app.logger.error(f"Admin questions fetch error: {e}")
        return render_template("admin.html", questions=[])

@app.route("/admin/users")
@admin_required
def admin_users_route():
    try:
        users = db_manager.get_all_users_for_admin()
        return render_template("admin_users.html", users=users)
    except sqlite3.Error as e:
        flash(f'Virhe käyttäjien haussa: {e}', 'danger')
        app.logger.error(f"Admin users fetch error: {e}")
        return redirect(url_for('admin_route'))

@app.route("/admin/stats")
@admin_required
def admin_stats_route():
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            general_stats = conn.execute('''
                SELECT
                    COUNT(DISTINCT u.id) as total_users,
                    COUNT(qa.id) as total_attempts,
                    AVG(CASE WHEN qa.is_correct = 1 THEN 100.0 ELSE 0.0 END) as avg_success_rate
                FROM users u
                LEFT JOIN question_attempts qa ON u.id = qa.user_id
            ''').fetchone()
            
            category_stats = conn.execute('''
                SELECT
                    q.category,
                    COUNT(qa.id) as attempts,
                    AVG(CASE WHEN qa.is_correct = 1 THEN 100.0 ELSE 0.0 END) as success_rate
                FROM questions q
                LEFT JOIN question_attempts qa ON q.id = qa.question_id
                GROUP BY q.category
                ORDER BY attempts DESC
            ''').fetchall()
            
            return render_template("admin_stats.html",
                                 general_stats=dict(general_stats),
                                 category_stats=[dict(row) for row in category_stats])
    except sqlite3.Error as e:
        flash(f'Virhe tilastojen haussa: {e}', 'danger')
        app.logger.error(f"Admin stats fetch error: {e}")
        return redirect(url_for('admin_route'))

@app.route("/admin/add_question", methods=['GET', 'POST'])
@admin_required
def admin_add_question_route():
    if request.method == 'POST':
        question_text = request.form.get('question')
        explanation = request.form.get('explanation')
        difficulty = request.form.get('difficulty', 'keskivaikea')
        
        category_choice = request.form.get('category')
        if category_choice == '__add_new__':
            category = request.form.get('new_category', '').strip().lower()
        else:
            category = category_choice
            
        correct_answer_text = request.form.get('option_correct')
        wrong_options = [
            request.form.get('option_wrong_1'),
            request.form.get('option_wrong_2'),
            request.form.get('option_wrong_3')
        ]
        
        options = [correct_answer_text] + wrong_options
        
        if not all([question_text, explanation, category, correct_answer_text] + wrong_options):
            flash('Kaikki kentät ovat pakollisia.', 'danger')
            categories_for_template = db_manager.get_categories()
            return render_template("admin_add_question.html", categories=categories_for_template)
            
        random.shuffle(options)
        correct = options.index(correct_answer_text)

        try:
            with sqlite3.connect(db_manager.db_path) as conn:
                conn.execute('''
                    INSERT INTO questions (question, options, correct, explanation, category, difficulty, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (question_text, json.dumps(options), correct, explanation, category, difficulty, datetime.now()))
                conn.commit()
            
            flash('Kysymys lisätty onnistuneesti!', 'success')
            app.logger.info(f"Admin {current_user.username} added new question in category {category}")
            return redirect(url_for('admin_route'))
        except sqlite3.Error as e:
            flash(f'Virhe kysymyksen lisäämisessä: {e}', 'danger')
            app.logger.error(f"Question add error: {e}")

    try:
        categories = db_manager.get_categories()
    except Exception as e:
        app.logger.error(f"Could not fetch categories for add_question page: {e}")
        categories = ['laskut', 'turvallisuus', 'annosjakelu']

    return render_template("admin_add_question.html", categories=categories)

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

@app.route("/admin/delete_user/<int:user_id>", methods=['POST'])
@admin_required
def admin_delete_user_route(user_id):
    if user_id == 1:
        flash('Pääkäyttäjää ei voi poistaa.', 'danger')
        return redirect(url_for('admin_users_route'))
    
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
        flash('Käyttäjä poistettu onnistuneesti.', 'success')
        app.logger.info(f"Admin {current_user.username} deleted user ID {user_id}")
    except sqlite3.Error as e:
        flash(f'Virhe käyttäjän poistossa: {e}', 'danger')
        app.logger.error(f"User delete error: {e}")
    
    return redirect(url_for('admin_users_route'))

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

#==============================================================================
# --- VIRHEKÄSITTELY ---
#==============================================================================

@app.errorhandler(404)
def not_found_error(error):
    return '''
    <html>
    <head><title>404 - Sivua ei löytynyt</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>404 - Sivua ei löytynyt</h1>
        <p>Hakemaasi sivua ei löytynyt.</p>
        <a href="/" style="color: #007bff;">Palaa etusivulle</a>
    </body>
    </html>
    ''', 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Internal server error: {error}")
    return '''
    <html>
    <head><title>500 - Palvelinvirhe</title></head>
    <body style="font-family: Arial, text-align: center; padding: 50px;">
        <h1>500 - Palvelinvirhe</h1>
        <p>Tapahtui odottamaton virhe.</p>
        <a href="/" style="color: #007bff;">Palaa etusivulle</a>
    </body>
    </html>
    ''', 500

@app.errorhandler(403)
def forbidden_error(error):
    app.logger.warning(f"Forbidden access attempt: {error}")
    return '''
    <html>
    <head><title>403 - Pääsy kielletty</title></head>
    <body style="font-family: Arial, text-align: center; padding: 50px;">
        <h1>403 - Pääsy kielletty</h1>
        <p>Sinulla ei ole oikeuksia tähän sivuun.</p>
        <a href="/" style="color: #007bff;">Palaa etusivulle</a>
    </body>
    </html>
    ''', 403

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

if __name__ == '__main__':
    print("Käynnistetään Flask-sovellus...")
    print(f"Debug-tila: {app.debug}")
    print(f"Tietokanta: {db_manager.db_path}")
    app.run(debug=True, host='127.0.0.1', port=5000)
