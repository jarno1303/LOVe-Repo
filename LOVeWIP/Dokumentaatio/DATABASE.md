# Tietokantadokumentaatio - LOVe Enhanced

Kattava dokumentaatio LOVe Enhanced -sovelluksen tietokantarakenteesta.

## 📋 Sisällysluettelo

- [Yleiskatsaus](#yleiskatsaus)
- [Taulut](#taulut)
- [Relaatiot](#relaatiot)
- [Indeksit](#indeksit)
- [Migraatiot](#migraatiot)

---

## Yleiskatsaus

### Tietokantateknologia

- **Kehitys:** SQLite 3.x
- **Tuotanto:** PostgreSQL 14+

### Tietokannan nimi

- `loveenhanced` (tuotanto)
- `questions.db` (SQLite-tiedosto kehityksessä)

### Tietueiden määrät (arviot)

| Taulu | Tietueet |
|-------|----------|
| users | 100-10,000 |
| questions | 340-500 |
| question_attempts | 10,000-1,000,000 |
| user_question_progress | 34,000-5,000,000 |
| user_achievements | 1,600-160,000 |
| study_sessions | 5,000-500,000 |

---

## Taulut

### users

Käyttäjien perustiedot ja asetukset.

**Sarakkeet:**

| Sarake | Tyyppi | Null | Default | Kuvaus |
|--------|--------|------|---------|---------|
| id | INTEGER | NO | AUTO | Pääavain |
| username | TEXT | NO | - | Käyttäjänimi (unique) |
| email | TEXT | NO | - | Sähköposti (unique) |
| password | TEXT | NO | - | Salasana (bcrypt hash) |
| role | TEXT | NO | 'user' | Rooli: user/teacher/admin |
| status | TEXT | NO | 'active' | Status: active/inactive |
| created_at | TIMESTAMP | NO | NOW() | Luontiaika |
| expires_at | TIMESTAMP | YES | NULL | Vanhenemisaika (NULL = ei vanhene) |
| distractors_enabled | BOOLEAN | NO | FALSE | Häiriötekijät päällä |
| distractor_probability | INTEGER | NO | 25 | Häiriötekijän todennäköisyys (%) |

**Indeksit:**
- PRIMARY KEY (id)
- UNIQUE (username)
- UNIQUE (email)
- INDEX (role)
- INDEX (status)

**Esimerkkitietue:**
```sql
INSERT INTO users (username, email, password, role, distractors_enabled)
VALUES ('opiskelija1', 'opiskelija1@example.com', '$2b$12$hash...', 'user', TRUE);
```

---

### questions

Kysymyspankki.

**Sarakkeet:**

| Sarake | Tyyppi | Null | Default | Kuvaus |
|--------|--------|------|---------|---------|
| id | INTEGER | NO | AUTO | Pääavain |
| question | TEXT | NO | - | Kysymysteksti |
| options | TEXT | NO | - | Vastausvaihtoehdot (JSON) |
| correct | INTEGER | NO | - | Oikean vastauksen indeksi (0-3) |
| explanation | TEXT | NO | - | Selitys |
| category | TEXT | NO | - | Kategoria |
| difficulty | TEXT | NO | - | Vaikeustaso: helppo/keskivaikea/vaikea |
| hint_type | TEXT | YES | NULL | Vihjetyyppi |
| status | TEXT | NO | 'approved' | Status: needs_review/approved |
| created_at | TIMESTAMP | NO | NOW() | Luontiaika |
| validated_by | INTEGER | YES | NULL | Validoijan user_id |
| validated_at | TIMESTAMP | YES | NULL | Validointiaika |
| validation_comment | TEXT | YES | NULL | Validointikommentti |
| question_normalized | TEXT | YES | NULL | Normalisoitu haku varten |

**Indeksit:**
- PRIMARY KEY (id)
- INDEX (category)
- INDEX (difficulty)
- INDEX (status)
- INDEX (question_normalized)

**JSON-rakenne (options):**
```json
["Vaihtoehto A", "Vaihtoehto B", "Vaihtoehto C", "Vaihtoehto D"]
```

**Esimerkkitietue:**
```sql
INSERT INTO questions (question, options, correct, explanation, category, difficulty)
VALUES (
  'Mikä on parasetamolin maksimi vuorokausiannos aikuiselle?',
  '["2g", "3g", "4g", "5g"]',
  2,
  'Parasetamolin maksimi vuorokausiannos aikuiselle on 4 grammaa...',
  'Farmakologia',
  'helppo'
);
```

---

### user_question_progress

Käyttäjäkohtainen edistyminen jokaisessa kysymyksessä. Tämä on Spaced Repetition -järjestelmän ydin.

**Sarakkeet:**

| Sarake | Tyyppi | Null | Default | Kuvaus |
|--------|--------|------|---------|---------|
| id | INTEGER | NO | AUTO | Pääavain |
| user_id | INTEGER | NO | - | Käyttäjä (FK) |
| question_id | INTEGER | NO | - | Kysymys (FK) |
| times_shown | INTEGER | NO | 0 | Montako kertaa näytetty |
| times_correct | INTEGER | NO | 0 | Montako kertaa oikein |
| last_shown | TIMESTAMP | YES | NULL | Viimeksi näytetty |
| ease_factor | REAL | NO | 2.5 | SM-2 ease factor |
| interval | INTEGER | NO | 1 | Kertausväli (päivinä) |

**Indeksit:**
- PRIMARY KEY (id)
- UNIQUE (user_id, question_id)
- INDEX (user_id)
- INDEX (question_id)
- INDEX (last_shown)

**Foreign Keys:**
- user_id → users(id)
- question_id → questions(id)

**SM-2 Algoritmi:**
- `ease_factor`: 1.3 - 2.5+ (mitä suurempi, sitä paremmin muistaa)
- `interval`: 1, 3, 7, 14, 30, ... (päivät seuraavaan kertaukseen)

**Esimerkkitietue:**
```sql
INSERT INTO user_question_progress (user_id, question_id, times_shown, times_correct, last_shown, ease_factor, interval)
VALUES (1, 45, 3, 2, '2025-10-17 14:30:00', 2.3, 7);
```

---

### question_attempts

Käyttäjien vastaushistoria. Jokainen vastaus tallennetaan.

**Sarakkeet:**

| Sarake | Tyyppi | Null | Default | Kuvaus |
|--------|--------|------|---------|---------|
| id | INTEGER | NO | AUTO | Pääavain |
| user_id | INTEGER | NO | - | Käyttäjä (FK) |
| question_id | INTEGER | NO | - | Kysymys (FK) |
| correct | BOOLEAN | NO | - | Oliko vastaus oikein |
| time_taken | INTEGER | NO | - | Vastausaika (sekunteina) |
| timestamp | TIMESTAMP | NO | NOW() | Milloin vastattu |

**Indeksit:**
- PRIMARY KEY (id)
- INDEX (user_id, timestamp)
- INDEX (question_id)
- INDEX (timestamp)

**Foreign Keys:**
- user_id → users(id)
- question_id → questions(id)

**Esimerkkitietue:**
```sql
INSERT INTO question_attempts (user_id, question_id, correct, time_taken)
VALUES (1, 45, TRUE, 18);
```

**Käyttötapauksia:**
- Tilastojen laskenta
- Kategoriakohtainen onnistumisprosentti
- Vaikeimpien kysymysten tunnistaminen
- Oppimiskäyrän piirtäminen

---

### user_achievements

Käyttäjien avaamat saavutukset.

**Sarakkeet:**

| Sarake | Tyyppi | Null | Default | Kuvaus |
|--------|--------|------|---------|---------|
| id | INTEGER | NO | AUTO | Pääavain |
| user_id | INTEGER | NO | - | Käyttäjä (FK) |
| achievement_id | TEXT | NO | - | Saavutuksen tunniste |
| unlocked_at | TIMESTAMP | NO | NOW() | Milloin avattu |

**Indeksit:**
- PRIMARY KEY (id)
- UNIQUE (user_id, achievement_id)
- INDEX (user_id)
- INDEX (achievement_id)

**Foreign Keys:**
- user_id → users(id)

**Saavutukset (achievement_id):**
- first_steps
- quick_learner
- perfectionist
- dedicated
- expert
- master
- streak_3
- streak_7
- streak_30
- category_master_farmakologia
- category_master_annosjakelu
- simulation_complete
- simulation_perfect
- early_bird
- night_owl
- speed_demon

**Esimerkkitietue:**
```sql
INSERT INTO user_achievements (user_id, achievement_id)
VALUES (1, 'first_steps');
```

---

### study_sessions

Oppimissessiot. Tallentaa milloin käyttäjä on harjoitellut.

**Sarakkeet:**

| Sarake | Tyyppi | Null | Default | Kuvaus |
|--------|--------|------|---------|---------|
| id | INTEGER | NO | AUTO | Pääavain |
| user_id | INTEGER | NO | - | Käyttäjä (FK) |
| start_time | TIMESTAMP | NO | NOW() | Aloitusaika |
| end_time | TIMESTAMP | YES | NULL | Lopetusaika (NULL = kesken) |
| session_type | TEXT | NO | - | Tyyppi: practice/review/simulation |
| questions_answered | INTEGER | YES | 0 | Vastattujen kysymysten määrä |
| questions_correct | INTEGER | YES | 0 | Oikeiden vastausten määrä |
| categories | TEXT | YES | NULL | Kategoriat (JSON) |

**Indeksit:**
- PRIMARY KEY (id)
- INDEX (user_id, start_time)
- INDEX (session_type)

**Foreign Keys:**
- user_id → users(id)

**Esimerkkitietue:**
```sql
INSERT INTO study_sessions (user_id, start_time, end_time, session_type, questions_answered, questions_correct)
VALUES (1, '2025-10-24 10:00:00', '2025-10-24 10:30:00', 'practice', 20, 17);
```

---

### simulation_results

Koesimulaatioiden tulokset.

**Sarakkeet:**

| Sarake | Tyyppi | Null | Default | Kuvaus |
|--------|--------|------|---------|---------|
| id | INTEGER | NO | AUTO | Pääavain |
| user_id | INTEGER | NO | - | Käyttäjä (FK) |
| score | INTEGER | NO | - | Pisteet (oikeat vastaukset) |
| total_questions | INTEGER | NO | 50 | Kysymysten määrä |
| time_taken | INTEGER | NO | - | Kulunut aika (sekunteina) |
| completed_at | TIMESTAMP | NO | NOW() | Valmistumisaika |
| passed | BOOLEAN | NO | - | Läpäisikö (80%+) |
| answers | TEXT | YES | NULL | Vastaukset (JSON) |

**Indeksit:**
- PRIMARY KEY (id)
- INDEX (user_id, completed_at)
- INDEX (passed)

**Foreign Keys:**
- user_id → users(id)

**JSON-rakenne (answers):**
```json
[
  {"question_id": 1, "selected": 2, "correct": true, "time_taken": 15},
  {"question_id": 5, "selected": 0, "correct": false, "time_taken": 22},
  ...
]
```

**Esimerkkitietue:**
```sql
INSERT INTO simulation_results (user_id, score, total_questions, time_taken, passed)
VALUES (1, 42, 50, 2845, TRUE);
```

---

### distractor_attempts

Häiriötekijien vastaukset.

**Sarakkeet:**

| Sarake | Tyyppi | Null | Default | Kuvaus |
|--------|--------|------|---------|---------|
| id | INTEGER | NO | AUTO | Pääavain |
| user_id | INTEGER | NO | - | Käyttäjä (FK) |
| scenario | TEXT | NO | - | Häiriötekijän skenaario |
| user_choice | INTEGER | NO | - | Käyttäjän valinta (0-2) |
| correct_choice | INTEGER | NO | - | Oikea valinta |
| is_correct | BOOLEAN | NO | - | Oliko valinta oikein |
| response_time | INTEGER | NO | - | Vastausaika (ms) |
| created_at | TIMESTAMP | NO | NOW() | Luontiaika |

**Indeksit:**
- PRIMARY KEY (id)
- INDEX (user_id, created_at)

**Foreign Keys:**
- user_id → users(id)

**Esimerkkitietue:**
```sql
INSERT INTO distractor_attempts (user_id, scenario, user_choice, correct_choice, is_correct, response_time)
VALUES (1, 'Puhelimesi soi...', 2, 2, TRUE, 3500);
```

---

## Relaatiot

### Kaavio

```
users (1) ──< (N) user_question_progress >── (1) questions
  │                                                    │
  │                                                    │
  ├─< (N) question_attempts >──────────────────────────┤
  │
  ├─< (N) user_achievements
  │
  ├─< (N) study_sessions
  │
  ├─< (N) simulation_results
  │
  └─< (N) distractor_attempts
```

### Foreign Key -rajoitteet

```sql
-- user_question_progress
ALTER TABLE user_question_progress
ADD CONSTRAINT fk_uqp_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
ADD CONSTRAINT fk_uqp_question FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE;

-- question_attempts
ALTER TABLE question_attempts
ADD CONSTRAINT fk_qa_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
ADD CONSTRAINT fk_qa_question FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE;

-- user_achievements
ALTER TABLE user_achievements
ADD CONSTRAINT fk_ua_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- study_sessions
ALTER TABLE study_sessions
ADD CONSTRAINT fk_ss_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- simulation_results
ALTER TABLE simulation_results
ADD CONSTRAINT fk_sr_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- distractor_attempts
ALTER TABLE distractor_attempts
ADD CONSTRAINT fk_da_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
```

---

## Indeksit

### Suorituskyvyn optimointi

**Tärkeitä indeksejä:**

```sql
-- Käyttäjähaku
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);

-- Kysymyshaut
CREATE INDEX idx_questions_category ON questions(category);
CREATE INDEX idx_questions_difficulty ON questions(difficulty);

-- Spaced Repetition
CREATE INDEX idx_uqp_user_question ON user_question_progress(user_id, question_id);
CREATE INDEX idx_uqp_last_shown ON user_question_progress(last_shown);

-- Tilastot
CREATE INDEX idx_qa_user_timestamp ON question_attempts(user_id, timestamp);
CREATE INDEX idx_qa_question ON question_attempts(question_id);

-- Sessiot
CREATE INDEX idx_ss_user_start ON study_sessions(user_id, start_time);
```

### Composite-indeksit

```sql
-- Käyttäjän kertauskysymykset
CREATE INDEX idx_uqp_due ON user_question_progress(user_id, last_shown, interval);

-- Käyttäjän viimeaikaiset vastaukset
CREATE INDEX idx_qa_user_recent ON question_attempts(user_id, timestamp DESC);

-- Kategoriakohtaiset tilastot
CREATE INDEX idx_qa_user_category ON question_attempts(user_id, question_id);
```

---

## Kyselyesimerkkejä

### 1. Hae käyttäjän tilastot

```sql
SELECT 
    COUNT(*) as total_attempts,
    SUM(CASE WHEN correct THEN 1 ELSE 0 END) as correct_attempts,
    CAST(SUM(CASE WHEN correct THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as success_rate,
    AVG(time_taken) as avg_time
FROM question_attempts
WHERE user_id = ?;
```

### 2. Hae kertauskysymykset (Spaced Repetition)

```sql
SELECT 
    q.*,
    p.times_shown,
    p.times_correct,
    p.last_shown,
    p.ease_factor,
    p.interval
FROM questions q
JOIN user_question_progress p ON q.id = p.question_id
WHERE p.user_id = ?
  AND p.last_shown IS NOT NULL
  AND DATE(p.last_shown, '+' || p.interval || ' days') <= DATE('now')
ORDER BY DATE(p.last_shown, '+' || p.interval || ' days') ASC
LIMIT 20;
```

### 3. Kategoriakohtaiset tilastot

```sql
SELECT 
    q.category,
    SUM(p.times_shown) as attempts,
    SUM(p.times_correct) as corrects,
    CAST(SUM(p.times_correct) AS FLOAT) / SUM(p.times_shown) as success_rate
FROM user_question_progress p
JOIN questions q ON p.question_id = q.id
WHERE p.user_id = ?
  AND p.times_shown > 0
GROUP BY q.category;
```

### 4. Käyttäjän streak

```sql
SELECT DISTINCT DATE(timestamp) as practice_date
FROM question_attempts
WHERE user_id = ?
ORDER BY practice_date DESC;
```

### 5. Vaikeimmat kysymykset

```sql
SELECT 
    q.id,
    q.question,
    q.category,
    COUNT(qa.id) as attempts,
    SUM(CASE WHEN qa.correct THEN 1 ELSE 0 END) as corrects,
    CAST(SUM(CASE WHEN qa.correct THEN 1 ELSE 0 END) AS FLOAT) / COUNT(qa.id) as success_rate
FROM questions q
JOIN question_attempts qa ON q.id = qa.question_id
GROUP BY q.id
HAVING COUNT(qa.id) >= 10
ORDER BY success_rate ASC
LIMIT 10;
```

---

## Migraatiot

### Versiohistoria

**v1.0.0 (2025-10-24)** - Alkuperäinen schema
- Kaikki taulut luotu
- Indeksit lisätty
- Foreign key -rajoitteet

**v1.1.0 (tulossa)** - Lisäominaisuudet
- `user_notes` - Käyttäjän muistiinpanot kysymyksiin
- `question_tags` - Tägijärjestelmä
- `learning_paths` - Oppimispolut

### Migraatiotyökalu

**Flask-Migrate (suositeltu):**

```bash
# Alusta
flask db init

# Luo migraatio
flask db migrate -m "Lisää user_notes-taulu"

# Suorita migraatio
flask db upgrade

# Peruuta migraatio
flask db downgrade
```

### Manuaaliset migraatiot

**Esimerkki: Lisää sarake**
```sql
-- Lisää sarake users-tauluun
ALTER TABLE users ADD COLUMN last_login TIMESTAMP DEFAULT NULL;

-- Lisää indeksi
CREATE INDEX idx_users_last_login ON users(last_login);
```

---

## Backup ja palautus

### Backup (PostgreSQL)

```bash
# Täydellinen backup
pg_dump -U loveuser -h localhost loveenhanced > backup_$(date +%Y%m%d).sql

# Pakattu backup
pg_dump -U loveuser -h localhost loveenhanced | gzip > backup_$(date +%Y%m%d).sql.gz

# Vain data (ei schemaa)
pg_dump -U loveuser -h localhost --data-only loveenhanced > data_backup.sql
```

### Palautus (PostgreSQL)

```bash
# Palauta SQL-tiedostosta
psql -U loveuser -h localhost -d loveenhanced < backup_20251024.sql

# Palauta pakatusta
gunzip -c backup_20251024.sql.gz | psql -U loveuser -h localhost -d loveenhanced
```

### Backup (SQLite)

```bash
# Kopioi tiedosto
cp data/questions.db data/questions_backup_$(date +%Y%m%d).db

# Tai käytä sqlite3:n .backup-komentoa
sqlite3 data/questions.db ".backup data/questions_backup.db"
```

---

## Suorituskyvyn optimointi

### Analytiikka

**PostgreSQL:**
```sql
-- Tarkista kyselyn suoritussuunnitelma
EXPLAIN ANALYZE
SELECT * FROM question_attempts WHERE user_id = 1;

-- Tarkista taulun tilastot
SELECT schemaname, tablename, n_tup_ins, n_tup_upd, n_tup_del
FROM pg_stat_user_tables
WHERE tablename = 'question_attempts';
```

**SQLite:**
```sql
-- Tarkista kyselyn suoritussuunnitelma
EXPLAIN QUERY PLAN
SELECT * FROM question_attempts WHERE user_id = 1;

-- Analysoi tietokanta
ANALYZE;
```

### Vacuum

**PostgreSQL:**
```sql
-- Siivoa ja optimoi
VACUUM ANALYZE;

-- Täysi vacuum (vaatii enemmän aikaa)
VACUUM FULL;
```

**SQLite:**
```sql
-- Tiivistä tietokanta
VACUUM;
```

---

## Tietoturva

### Pääsy

- **Käyttäjän luonti:**
  ```sql
  CREATE USER loveuser WITH PASSWORD 'vahva-salasana';
  GRANT ALL PRIVILEGES ON DATABASE loveenhanced TO loveuser;
  ```

- **Rajoitettu pääsy:**
  ```sql
  -- Vain SELECT-oikeus
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonlyuser;
  ```

### Salasanat

**KOSKAAN:**
- Älä tallenna salasanoja selkotekstinä
- Älä käytä heikkoa hajautusta (MD5, SHA1)

**AINA:**
- Käytä bcrypt-hajautusta
- Salasanakustannus (cost) vähintään 12
- Tarkista salasanan vahvuus

**Python-esimerkki:**
```python
from werkzeug.security import generate_password_hash, check_password_hash

# Hajautus
hashed = generate_password_hash('salasana', method='pbkdf2:sha256')

# Tarkistus
is_valid = check_password_hash(hashed, 'salasana')
```

---

## Yhteystiedot

**Database Admin:** dba@loveenhanced.fi  
**Dokumentaatio:** https://docs.loveenhanced.fi/database

**Versio:** 1.0.0  
**Viimeksi päivitetty:** 24.10.2025
