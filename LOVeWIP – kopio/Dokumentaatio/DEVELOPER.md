# Kehittäjäohjeet - LOVe Enhanced

Tämä dokumentti on suunnattu kehittäjille, jotka työskentelevät LOVe Enhanced -koodikannan parissa.

## 📋 Sisällysluettelo

- [Arkkitehtuuri](#arkkitehtuuri)
- [Koodin rakenne](#koodin-rakenne)
- [Tietokanta](#tietokanta)
- [Backend-logiikka](#backend-logiikka)
- [Frontend](#frontend)
- [Testaus](#testaus)
- [Best Practices](#best-practices)
- [Deployment](#deployment)

---

## Arkkitehtuuri

### Yleiskuvaus

LOVe Enhanced noudattaa **MVC-arkkitehtuuria** (Model-View-Controller) Flask-frameworkin päälle rakennettuna.

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │
       ↓
┌─────────────────────┐
│  Flask App (app.py) │  ← Controller
│  - Reitit           │
│  - Request handling │
└──────┬──────────────┘
       │
       ↓
┌──────────────────────┐     ┌─────────────────┐
│   Logic Managers     │ ←─→ │  Templates      │ ← View
│ - achievement_mgr    │     │  - Jinja2       │
│ - stats_mgr          │     │  - HTML/CSS/JS  │
│ - spaced_repetition  │     └─────────────────┘
└──────┬───────────────┘
       │
       ↓
┌──────────────────────┐
│  Database Manager    │ ← Model
│  - SQLite/PostgreSQL │
└──────────────────────┘
```

### Teknologiat

**Backend:**
- Flask 3.0 - Web framework
- Flask-Login - Session-hallinta
- WTForms - Lomakevalidointi
- Werkzeug - Salasanojen hajautus

**Database:**
- SQLite (kehitys)
- PostgreSQL (tuotanto)

**Frontend:**
- Bootstrap 5.3 - UI framework
- Vanilla JavaScript - Interaktiivisuus
- Font Awesome 6 - Ikonit

---

## Koodin rakenne

### Hakemistorakenne

```
love-enhanced/
│
├── app.py                      # Pääsovellus ja reitit
├── database_manager.py         # Tietokantaoperaatiot
├── init_db.py                  # Tietokannan alustus
├── requirements.txt            # Python-riippuvuudet
├── .env                        # Ympäristömuuttujat (ei versionhallinnassa)
├── .gitignore
│
├── models/
│   └── models.py              # Datamallit (dataclasses)
│
├── logic/
│   ├── achievement_manager.py  # Saavutusjärjestelmä
│   ├── spaced_repetition.py    # SM-2 algoritmi
│   ├── stats_manager.py        # Tilastot ja analytiikka
│   └── simulation_manager.py   # Simulaatiot
│
├── templates/
│   ├── base.html              # Pohja-template
│   ├── dashboard.html         # Etusivu
│   ├── practice.html          # Harjoittelu
│   ├── review.html            # Kertaus
│   ├── stats.html             # Tilastot
│   ├── simulation.html        # Simulaatio
│   ├── login.html
│   ├── register.html
│   ├── settings.html
│   └── admin/
│       ├── dashboard.html
│       ├── users.html
│       ├── questions.html
│       └── analytics.html
│
├── static/
│   ├── css/
│   │   └── custom.css
│   ├── js/
│   │   ├── practice.js
│   │   ├── stats.js
│   │   └── admin.js
│   └── images/
│       └── logo.png
│
├── data/
│   └── questions.db           # SQLite-tietokanta
│
├── tests/                      # Testit (tulossa)
│   ├── test_database.py
│   ├── test_achievements.py
│   └── test_spaced_repetition.py
│
└── docs/
    ├── API.md
    ├── DATABASE.md
    ├── USER_GUIDE.md
    └── DEPLOYMENT.md
```

---

## Tietokanta

### Tietokantakaavio

```
┌─────────────────┐
│     users       │
├─────────────────┤
│ id (PK)         │
│ username        │──┐
│ email           │  │
│ password_hash   │  │
│ role            │  │
│ status          │  │
│ created_at      │  │
│ distractors...  │  │
└─────────────────┘  │
                     │
    ┌────────────────┘
    │
    ↓
┌──────────────────────────┐       ┌─────────────────┐
│ user_question_progress   │       │   questions     │
├──────────────────────────┤       ├─────────────────┤
│ id (PK)                  │       │ id (PK)         │
│ user_id (FK) ────────────┼───┐   │ question        │
│ question_id (FK) ────────┼───┼──→│ options (JSON)  │
│ times_shown              │   │   │ correct         │
│ times_correct            │   │   │ explanation     │
│ last_shown               │   │   │ category        │
│ ease_factor              │   │   │ difficulty      │
│ interval                 │   │   │ hint_type       │
└──────────────────────────┘   │   └─────────────────┘
                               │
    ┌──────────────────────────┘
    │
    ↓
┌─────────────────────┐
│ question_attempts   │
├─────────────────────┤
│ id (PK)             │
│ user_id (FK)        │
│ question_id (FK)    │
│ correct             │
│ time_taken          │
│ timestamp           │
└─────────────────────┘

┌──────────────────────┐
│ user_achievements    │
├──────────────────────┤
│ id (PK)              │
│ user_id (FK)         │
│ achievement_id       │
│ unlocked_at          │
└──────────────────────┘

┌─────────────────────┐
│ study_sessions      │
├─────────────────────┤
│ id (PK)             │
│ user_id (FK)        │
│ start_time          │
│ end_time            │
│ session_type        │
│ questions_answered  │
│ questions_correct   │
│ categories (JSON)   │
└─────────────────────┘

┌────────────────────────┐
│ simulation_results     │
├────────────────────────┤
│ id (PK)                │
│ user_id (FK)           │
│ score                  │
│ total_questions        │
│ time_taken             │
│ completed_at           │
│ passed                 │
│ answers (JSON)         │
└────────────────────────┘

┌──────────────────────┐
│ distractor_attempts  │
├──────────────────────┤
│ id (PK)              │
│ user_id (FK)         │
│ scenario             │
│ user_choice          │
│ correct_choice       │
│ response_time        │
│ created_at           │
└──────────────────────┘
```

### Tietokannan alustus

```python
# init_db.py
from database_manager import DatabaseManager

db = DatabaseManager('data/questions.db')
db.create_tables()
db.seed_questions()  # Lataa kysymykset
```

### Tietokantaoperaatiot

**DatabaseManager** tarjoaa abstraktoidun rajapinnan tietokantaan:

```python
from database_manager import DatabaseManager

db = DatabaseManager(db_url)

# Käyttäjähallinta
user = db.get_user_by_username('opiskelija')
db.create_user(username, email, password_hash)
db.update_user(user_id, **kwargs)

# Kysymykset
questions = db.get_random_questions(count=20, category='Farmakologia')
question = db.get_question_by_id(question_id)

# Vastaukset
db.record_answer(user_id, question_id, is_correct, time_taken)

# Progress
db.get_user_progress(user_id, question_id)
db.update_user_progress(user_id, question_id, **kwargs)
```

---

## Backend-logiikka

### app.py - Pääsovellus

**Rakenne:**
```python
from flask import Flask, render_template, request, redirect, session
from flask_login import LoginManager, login_required, current_user
from database_manager import DatabaseManager

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Database
db = DatabaseManager(os.getenv('DATABASE_URL'))

# Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

# Managers
from logic.achievement_manager import EnhancedAchievementManager
from logic.stats_manager import EnhancedStatsManager
from logic.spaced_repetition import SpacedRepetitionManager

achievement_mgr = EnhancedAchievementManager(db)
stats_mgr = EnhancedStatsManager(db)
sr_mgr = SpacedRepetitionManager(db)

# Routes
@app.route('/')
def index():
    ...

@app.route('/dashboard')
@login_required
def dashboard():
    ...

# API endpoints
@app.route('/api/random-questions')
@login_required
def api_random_questions():
    ...
```

### Reitit

**Julkiset reitit:**
- `/` - Etusivu
- `/login` - Kirjautuminen
- `/register` - Rekisteröityminen
- `/forgot-password` - Salasanan palautus

**Autentikoidut reitit:**
- `/dashboard` - Käyttäjän etusivu
- `/practice` - Harjoittelu
- `/review` - Älykäs kertaus
- `/stats` - Tilastot
- `/simulation` - Koesimulaatio
- `/settings` - Asetukset

**Admin-reitit:**
- `/admin/dashboard` - Admin-etusivu
- `/admin/users` - Käyttäjähallinta
- `/admin/questions` - Kysymysten hallinta
- `/admin/analytics` - Analytiikka

### Achievement Manager

Saavutusjärjestelmä hallinnoi 16 saavutusta.

```python
from logic.achievement_manager import EnhancedAchievementManager

achievement_mgr = EnhancedAchievementManager(db)

# Tarkista uudet saavutukset
new_achievements = achievement_mgr.check_achievements(
    user_id=current_user.id,
    context={'fast_answer': 4.5}
)

# Hae käyttäjän saavutukset
unlocked = achievement_mgr.get_unlocked_achievements(user_id)
progress = achievement_mgr.get_achievement_progress(user_id)
```

**Saavutustyypit:**
- **Määräpohjaiset:** first_steps, dedicated, expert, master
- **Streak-pohjaiset:** streak_3, streak_7, streak_30
- **Kategoria-pohjaiset:** category_master_farmakologia
- **Simulaatio-pohjaiset:** simulation_complete, simulation_perfect
- **Aika-pohjaiset:** early_bird, night_owl
- **Suorituskyky-pohjaiset:** quick_learner, perfectionist, speed_demon

### Spaced Repetition Manager

SM-2 (SuperMemo 2) -algoritmin toteutus.

```python
from logic.spaced_repetition import SpacedRepetitionManager

sr_mgr = SpacedRepetitionManager(db)

# Hae erääntyvät kertauskysymykset
due_questions = sr_mgr.get_due_questions(user_id, limit=20)

# Laske seuraava kertausaika
interval, ease_factor = sr_mgr.calculate_next_review(
    question=question,
    performance_rating=4  # 0-5, missä 5 = täydellinen muisti
)

# Tallenna kertaus
sr_mgr.record_review(user_id, question_id, interval, ease_factor)
```

**SM-2 Parametrit:**
- `ease_factor` - Helppokerroin (1.3 - 2.5+)
- `interval` - Kertausväli päivinä
- `performance_rating` - Arvio 0-5
  - 0-2: Unohtui, aloita alusta
  - 3: Vaikea muistaa, lyhyt intervalli
  - 4: Helppo muistaa, normaali intervalli
  - 5: Täydellinen, pitkä intervalli

### Stats Manager

Tilastojen ja analytiikan hallinta.

```python
from logic.stats_manager import EnhancedStatsManager

stats_mgr = EnhancedStatsManager(db)

# Aloita sessio
stats_mgr.start_session(user_id, session_type='practice')

# Lopeta sessio
stats_mgr.end_session(user_id, questions_answered=20, questions_correct=17)

# Hae analytiikka
analytics = stats_mgr.get_learning_analytics(user_id)
# Sisältää: general, categories, difficulties, weekly_progress

# Hae suositukset
recommendations = stats_mgr.get_recommendations(user_id)

# Hae streak
streak = stats_mgr.get_user_streak(user_id)
# {'current_streak': 5, 'longest_streak': 12}
```

---

## Frontend

### Template-rakenne

**base.html** - Pohja-template:
```html
<!DOCTYPE html>
<html lang="fi">
<head>
    <meta charset="UTF-8">
    <title>{% block title %}{% endblock %} - LOVe Enhanced</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    {% block extra_css %}{% endblock %}
</head>
<body>
    {% include 'navbar.html' %}
    
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, message in messages %}
                <div class="alert alert-{{ category }}">{{ message }}</div>
            {% endfor %}
        {% endif %}
    {% endwith %}
    
    {% block content %}{% endblock %}
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    {% block extra_js %}{% endblock %}
</body>
</html>
```

### JavaScript-moduulit

**practice.js** - Harjoittelun logiikka:
```javascript
let currentQuestion = null;
let selectedAnswer = null;

async function loadQuestion() {
    const response = await fetch('/api/random-questions?count=1');
    const data = await response.json();
    currentQuestion = data.questions[0];
    displayQuestion(currentQuestion);
}

function selectAnswer(optionIndex) {
    selectedAnswer = optionIndex;
    // Päivitä UI
    checkAnswer();
}

async function checkAnswer() {
    const isCorrect = selectedAnswer === currentQuestion.correct;
    
    const response = await fetch('/api/submit_answer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            question_id: currentQuestion.id,
            selected_option_text: currentQuestion.options[selectedAnswer],
            time_taken: timeElapsed
        })
    });
    
    const result = await response.json();
    showFeedback(result);
}
```

### CSS-tyylit

**custom.css** - Mukautetut tyylit:
```css
:root {
    --primary-color: #5A67D8;
    --primary-dark: #4C51BF;
    --success-color: #48BB78;
    --danger-color: #F56565;
    --warning-color: #ED8936;
}

.question-card {
    border-radius: 15px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    transition: transform 0.2s;
}

.question-card:hover {
    transform: translateY(-5px);
}

.option-btn {
    padding: 1rem;
    border: 2px solid #e2e8f0;
    border-radius: 10px;
    transition: all 0.2s;
}

.option-btn:hover {
    border-color: var(--primary-color);
    background-color: #f7fafc;
}

.option-btn.correct {
    border-color: var(--success-color);
    background-color: #f0fff4;
}

.option-btn.incorrect {
    border-color: var(--danger-color);
    background-color: #fff5f5;
}
```

---

## Testaus

### Yksikkötestit (tulossa)

**test_database.py:**
```python
import pytest
from database_manager import DatabaseManager

@pytest.fixture
def db():
    db = DatabaseManager(':memory:')
    db.create_tables()
    yield db
    db.close()

def test_create_user(db):
    user_id = db.create_user('testuser', 'test@example.com', 'hash')
    assert user_id is not None
    
def test_get_user_by_username(db):
    db.create_user('testuser', 'test@example.com', 'hash')
    user = db.get_user_by_username('testuser')
    assert user.username == 'testuser'
```

**test_achievements.py:**
```python
from logic.achievement_manager import EnhancedAchievementManager

def test_first_steps_achievement(db):
    mgr = EnhancedAchievementManager(db)
    
    # Käyttäjä vastaa ensimmäiseen kysymykseen
    db.record_answer(user_id=1, question_id=1, is_correct=True, time_taken=10)
    
    new_achievements = mgr.check_achievements(user_id=1)
    assert 'first_steps' in new_achievements
```

**test_spaced_repetition.py:**
```python
from logic.spaced_repetition import SpacedRepetitionManager

def test_calculate_next_review():
    mgr = SpacedRepetitionManager(db)
    
    question = Question(
        id=1, ease_factor=2.5, interval=1, times_shown=1, ...
    )
    
    # Hyvä vastaus (4/5)
    interval, ease_factor = mgr.calculate_next_review(question, 4)
    
    assert interval > 1  # Intervalli kasvaa
    assert ease_factor >= 2.5  # Ease kasvaa tai pysyy samana
```

### Integraatiotestit

```python
def test_full_practice_flow(client, db):
    # Kirjaudu
    client.post('/login', data={'username': 'test', 'password': 'test123'})
    
    # Hae kysymys
    response = client.get('/api/random-questions?count=1')
    question = response.json['questions'][0]
    
    # Vastaa kysymykseen
    response = client.post('/api/submit_answer', json={
        'question_id': question['id'],
        'selected_option_text': question['options'][0],
        'time_taken': 15
    })
    
    assert response.json['success'] == True
```

### Manuaalinen testaus

**Testilista:**
- [ ] Rekisteröityminen uutena käyttäjänä
- [ ] Kirjautuminen ja uloskirjautuminen
- [ ] Vastaa 20 kysymykseen
- [ ] Tarkista että tilastot päivittyvät
- [ ] Avaa 3 saavutusta
- [ ] Kokeile kertausjärjestelmää
- [ ] Tee koesimulaatio
- [ ] Admin: Lisää uusi kysymys
- [ ] Admin: Muokkaa käyttäjää

---

## Best Practices

### Koodi-tyyli

**Python (PEP 8):**
```python
# Funktiot: snake_case
def calculate_next_review(question, rating):
    pass

# Luokat: PascalCase
class EnhancedAchievementManager:
    pass

# Vakiot: UPPER_CASE
MAX_QUESTIONS_PER_SESSION = 50

# Docstringit
def get_due_questions(user_id, limit=20):
    """
    Hakee käyttäjän erääntyvät kertauskysymykset.
    
    Args:
        user_id (int): Käyttäjän ID
        limit (int): Maksimimäärä kysymyksiä
        
    Returns:
        list: Lista Question-objekteja
    """
    pass
```

**JavaScript:**
```javascript
// Funktiot: camelCase
function loadQuestion() { }

// Muuttujat: camelCase
let currentQuestion = null;

// Vakiot: UPPER_CASE
const MAX_TIME_LIMIT = 3600;

// JSDoc
/**
 * Lataa satunnaisen kysymyksen
 * @returns {Promise<Object>} Kysymysobjekti
 */
async function loadQuestion() { }
```

### Tietoturva

**Älä koskaan:**
- Tallenna salasanoja selkotekstinä
- Käytä string-konkatenaatiota SQL-kyselyissä
- Luota käyttäjän syötteeseen ilman validointia
- Paljasta tietokantavirheitä käyttäjälle

**Tee aina:**
- Hajuta salasanat bcryptillä
- Käytä parametrisoituja kyselyitä
- Validoi ja sanitoi kaikki syötteet
- Käytä CSRF-suojausta

```python
# HUONO
query = f"SELECT * FROM users WHERE username = '{username}'"

# HYVÄ
query = "SELECT * FROM users WHERE username = ?"
result = db.execute(query, (username,))
```

### Error Handling

```python
try:
    result = db.get_user_by_id(user_id)
    if not result:
        flash('Käyttäjää ei löydy', 'error')
        return redirect(url_for('dashboard'))
except DatabaseError as e:
    logger.error(f"Database error: {e}")
    flash('Virhe tietokannassa', 'error')
    return redirect(url_for('dashboard'))
```

### Logging

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/api/submit_answer', methods=['POST'])
def submit_answer():
    logger.info(f"User {current_user.id} submitting answer for question {question_id}")
    
    try:
        # ... logiikka ...
        logger.info(f"Answer submitted successfully")
    except Exception as e:
        logger.error(f"Error submitting answer: {e}", exc_info=True)
```

---

## Deployment

### Kehitysympäristö

```bash
# .env
FLASK_ENV=development
SECRET_KEY=dev-secret-key
DATABASE_URL=sqlite:///data/questions.db
DEBUG=True
```

### Tuotantoympäristö

```bash
# .env.production
FLASK_ENV=production
SECRET_KEY=<vahva-satunnainen-avain>
DATABASE_URL=postgresql://user:pass@host:5432/loveenhanced
DEBUG=False
HTTPS_ONLY=True
```

**Gunicorn:**
```bash
gunicorn --bind 0.0.0.0:8000 --workers 4 app:app
```

**Nginx (reverse proxy):**
```nginx
server {
    listen 80;
    server_name loveenhanced.fi;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /static {
        alias /var/www/love-enhanced/static;
    }
}
```

---

## Yhteystiedot

**Tech Lead:** dev@loveenhanced.fi  
**Dokumentaatio:** https://docs.loveenhanced.fi  
**Issues:** https://github.com/yourusername/love-enhanced/issues

**Versio:** 1.0.0  
**Viimeksi päivitetty:** 24.10.2025
