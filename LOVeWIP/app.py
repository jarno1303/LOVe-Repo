from flask import Flask, jsonify, render_template, request, redirect, url_for, flash
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import sqlite3
import random
from dataclasses import asdict
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime

# Omien moduulien importit
from data_access.database_manager import DatabaseManager
from logic.stats_manager import EnhancedStatsManager
from logic.achievement_manager import EnhancedAchievementManager, ENHANCED_ACHIEVEMENTS
from logic.spaced_repetition import SpacedRepetitionManager
from models.models import User

#==============================================================================
# --- HÄIRIÖTEKIJÄT ---
#==============================================================================

DISTRACTORS = [
    {
        "scenario": "Potilaan omainen tulee kysymään, voisitko tuoda hänen läheiselleen lasin vettä.",
        "options": ["Lupaan tuoda veden heti lääkkeenjaon jälkeen.", "Keskeytän ja haen veden välittömästi."],
        "correct": 0
    },
    {
        "scenario": "Lääkäri soittaa ja kysyy toisen potilaan vointia.",
        "options": ["Pyydän lääkäriä soittamaan hetken päästä uudelleen.", "Vastaan lääkärin kysymyksiin lääkkeenjaon ohessa."],
        "correct": 0
    },
    {
        "scenario": "Viereisen sängyn potilas valittaa äkillistä, kovaa rintakipua.",
        "options": ["Soitan hoitokelloa ja pyydän kollegan apuun.", "Jätän lääkkeet ja menen välittömästi potilaan luo."],
        "correct": 1
    },
    {
        "scenario": "Lääkehuoneen hälytys alkaa soida.",
        "options": ["Tarkistan tilanteen nopeasti.", "Jatkan lääkkeenjakoa, joku muu varmasti hoitaa."],
        "correct": 0
    },
    {
        "scenario": "Levoton potilas yrittää nousta sängystä, vaikka hänellä on kaatumisriski.",
        "options": ["Puhun potilaalle rauhallisesti ja ohjaan takaisin sänkyyn.", "Huudan apua käytävältä."],
        "correct": 0
    },
    {
        "scenario": "Asiakas pyytää apua WC:hen juuri kun olet jakamassa lääkkeitä toiselle asiakkaalle.",
        "options": ["Pyydän asiakasta odottamaan hetken.", "Keskeytän lääkkeenjaon ja autan WC:hen."],
        "correct": 0
    },
    {
        "scenario": "Kollega tulee kysymään kiireesti: 'Muistatko missä säilytämme insuliinikyniä?'",
        "options": ["Vastaan nopeasti 'Jääkaapissa' ja jatkan.", "Lopetan ja näytän tarkasti missä ne ovat."],
        "correct": 0
    },
    {
        "scenario": "Asiakkaan omainen soittaa ja kysyy: 'Onko äitini ottanut aamulääkkeensä?'",
        "options": ["Pyydän soittamaan puoli tuntia myöhemmin.", "Tarkistan heti kirjauksista ja kerron."],
        "correct": 0
    },
    {
        "scenario": "Huomaat lattialla vesiläikkän käytävässä heti oven vieressä.",
        "options": ["Merkitsen muistiin ja ilmoitan siivoushenkilökunnalle.", "Haen heti moppauksen ja korjaan tilanteen."],
        "correct": 0
    },
    {
        "scenario": "Asiakas alkaa itkemään ja sanoo: 'Minua pelottaa, enkä halua ottaa lääkkeitä.'",
        "options": ["Rauhoittelen ja selitän lääkkeiden tärkeyden.", "Jätän lääkkeet ottamatta ja keskustelen ensin."],
        "correct": 1
    },
    {
        "scenario": "Palovaroitin alkaa piipata keittiöstä (mahdollisesti väärästi).",
        "options": ["Tarkistan tilanteen nopeasti keittiöstä.", "Soitan hätäkeskukseen varmuuden vuoksi."],
        "correct": 0
    },
    {
        "scenario": "Asiakkaiden välille syntyy kiista yhteisessä tilassa.",
        "options": ["Menen rauhoittamaan tilannetta.", "Pyydän kollegan hoitamaan asian."],
        "correct": 0
    },
    {
        "scenario": "Huomaat että toisen asiakkaan verensokeri näyttää olevan huolestuttavan alhainen.",
        "options": ["Keskeytän ja mittaan verensokerin heti.", "Merkitsen muistiin ja tarkistan mittauksen jälkeen."],
        "correct": 0
    },
    {
        "scenario": "Asiakkaan avustaja tulee kysymään: 'Missä vaiheessa lääkkeenjakoa mennään?'",
        "options": ["Kerron nopeasti tilanteen ja jatkan.", "Näytän tarkasti mistä mennään ja mitä on jäljellä."],
        "correct": 0
    },
    {
        "scenario": "Kuulet keittiöstä kovaa kolinaa ja asiakkaan huudahduksen.",
        "options": ["Huudan 'Kaikki kunnossa?' ja kuuntelen vastausta.", "Juoksen heti katsomaan mitä tapahtui."],
        "correct": 1
    },
    {
        "scenario": "Asiakas kysyy: 'Voinko ottaa kaksi särkylääkettä kerralla kun pää särkee niin kovaa?'",
        "options": ["Selitän miksi annostusta ei saa muuttaa.", "Soitan lääkärille kysyäkseni lisäannoksesta."],
        "correct": 0
    },
    {
        "scenario": "Huomaat että asiakkaalla on ihottumaa käsivarressa lääkelaastarien kohdalla.",
        "options": ["Merkitsen havainnon ja jatkan lääkkeenjakoa.", "Tutkin ihon kunnon tarkemmin heti."],
        "correct": 1
    },
    {
        "scenario": "Toimintakeskuksen johtaja tulee kysymään: 'Onko Virtasella ollut oksentelua tänään?'",
        "options": ["Vastaan sen mitä tiedän ja jatkan.", "Lopetan ja tarkistan kirjaukset huolellisesti."],
        "correct": 0
    },
    {
        "scenario": "Asiakas pudottaa lasillisen vettä lattialle ja se särkyi.",
        "options": ["Pyydän asiakasta siirtymään turvallisesti ja siivotan lasit.", "Huudan apua ja pyydän asiakasta pysymään paikallaan."],
        "correct": 0
    },
    {
        "scenario": "Kollega tulee sanomaan: 'Unohdin mainita että Marja tarvitsee antibioottinsa tunnin päästä.'",
        "options": ["Merkitsen muistiini ja huolehdin asiasta.", "Lopetan nykyisen ja hoidan Marjan lääkkeen heti."],
        "correct": 0
    }
]

#==============================================================================
# --- SOVELLUKSEN ALUSTUS ---
#==============================================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'kehityksenaikainen-oletusavain')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

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

# Luo häiriötekijätaulu jos ei ole
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
        print(f"Virhe häiriötekijätaulun luomisessa: {e}")

# Lisää häiriötekijöiden todennäköisyys-sarake
def add_distractor_probability_column():
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            # Tarkista onko sarake jo olemassa
            cursor = conn.execute("PRAGMA table_info(users)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'distractor_probability' not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN distractor_probability INTEGER DEFAULT 25")
                conn.commit()
                print("Lisätty distractor_probability sarake")
    except sqlite3.Error as e:
        print(f"Virhe sarakkeen lisäämisessä: {e}")

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
                # Fallback vanhalle rakenteelle
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
    except sqlite3.Error:
        pass
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
# --- API-REITIT ---
#==============================================================================

@app.route("/api/settings/toggle_distractors", methods=['POST'])
@login_required
def toggle_distractors_api():
    data = request.get_json()
    is_enabled = data.get('enabled', False)
    
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.execute("UPDATE users SET distractors_enabled = ? WHERE id = ?", (is_enabled, current_user.id))
            conn.commit()
        return jsonify({'success': True, 'distractors_enabled': is_enabled})
    except sqlite3.Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/settings/update_distractor_probability", methods=['POST'])
@login_required
def update_distractor_probability_api():
    data = request.get_json()
    probability = data.get('probability', 25)
    
    # Varmista että arvo on 0-100 välillä
    probability = max(0, min(100, int(probability)))
    
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.execute("UPDATE users SET distractor_probability = ? WHERE id = ?", (probability, current_user.id))
            conn.commit()
        return jsonify({'success': True, 'probability': probability})
    except sqlite3.Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/questions")
@login_required
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
            print(f"Virhe kysymyksen käsittelyssä: {e}")
            continue
    
    random.shuffle(processed_questions)
    response_data = {'questions': processed_questions}
    
    # Häiriötekijät tarkistetaan nyt jokaiselle kysymykselle erikseen
    print("DEBUG: Häiriötekijät tarkistetaan per kysymys /api/check_distractor reitissä")
    
    return jsonify(response_data)

@app.route("/api/check_distractor")
@login_required
def check_distractor_api():
    """Tarkistaa pitääkö näyttää häiriötekijä tälle kysymykselle"""
    distractors_enabled = hasattr(current_user, 'distractors_enabled') and current_user.distractors_enabled
    probability = getattr(current_user, 'distractor_probability', 25) / 100.0  # Muunna prosenteiksi
    random_value = random.random()
    
    print(f"DEBUG DISTRACTOR: enabled={distractors_enabled}, probability={probability*100}%, random={random_value}")
    
    if distractors_enabled and random_value < probability:
        print("DEBUG DISTRACTOR: Lähetetään häiriötekijä")
        return jsonify({
            'distractor': random.choice(DISTRACTORS),
            'success': True
        })
    else:
        print("DEBUG DISTRACTOR: Ei häiriötekijää")
        return jsonify({
            'distractor': None,
            'success': True
        })

@app.route("/api/submit_distractor", methods=['POST'])
@login_required
def submit_distractor_api():
    try:
        data = request.get_json()
        print(f"DEBUG submit_distractor: Vastaanotettu data: {data}")
        
        scenario = data.get('scenario')
        user_choice = data.get('user_choice')
        response_time = data.get('response_time', 0)
        
        print(f"DEBUG submit_distractor: scenario={scenario}")
        print(f"DEBUG submit_distractor: user_choice={user_choice}")
        
        if scenario is None:
            print("DEBUG: scenario puuttuu!")
            return jsonify({'error': 'scenario is required'}), 400
        
        if user_choice is None:
            print("DEBUG: user_choice puuttuu!")
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
        
        print(f"DEBUG submit_distractor: Tallennettu onnistuneesti, is_correct={is_correct}")
        
        return jsonify({
            'success': True,
            'is_correct': is_correct,
            'correct_choice': correct_choice
        })
    except sqlite3.Error as e:
        print(f"VIRHE submit_distractor SQL: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        print(f"VIRHE submit_distractor: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/distractor_stats")
@login_required
def get_distractor_stats_api():
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            total_stats = conn.execute('''
                SELECT
                    COUNT(*) as total_attempts,
                    SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct_attempts,
                    AVG(response_time) as avg_response_time
                FROM distractor_attempts
                WHERE user_id = ?
            ''', (current_user.id,)).fetchone()
            
            recent_attempts = conn.execute('''
                SELECT distractor_scenario, is_correct, created_at
                FROM distractor_attempts
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 10
            ''', (current_user.id,)).fetchall()
            
            scenario_stats = conn.execute('''
                SELECT
                    CASE
                        WHEN distractor_scenario LIKE '%potilas%' OR distractor_scenario LIKE '%asiakas%' THEN 'Potilastyö'
                        WHEN distractor_scenario LIKE '%lääkäri%' OR distractor_scenario LIKE '%kollega%' THEN 'Tiimityö'
                        WHEN distractor_scenario LIKE '%hälytys%' OR distractor_scenario LIKE '%kiista%' THEN 'Hätätilanteet'
                        ELSE 'Muut'
                    END as category,
                    COUNT(*) as attempts,
                    ROUND(AVG(CASE WHEN is_correct = 1 THEN 100.0 ELSE 0.0 END), 1) as success_rate
                FROM distractor_attempts
                WHERE user_id = ?
                GROUP BY category
            ''', (current_user.id,)).fetchall()
            
            return jsonify({
                'total_attempts': total_stats['total_attempts'] or 0,
                'correct_attempts': total_stats['correct_attempts'] or 0,
                'success_rate': round((total_stats['correct_attempts'] or 0) / max(total_stats['total_attempts'] or 1, 1) * 100, 1),
                'avg_response_time': round(total_stats['avg_response_time'] or 0, 0),
                'recent_attempts': [dict(row) for row in recent_attempts],
                'category_stats': [dict(row) for row in scenario_stats]
            })
    except sqlite3.Error as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/submit_answer", methods=['POST'])
@login_required
def submit_answer_api():
    data = request.get_json()
    question_id = data.get('question_id')
    selected_option_text = data.get('selected_option_text')
    time_taken = data.get('time_taken', 0)
    
    print(f"DEBUG: Etsitään kysymystä ID:llä {question_id}")
    print(f"DEBUG: Käyttäjä: {current_user.id}")
    
    question = db_manager.get_question_by_id(question_id, current_user.id)
    print(f"DEBUG: Löytyi kysymys: {question}")
    
    if not question:
        print(f"DEBUG: Kysymystä {question_id} ei löytynyt!")
        return jsonify({'error': 'Question not found'}), 404
    
    is_correct = (selected_option_text == question.options[question.correct])
    
    db_manager.update_question_stats(question_id, is_correct, time_taken, current_user.id)
    
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
            print(f"Virhe saavutuksen {ach_id} käsittelyssä: {e}")
            continue
    
    return jsonify({
        'correct': is_correct,
        'correct_answer_index': question.correct,
        'explanation': question.explanation,
        'new_achievements': new_achievements
    })

@app.route("/api/submit_simulation", methods=['POST'])
@login_required
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
    
    return jsonify({
        'score': correct_answers_count,
        'total': len(questions_ids),
        'percentage': percentage,
        'detailed_results': detailed_results
    })

@app.route("/api/stats")
@login_required
def get_stats_api():
    return jsonify(stats_manager.get_learning_analytics(current_user.id))

@app.route("/api/achievements")
@login_required
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
                print(f"Virhe saavutuksen {ach_id} käsittelyssä: {e}")
                continue
        
        return jsonify(all_achievements)
    except Exception as e:
        print(f"Virhe saavutusten haussa: {e}")
        return jsonify([])

@app.route("/api/review-questions")
@login_required
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
        print(f"Virhe review-kysymyksen käsittelyssä: {e}")
        return jsonify({'question': None, 'distractor': None})
    
    if hasattr(current_user, 'distractors_enabled') and current_user.distractors_enabled and random.random() < 0.3:
        distractor = random.choice(DISTRACTORS)
    
    return jsonify({
        'question': question_data,
        'distractor': distractor
    })

@app.route("/api/recommendations")
@login_required
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
    return render_template("dashboard.html", categories=db_manager.get_categories())

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

@app.route("/simulation")
@login_required
def simulation_route():
    return render_template("simulation.html")

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
                flash('Nykyinen salasana on väärin.', 'danger')
                return redirect(url_for('settings_route'))
        
        new_hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        success, error = db_manager.update_user_password(current_user.id, new_hashed_password)
        
        if success:
            flash('Salasana vaihdettu onnistuneesti!', 'success')
        else:
            flash(f'Salasanan vaihdossa tapahtui virhe: {error}', 'danger')
        
        return redirect(url_for('settings_route'))
    
    return render_template("settings.html")

#==============================================================================
# --- KIRJAUTUMISEN REITIT ---
#==============================================================================

@app.route("/login", methods=['GET', 'POST'])
def login_route():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Käyttäjänimi ja salasana ovat pakollisia.', 'danger')
            return render_template("login.html")
        
        try:
            with sqlite3.connect(db_manager.db_path) as conn:
                conn.row_factory = sqlite3.Row
                user_data = conn.execute(
                    "SELECT id, username, email, password, role FROM users WHERE username = ?",
                    (username,)
                ).fetchone()
                
                if user_data and bcrypt.check_password_hash(user_data['password'], password):
                    user = User(
                        id=user_data['id'],
                        username=user_data['username'],
                        email=user_data['email'],
                        role=user_data['role']
                    )
                    login_user(user)
                    flash(f'Tervetuloa takaisin, {user.username}!', 'success')
                    return redirect(url_for('dashboard_route'))
                else:
                    flash('Virheellinen käyttäjänimi tai salasana.', 'danger')
        except sqlite3.Error as e:
            flash('Kirjautumisessa tapahtui virhe. Yritä uudelleen.', 'danger')
            print(f"Login error: {e}")
    
    return render_template("login.html")

@app.route("/register", methods=['GET', 'POST'])
def register_route():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not all([username, email, password, confirm_password]):
            flash('Kaikki kentät ovat pakollisia.', 'danger')
            return render_template("register.html")
        
        if password != confirm_password:
            flash('Salasanat eivät täsmää.', 'danger')
            return render_template("register.html")
        
        if len(password) < 6:
            flash('Salasanan tulee olla vähintään 6 merkkiä pitkä.', 'danger')
            return render_template("register.html")
        
        try:
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            success, error = db_manager.create_user(username, email, hashed_password)
            
            if success:
                flash('Rekisteröityminen onnistui! Voit nyt kirjautua sisään.', 'success')
                return redirect(url_for('login_route'))
            else:
                flash(f'Rekisteröitymisessä tapahtui virhe: {error}', 'danger')
        except Exception as e:
            flash('Rekisteröitymisessä tapahtui odottamaton virhe.', 'danger')
            print(f"Registration error: {e}")
    
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout_route():
    logout_user()
    flash('Olet kirjautunut ulos.', 'info')
    return redirect(url_for('login_route'))

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
        return render_template("admin.html", questions=[])

@app.route("/admin/users")
@admin_required
def admin_users_route():
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            users = conn.execute(
                "SELECT id, username, email, role, created_at FROM users ORDER BY created_at DESC"
            ).fetchall()
            return render_template("admin_users.html", users=[dict(row) for row in users])
    except sqlite3.Error as e:
        flash(f'Virhe käyttäjien haussa: {e}', 'danger')
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
        return redirect(url_for('admin_route'))

@app.route("/admin/add_question", methods=['GET', 'POST'])
@admin_required
def admin_add_question_route():
    if request.method == 'POST':
        question_text = request.form.get('question')
        options = [
            request.form.get('option_1'),
            request.form.get('option_2'),
            request.form.get('option_3'),
            request.form.get('option_4')
        ]
        correct = int(request.form.get('correct', 0))
        explanation = request.form.get('explanation')
        category = request.form.get('category')
        difficulty = int(request.form.get('difficulty', 1))
        
        if not all([question_text, explanation, category]) or not all(options):
            flash('Kaikki kentät ovat pakollisia.', 'danger')
            return render_template("admin_add_question.html")
        
        try:
            with sqlite3.connect(db_manager.db_path) as conn:
                conn.execute('''
                    INSERT INTO questions (question, options, correct, explanation, category, difficulty, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (question_text, str(options), correct, explanation, category, difficulty, datetime.now()))
                conn.commit()
            
            flash('Kysymys lisätty onnistuneesti!', 'success')
            return redirect(url_for('admin_route'))
        except sqlite3.Error as e:
            flash(f'Virhe kysymyksen lisäämisessä: {e}', 'danger')
    
    try:
        categories = db_manager.get_categories()
    except:
        categories = ['farmakologia', 'annosjakelu', 'antibiotit', 'apteekki ja lääkehuolto', 'diabeteslääkkeet']
    
    return render_template("admin_add_question.html", categories=categories)

@app.route("/admin/edit_question/<int:question_id>", methods=['GET', 'POST'])
@admin_required
def admin_edit_question_route(question_id):
    if request.method == 'POST':
        # Toteuta kysymyksen päivitys tässä myöhemmin
        flash('Kysymyksen muokkaus toteutettu!', 'success')
        return redirect(url_for('admin_route'))
    
    # GET - näytä muokkauslomake
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            question = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
            
            if not question:
                flash('Kysymystä ei löytynyt.', 'danger')
                return redirect(url_for('admin_route'))
            
            # Tämä vaatii edit_question.html templaten
            flash('Muokkaussivu ei ole vielä valmis.', 'info')
            return redirect(url_for('admin_route'))
    except sqlite3.Error as e:
        flash(f'Virhe kysymyksen haussa: {e}', 'danger')
        return redirect(url_for('admin_route'))

@app.route("/admin/delete_user/<int:user_id>", methods=['POST'])
@admin_required
def admin_delete_user_route(user_id):
    if user_id == 1:  # Suojaa pääkäyttäjä
        flash('Pääkäyttäjää ei voi poistaa.', 'danger')
        return redirect(url_for('admin_users_route'))
    
    try:
        with sqlite3.connect(db_manager.db_path) as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
        flash('Käyttäjä poistettu onnistuneesti.', 'success')
    except sqlite3.Error as e:
        flash(f'Virhe käyttäjän poistossa: {e}', 'danger')
    
    return redirect(url_for('admin_users_route'))

@app.route("/admin/toggle_user/<int:user_id>", methods=['POST'])
@admin_required
def admin_toggle_user_route(user_id):
    flash('Käyttäjän tilan vaihto ei ole vielä toteutettu.', 'info')
    return redirect(url_for('admin_users_route'))

#==============================================================================
# --- VIRHEENKÄSITTELY ---
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
    return '''
    <html>
    <head><title>500 - Palvelinvirhe</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>500 - Palvelinvirhe</h1>
        <p>Tapahtui odottamaton virhe.</p>
        <a href="/" style="color: #007bff;">Palaa etusivulle</a>
    </body>
    </html>
    ''', 500

@app.errorhandler(403)
def forbidden_error(error):
    return '''
    <html>
    <head><title>403 - Pääsy kielletty</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>403 - Pääsy kielletty</h1>
        <p>Sinulla ei ole oikeuksia tähän sivuun.</p>
        <a href="/" style="color: #007bff;">Palaa etusivulle</a>
    </body>
    </html>
    ''', 403

#==============================================================================
# --- SOVELLUKSEN KÄYNNISTYS ---
#==============================================================================

if __name__ == '__main__':
    print("Käynnistetään Flask-sovellus...")
    print(f"Debug-tila: {app.debug}")
    print(f"Tietokanta: {db_manager.db_path}")
    app.run(debug=True, host='127.0.0.1', port=5000)