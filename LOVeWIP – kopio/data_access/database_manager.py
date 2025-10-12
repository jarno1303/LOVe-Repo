import sqlite3
import json
import os
from datetime import datetime
from models.models import Question
import random
from difflib import SequenceMatcher

class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = 'love_enhanced_web.db'
        self.db_path = db_path
        if not os.path.exists(db_path):
            print("Tietokantaa ei löytynyt, alustetaan uusi...")
            self.init_database()
        
        self.migrate_database()

    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                question_normalized TEXT,
                explanation TEXT NOT NULL,
                options TEXT NOT NULL,
                correct INTEGER NOT NULL,
                category TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                hint_type TEXT
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                distractors_enabled BOOLEAN NOT NULL DEFAULT 1,
                distractor_probability INTEGER NOT NULL DEFAULT 25,
                last_practice_categories TEXT,
                last_practice_difficulties TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_question_progress (
                user_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                times_shown INTEGER DEFAULT 0,
                times_correct INTEGER DEFAULT 0,
                last_shown TIMESTAMP,
                ease_factor REAL DEFAULT 2.5,
                interval INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, question_id),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS question_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                correct BOOLEAN NOT NULL,
                time_taken REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS active_sessions (
                user_id INTEGER PRIMARY KEY,
                session_type TEXT NOT NULL,
                question_ids TEXT NOT NULL,
                answers TEXT NOT NULL,
                current_index INTEGER NOT NULL,
                time_remaining INTEGER NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS user_achievements (
                user_id INTEGER NOT NULL,
                achievement_id TEXT NOT NULL,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, achievement_id),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
            """)

    def normalize_question(self, text):
        """Normalisoi kysymystekstin duplikaattitarkistusta varten."""
        if not text:
            return ""
        
        # Poista ylimääräiset välilyönnit ja rivinvaihdot
        normalized = " ".join(text.split())
        
        # Pienet kirjaimet
        normalized = normalized.lower()
        
        # Poista lopun erikoismerkit
        normalized = normalized.rstrip('?!. ')
        
        return normalized

    def migrate_database(self):
        """Tarkistaa ja lisää puuttuvat sarakkeet ja taulut tietokantaan."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("PRAGMA table_info(users)")
                user_columns = [row[1] for row in cursor.fetchall()]
                if 'distractors_enabled' not in user_columns:
                    cursor.execute("ALTER TABLE users ADD COLUMN distractors_enabled BOOLEAN NOT NULL DEFAULT 1")
                if 'distractor_probability' not in user_columns:
                    cursor.execute("ALTER TABLE users ADD COLUMN distractor_probability INTEGER NOT NULL DEFAULT 25")
                if 'last_practice_categories' not in user_columns:
                    cursor.execute("ALTER TABLE users ADD COLUMN last_practice_categories TEXT")
                if 'last_practice_difficulties' not in user_columns:
                    cursor.execute("ALTER TABLE users ADD COLUMN last_practice_difficulties TEXT")

                cursor.execute("PRAGMA table_info(questions)")
                question_columns = [row[1] for row in cursor.fetchall()]
                if 'hint_type' not in question_columns:
                    cursor.execute("ALTER TABLE questions ADD COLUMN hint_type TEXT")
                
                # UUSI: Lisää question_normalized -sarake
                if 'question_normalized' not in question_columns:
                    cursor.execute("ALTER TABLE questions ADD COLUMN question_normalized TEXT")
                    
                    # Päivitä olemassa olevat kysymykset
                    print("Normalisoidaan olemassa olevat kysymykset...")
                    questions = cursor.execute("SELECT id, question FROM questions").fetchall()
                    for q_id, q_text in questions:
                        normalized = self.normalize_question(q_text)
                        cursor.execute("UPDATE questions SET question_normalized = ? WHERE id = ?", (normalized, q_id))
                    
                    # Luo UNIQUE-indeksi
                    try:
                        cursor.execute("CREATE UNIQUE INDEX idx_unique_question ON questions(question_normalized)")
                        print("✅ UNIQUE-indeksi luotu kysymyksille")
                    except sqlite3.OperationalError:
                        # Indeksi on jo olemassa
                        pass

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS active_sessions (
                        user_id INTEGER PRIMARY KEY, session_type TEXT NOT NULL, question_ids TEXT NOT NULL,
                        answers TEXT NOT NULL, current_index INTEGER NOT NULL, time_remaining INTEGER NOT NULL,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    );
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_achievements (
                        user_id INTEGER NOT NULL, achievement_id TEXT NOT NULL,
                        unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, achievement_id),
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    );
                """)
                
                conn.commit()
        except sqlite3.Error as e:
            print(f"Tietokannan migraatiovirhe: {e}")

    def create_user(self, username, email, hashed_password):
        try:
            with sqlite3.connect(self.db_path) as conn:
                role = 'admin' if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0 else 'user'
                conn.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)", (username, email, hashed_password, role))
            return True, None
        except sqlite3.IntegrityError as e:
            return False, str(e)

    def get_user_by_id(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def update_user_password(self, user_id, new_hashed_password):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("UPDATE users SET password = ? WHERE id = ?", (new_hashed_password, user_id))
            return True, None
        except Exception as e:
            return False, str(e)

    def update_user_role(self, user_id, new_role):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
            return True, None
        except Exception as e:
            return False, str(e)

    def update_user(self, user_id, data):
        """
        Päivittää käyttäjän asetuksia (distractors_enabled ja distractor_probability).
        
        Args:
            user_id: Käyttäjän ID
            data: Sanakirja, joka sisältää päivitettävät kentät (distractors_enabled, distractor_probability)
        
        Returns:
            tuple: (success, error)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                update_query = "UPDATE users SET "
                update_params = []
                set_clauses = []
                
                if 'distractors_enabled' in data:
                    set_clauses.append("distractors_enabled = ?")
                    update_params.append(int(bool(data['distractors_enabled'])))  # Muunnetaan boolean kokonaisluvuksi (0 tai 1)
                
                if 'distractor_probability' in data:
                    probability = max(0, min(100, int(data['distractor_probability'])))  # Rajaa 0–100
                    set_clauses.append("distractor_probability = ?")
                    update_params.append(probability)
                
                if not set_clauses:
                    return True, None  # Ei päivitettäviä kenttiä
                
                update_query += ", ".join(set_clauses) + " WHERE id = ?"
                update_params.append(user_id)
                
                conn.execute(update_query, update_params)
                conn.commit()
                return True, None
        except sqlite3.Error as e:
            return False, str(e)

    def get_all_users_for_admin(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("""
                SELECT id, username, email, role, status, created_at, distractors_enabled, distractor_probability 
                FROM users ORDER BY id
            """).fetchall()

    def update_user_practice_preferences(self, user_id, categories, difficulties):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("UPDATE users SET last_practice_categories = ?, last_practice_difficulties = ? WHERE id = ?", 
                             (json.dumps(categories), json.dumps(difficulties), user_id))
                conn.commit()
            return True, None
        except sqlite3.Error as e:
            return False, str(e)

    def save_or_update_session(self, user_id, session_type, question_ids, answers, current_index, time_remaining):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO active_sessions (user_id, session_type, question_ids, answers, current_index, time_remaining, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        question_ids = excluded.question_ids, answers = excluded.answers, current_index = excluded.current_index,
                        time_remaining = excluded.time_remaining, last_updated = excluded.last_updated;
                """, (user_id, session_type, json.dumps(question_ids), json.dumps(answers), current_index, time_remaining, datetime.now()))
                conn.commit()
            return True, None
        except Exception as e:
            return False, str(e)

    def get_active_session(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            session_data = conn.execute("SELECT * FROM active_sessions WHERE user_id = ?", (user_id,)).fetchone()
            if session_data:
                session_dict = dict(session_data)
                session_dict['question_ids'] = json.loads(session_dict['question_ids'])
                session_dict['answers'] = json.loads(session_dict['answers'])
                return session_dict
            return None

    def delete_active_session(self, user_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM active_sessions WHERE user_id = ?", (user_id,))
            return True, None
        except Exception as e:
            return False, str(e)

    def get_questions(self, user_id, categories=None, difficulties=None, limit=None):
        query = "SELECT q.*, p.times_shown, p.times_correct, p.ease_factor, p.interval FROM questions q LEFT JOIN user_question_progress p ON q.id = p.question_id AND p.user_id = ?"
        params = [user_id]
        where_clauses = []

        if categories and categories != ['']:
            cat_list = categories if isinstance(categories, list) else [categories]
            where_clauses.append(f"q.category IN ({', '.join('?'*len(cat_list))})")
            params.extend(cat_list)
        
        if difficulties and difficulties != ['']:
            diff_list = difficulties if isinstance(difficulties, list) else [difficulties]
            where_clauses.append(f"q.difficulty IN ({', '.join('?'*len(diff_list))})")
            params.extend(diff_list)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        if limit:
            query += " ORDER BY RANDOM()"
            query += " LIMIT ?"
            params.append(limit)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        
        questions = []
        for row in rows:
            row_dict = dict(row)
            try:
                question_fields = {
                    'id': row_dict.get('id'), 'question': row_dict.get('question'),
                    'options': json.loads(row_dict.get('options', '[]')), 'correct': row_dict.get('correct'),
                    'explanation': row_dict.get('explanation'), 'category': row_dict.get('category'),
                    'difficulty': row_dict.get('difficulty'), 'created_at': row_dict.get('created_at'),
                    'hint_type': row_dict.get('hint_type'),
                    'times_shown': row_dict.get('times_shown', 0) or 0,
                    'times_correct': row_dict.get('times_correct', 0) or 0,
                    'last_shown': row_dict.get('last_shown'),
                    'ease_factor': row_dict.get('ease_factor', 2.5) or 2.5,
                    'interval': row_dict.get('interval', 1) or 1
                }
                questions.append(Question(**question_fields))
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                print(f"Virheellinen data kysymykselle ID {row_dict.get('id')}: {e}")
                continue
                
        return questions

    def get_question_by_id(self, question_id, user_id):
        query = """
            SELECT
                q.id, q.question, q.options, q.correct, q.explanation, q.category, q.difficulty, q.created_at, q.hint_type,
                COALESCE(p.times_shown, 0) as times_shown,
                COALESCE(p.times_correct, 0) as times_correct,
                p.last_shown,
                COALESCE(p.ease_factor, 2.5) as ease_factor,
                COALESCE(p.interval, 1) as interval
            FROM questions q
            LEFT JOIN user_question_progress p ON q.id = p.question_id AND p.user_id = ?
            WHERE q.id = ?
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(query, (user_id, question_id)).fetchone()
            if not row:
                return None
            row_dict = dict(row)
            try:
                return Question(
                    id=row_dict.get('id'), question=row_dict.get('question'),
                    options=json.loads(row_dict.get('options', '[]')), correct=row_dict.get('correct'),
                    explanation=row_dict.get('explanation'), category=row_dict.get('category'),
                    difficulty=row_dict.get('difficulty'), created_at=row_dict.get('created_at'),
                    hint_type=row_dict.get('hint_type'),
                    times_shown=row_dict.get('times_shown'), times_correct=row_dict.get('times_correct'),
                    last_shown=row_dict.get('last_shown'), ease_factor=row_dict.get('ease_factor'),
                    interval=row_dict.get('interval')
                )
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                print(f"Virhe Question-objektin luonnissa ID:llä {question_id}: {e}")
                return None

    def update_question_stats(self, question_id, is_correct, time_taken, user_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("INSERT OR IGNORE INTO user_question_progress (user_id, question_id) VALUES (?, ?)", (user_id, question_id))
                conn.execute("UPDATE user_question_progress SET times_shown = times_shown + 1, times_correct = times_correct + ?, last_shown = ? WHERE user_id = ? AND question_id = ?",
                             (1 if is_correct else 0, datetime.now(), user_id, question_id))
                conn.execute("INSERT INTO question_attempts (user_id, question_id, correct, time_taken) VALUES (?, ?, ?, ?)",
                             (user_id, question_id, is_correct, time_taken))
        except sqlite3.Error as e:
            print(f"Virhe päivitettäessä kysymystilastoja: {e}")

    def check_question_duplicate(self, question_text, exclude_id=None):
        """
        Tarkistaa onko kysymys jo olemassa.
        
        Args:
            question_text: Kysymysteksti
            exclude_id: Kysymyksen ID joka jätetään pois (käytä muokkauksessa)
        
        Returns:
            tuple: (is_duplicate, existing_question_dict tai None)
        """
        normalized = self.normalize_question(question_text)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            if exclude_id:
                existing = conn.execute(
                    "SELECT id, question, category, difficulty FROM questions WHERE question_normalized = ? AND id != ?",
                    (normalized, exclude_id)
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id, question, category, difficulty FROM questions WHERE question_normalized = ?",
                    (normalized,)
                ).fetchone()
            
            if existing:
                return True, dict(existing)
            return False, None

    def bulk_add_questions(self, questions_data):
        try:
            added_count = 0
            skipped_count = 0
            duplicate_count = 0
            errors = []
            
            with sqlite3.connect(self.db_path) as conn:
                for idx, q_data in enumerate(questions_data, 1):
                    try:
                        # Validoi kentät
                        required_fields = ['question', 'explanation', 'options', 'correct', 'category', 'difficulty']
                        if not all(field in q_data for field in required_fields):
                            raise ValueError("Puuttuvia kenttiä")
                        
                        # Normalisoi kysymysteksti
                        question_normalized = self.normalize_question(q_data['question'])
                        
                        # Tarkista duplikaatti
                        existing = conn.execute(
                            "SELECT id, question FROM questions WHERE question_normalized = ?",
                            (question_normalized,)
                        ).fetchone()
                        
                        if existing:
                            duplicate_count += 1
                            errors.append(f"Kysymys #{idx}: Duplikaatti (ID: {existing[0]}) - \"{existing[1][:50]}...\"")
                            continue
                        
                        # Lisää kysymys
                        conn.execute('''
                            INSERT INTO questions (question, question_normalized, options, correct, explanation, category, difficulty, created_at, hint_type)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            q_data['question'],
                            question_normalized,
                            json.dumps(q_data['options']),
                            q_data['correct'],
                            q_data['explanation'],
                            q_data['category'].lower(),
                            q_data['difficulty'].lower(),
                            datetime.now(),
                            q_data.get('hint_type')
                        ))
                        added_count += 1
                        
                    except sqlite3.IntegrityError:
                        # UNIQUE-rajoite esti duplikaatin
                        duplicate_count += 1
                        errors.append(f"Kysymys #{idx}: Duplikaatti havaittu tietokannassa")
                    except Exception as e:
                        errors.append(f"Kysymys #{idx}: {str(e)}")
                        skipped_count += 1
                
                conn.commit()
            
            return True, {
                'added': added_count,
                'skipped': skipped_count,
                'duplicates': duplicate_count,
                'errors': errors
            }
            
        except Exception as e:
            return False, str(e)

    def find_similar_questions(self, similarity_threshold=0.95):
        """
        Löytää samankaltaiset kysymykset käyttäen fuzzy matching -algoritmia.
        
        Args:
            similarity_threshold: Samankaltaisuuden kynnysarvo (0.0-1.0), oletuksena 0.95 (95%)
        
        Returns:
            list: Lista tuplia [(id1, id2, similarity, question1, question2), ...]
        """
        similar_pairs = []
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            questions = conn.execute("SELECT id, question, question_normalized FROM questions ORDER BY id").fetchall()
            
            # Vertaa jokaista kysymystä kaikkiin sen jälkeisiin
            for i in range(len(questions)):
                for j in range(i + 1, len(questions)):
                    q1 = questions[i]
                    q2 = questions[j]
                    
                    # Käytä normalisoituja versioita vertailuun
                    text1 = q1['question_normalized'] or self.normalize_question(q1['question'])
                    text2 = q2['question_normalized'] or self.normalize_question(q2['question'])
                    
                    # Laske samankaltaisuus
                    similarity = SequenceMatcher(None, text1, text2).ratio()
                    
                    if similarity >= similarity_threshold:
                        similar_pairs.append({
                            'id1': q1['id'],
                            'id2': q2['id'],
                            'similarity': round(similarity * 100, 1),
                            'question1': q1['question'],
                            'question2': q2['question']
                        })
        
        return similar_pairs

    def clear_all_questions(self):
        """
        VAROITUS: Poistaa KAIKKI kysymykset tietokannasta!
        Tämä toiminto on peruuttamaton.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Poista ensin viittaukset
                conn.execute("DELETE FROM question_attempts")
                conn.execute("DELETE FROM user_question_progress")
                conn.execute("DELETE FROM active_sessions")
                
                # Poista kysymykset
                result = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
                conn.execute("DELETE FROM questions")
                
                # Nollaa autoincrement
                conn.execute("DELETE FROM sqlite_sequence WHERE name='questions'")
                
                conn.commit()
            
            return True, {"deleted_count": result}
        except Exception as e:
            return False, str(e)

    def get_categories(self):
        with sqlite3.connect(self.db_path) as conn:
            return [row[0] for row in conn.execute("SELECT DISTINCT category FROM questions ORDER BY category").fetchall()]

    def get_single_question_for_edit(self, question_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            question_data = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
            if question_data:
                mutable_question = dict(question_data)
                mutable_question['options'] = json.loads(mutable_question['options'])
                return mutable_question
            return None

    def update_question(self, question_id, data):
        try:
            with sqlite3.connect(self.db_path) as conn:
                question_normalized = self.normalize_question(data['question'])
                conn.execute("""
                     UPDATE questions SET question = ?, question_normalized = ?, explanation = ?, options = ?, correct = ?, category = ?, difficulty = ?, hint_type = ?
                     WHERE id = ?
                """, (
                    data['question'], question_normalized, data['explanation'], json.dumps(data['options']),
                    data['correct'], data['category'].lower(), data['difficulty'].lower(), 
                    data.get('hint_type'), question_id
                ))
            return True, None
        except Exception as e:
            return False, str(e)

    def delete_question(self, question_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
                conn.commit()
            return True, None
        except Exception as e:
            return False, str(e)

    def delete_user_by_id(self, user_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return True, None
        except Exception as e:
            return False, str(e)