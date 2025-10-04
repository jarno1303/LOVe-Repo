import sqlite3
import json
import os
from datetime import datetime
from models.models import Question
import random

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
                explanation TEXT NOT NULL,
                options TEXT NOT NULL,
                correct INTEGER NOT NULL,
                category TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            """)

    def migrate_database(self):
        """Tarkistaa ja lisää puuttuvat sarakkeet ja taulut tietokantaan."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("PRAGMA table_info(users)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'distractors_enabled' not in columns:
                    cursor.execute("ALTER TABLE users ADD COLUMN distractors_enabled BOOLEAN NOT NULL DEFAULT 1")
                if 'distractor_probability' not in columns:
                    cursor.execute("ALTER TABLE users ADD COLUMN distractor_probability INTEGER NOT NULL DEFAULT 25")
                if 'last_practice_categories' not in columns:
                    cursor.execute("ALTER TABLE users ADD COLUMN last_practice_categories TEXT")
                if 'last_practice_difficulties' not in columns:
                    cursor.execute("ALTER TABLE users ADD COLUMN last_practice_difficulties TEXT")

                cursor.execute("""
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
                """)
                
                conn.commit()
        except sqlite3.Error as e:
            print(f"Tietokannan migraatiovirhe: {e}")

    def get_next_question(self, user_id, categories=None, difficulties=None):
        questions = self.get_questions(user_id, categories, difficulties, limit=100)
        if not questions:
            return None
        return random.choice(questions)

    def create_user(self, username, email, hashed_password):
        try:
            with sqlite3.connect(self.db_path) as conn:
                role = 'admin' if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0 else 'user'
                conn.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)", (username, email, hashed_password, role))
            return True, None
        except sqlite3.IntegrityError as e:
            return False, str(e)

    def get_user_by_username(self, username):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            
    def get_user_by_id(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            
    def get_users_by_role(self, role):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM users WHERE role = ?", (role,)).fetchall()

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

    def toggle_user_status(self, user_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                current_status = conn.execute("SELECT status FROM users WHERE id = ?", (user_id,)).fetchone()[0]
                new_status = 'blocked' if current_status == 'active' else 'active'
                conn.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, user_id))
            return True, None
        except Exception as e:
            return False, str(e)

    def update_user_practice_preferences(self, user_id, categories, difficulties):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE users 
                    SET last_practice_categories = ?, last_practice_difficulties = ?
                    WHERE id = ?
                """, (json.dumps(categories), json.dumps(difficulties), user_id))
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
                        question_ids = excluded.question_ids,
                        answers = excluded.answers,
                        current_index = excluded.current_index,
                        time_remaining = excluded.time_remaining,
                        last_updated = excluded.last_updated;
                """, (user_id, session_type, json.dumps(question_ids), json.dumps(answers), current_index, time_remaining, datetime.now()))
                # KORJATTU: Varmistetaan, että muutokset tallennetaan tietokantaan
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
        query = "SELECT q.*, p.times_shown, p.times_correct FROM questions q LEFT JOIN user_question_progress p ON q.id = p.question_id AND p.user_id = ? WHERE 1=1"
        params = [user_id]
        if categories and categories != ['']:
            query += f" AND q.category IN ({', '.join('?'*len(categories))})"
            params.extend(categories)
        if difficulties and difficulties != ['']:
            query += f" AND q.difficulty IN ({', '.join('?'*len(difficulties))})"
            params.extend(difficulties)
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        
        questions = []
        for row in rows:
            row_dict = dict(row)
            try:
                options = json.loads(row_dict.get('options', '[]'))
            except (json.JSONDecodeError, TypeError):
                continue
            
            correct_index = row_dict.get('correct')
            if not (isinstance(correct_index, int) and 0 <= correct_index < len(options)):
                continue

            question_fields = {k: row_dict.get(k) for k in Question.__annotations__ if k in row_dict}
            question_fields['options'] = options
            question_fields['times_seen'] = row_dict.get('times_shown') or 0
            question_fields['times_correct'] = row_dict.get('times_correct') or 0

            for field in Question.__annotations__:
                if field not in question_fields:
                    question_fields[field] = None
            
            try:
                questions.append(Question(**question_fields))
            except TypeError as e:
                print(f"Error creating Question object for ID {row_dict.get('id')}: {e}")
                
        return questions

    def get_question_by_id(self, question_id, user_id):
        query = "SELECT q.*, p.times_shown, p.times_correct FROM questions q LEFT JOIN user_question_progress p ON q.id = p.question_id AND p.user_id = ? WHERE q.id = ?"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(query, (user_id, question_id)).fetchone()
            if not row: return None
            
            row_dict = dict(row)
            options = json.loads(row_dict.get('options', '[]'))
            
            question_fields = {k: row_dict.get(k) for k in Question.__annotations__ if k in row_dict}
            question_fields['options'] = options
            question_fields['times_seen'] = row_dict.get('times_shown') or 0
            question_fields['times_correct'] = row_dict.get('times_correct') or 0
            
            for field in Question.__annotations__:
                if field not in question_fields:
                    question_fields[field] = None
            
            return Question(**question_fields)

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

    def get_categories(self):
        with sqlite3.connect(self.db_path) as conn:
            return [row[0] for row in conn.execute("SELECT DISTINCT category FROM questions ORDER BY category").fetchall()]

    def get_category_question_counts(self):
        """Laskee ja palauttaa kysymysten määrän per kategoria."""
        query = "SELECT category, COUNT(*) as count FROM questions GROUP BY category"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query).fetchall()
        return {row['category']: row['count'] for row in rows}

    def get_all_questions_for_admin(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT id, question, category, difficulty FROM questions ORDER BY category, id").fetchall()

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
                conn.execute("""
                     UPDATE questions SET question = ?, explanation = ?, options = ?, correct = ?, category = ?, difficulty = ?
                     WHERE id = ?
                """, (
                    data['question'], data['explanation'], json.dumps(data['options']),
                    data['correct'], data['category'].lower(), data['difficulty'].lower(), question_id
                ))
            return True, None
        except Exception as e:
            return False, str(e)

    def get_all_users_for_admin(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT id, username, email, role, status, created_at FROM users ORDER BY id").fetchall()

    def delete_user_by_id(self, user_id):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return True, None
        except Exception as e:
            return False, str(e)