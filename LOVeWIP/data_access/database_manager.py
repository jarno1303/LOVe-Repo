# data_access/database_manager.py
import sqlite3
import json
import os
from datetime import datetime
from models.models import Question
import random
from difflib import SequenceMatcher
import psycopg2
from psycopg2.extras import DictCursor

class DatabaseManager:
    def __init__(self, db_path=None):
        self.database_url = os.environ.get('DATABASE_URL')
        self.is_postgres = self.database_url is not None
        self.param_style = '%s' if self.is_postgres else '?'
        
        if not self.is_postgres:
            self.db_path = db_path if db_path else 'love_enhanced_web.db'
            if not os.path.exists(self.db_path):
                print("Tietokantaa ei löytynyt, alustetaan uusi...")
                self.init_database()
        
        self.migrate_database()

    def get_connection(self):
        if self.is_postgres:
            return psycopg2.connect(self.database_url)
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn

    def _execute(self, query, params=(), fetch=None):
        query = query.replace('?', self.param_style)
        conn = None
        try:
            conn = self.get_connection()
            with conn:
                with conn.cursor(cursor_factory=DictCursor if self.is_postgres else None) as cur:
                    cur.execute(query, params)
                    if fetch == 'one':
                        res = cur.fetchone()
                        return dict(res) if res else None
                    if fetch == 'all':
                        return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"Database error on query '{query[:100]}...': {e}")
            if conn and self.is_postgres:
                conn.rollback()
            return None if fetch == 'one' else []
        finally:
            if conn:
                conn.close()

    def init_database(self):
        id_type = "SERIAL PRIMARY KEY" if self.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        bool_type = "BOOLEAN" if self.is_postgres else "INTEGER"

        create_tables_sql = f"""
            CREATE TABLE IF NOT EXISTS questions (
                id {id_type}, question TEXT NOT NULL, question_normalized TEXT,
                explanation TEXT NOT NULL, options TEXT NOT NULL, correct INTEGER NOT NULL,
                category TEXT NOT NULL, difficulty TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, hint_type TEXT
            );
            CREATE TABLE IF NOT EXISTS users (
                id {id_type}, username TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', status TEXT NOT NULL DEFAULT 'active',
                distractors_enabled {bool_type} NOT NULL DEFAULT true, distractor_probability INTEGER NOT NULL DEFAULT 25,
                last_practice_categories TEXT, last_practice_difficulties TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_question_progress (
                user_id INTEGER NOT NULL, question_id INTEGER NOT NULL, times_shown INTEGER DEFAULT 0,
                times_correct INTEGER DEFAULT 0, last_shown TIMESTAMP, ease_factor REAL DEFAULT 2.5,
                interval INTEGER DEFAULT 1, PRIMARY KEY (user_id, question_id)
            );
            CREATE TABLE IF NOT EXISTS question_attempts (
                id {id_type}, user_id INTEGER NOT NULL, question_id INTEGER NOT NULL,
                correct {bool_type} NOT NULL, time_taken REAL NOT NULL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS active_sessions (
                user_id INTEGER PRIMARY KEY, session_type TEXT NOT NULL, question_ids TEXT NOT NULL,
                answers TEXT NOT NULL, current_index INTEGER NOT NULL, time_remaining INTEGER NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_achievements (
                user_id INTEGER NOT NULL, achievement_id TEXT NOT NULL, unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, achievement_id)
            );
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_tables_sql)
        except Exception as e:
            print(f"Virhe tietokannan alustuksessa: {e}")

    def normalize_question(self, text):
        if not text: return ""
        return " ".join(text.split()).lower().rstrip('?!. ')

    def migrate_database(self):
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor if self.is_postgres else None) as cur:
                    if self.is_postgres:
                        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
                        user_columns = [row['column_name'] for row in cur.fetchall()]
                    else:
                        cur.execute("PRAGMA table_info(users)")
                        user_columns = [row['name'] for row in cur.fetchall()]
                    
                    if 'expires_at' not in user_columns:
                        self._execute("ALTER TABLE users ADD COLUMN expires_at TIMESTAMP")
        except Exception as e:
            print(f"Migraatiovirhe: {e}")

    def create_user(self, username, email, hashed_password, expires_at=None):
        try:
            count_result = self._execute("SELECT COUNT(*) as count FROM users", fetch='one')
            count = count_result['count'] if count_result else 0
            role = 'admin' if count == 0 else 'user'
            
            self._execute(
                "INSERT INTO users (username, email, password, role, expires_at) VALUES (?, ?, ?, ?, ?)",
                (username, email, hashed_password, role, expires_at)
            )
            return True, None
        except Exception as e:
            error_str = str(e).lower()
            if 'unique constraint' in error_str or 'duplicate key value' in error_str:
                if 'username' in error_str: return False, "UNIQUE constraint failed: users.username"
                elif 'email' in error_str: return False, "UNIQUE constraint failed: users.email"
            return False, str(e)
            
    def get_next_test_user_number(self):
        try:
            test_users = self._execute("SELECT username FROM users WHERE username LIKE 'testuser%'", fetch='all')
            if not test_users: return 1
            max_num = 0
            for user in test_users:
                num_part = user['username'].replace('testuser', '')
                if num_part.isdigit():
                    num = int(num_part)
                    if num > max_num: max_num = num
            return max_num + 1
        except:
            return 1

    def get_user_by_id(self, user_id):
        return self._execute("SELECT * FROM users WHERE id = ?", (user_id,), fetch='one')
        
    def get_all_users_for_admin(self):
        return self._execute("SELECT id, username, email, role, status, created_at, distractors_enabled, distractor_probability, expires_at FROM users ORDER BY id", fetch='all')
    
    def update_user_password(self, user_id, new_hashed_password):
        try:
            self._execute("UPDATE users SET password = ? WHERE id = ?", (new_hashed_password, user_id))
            return True, None
        except Exception as e:
            return False, str(e)
            
    def update_user_role(self, user_id, new_role):
        try:
            self._execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
            return True, None
        except Exception as e:
            return False, str(e)

    def update_user(self, user_id, data):
        try:
            set_clauses = []
            update_params = []
            if 'distractors_enabled' in data:
                set_clauses.append("distractors_enabled = ?")
                update_params.append(bool(data['distractors_enabled']))
            if 'distractor_probability' in data:
                set_clauses.append("distractor_probability = ?")
                update_params.append(max(0, min(100, int(data['distractor_probability']))))
            
            if not set_clauses: return True, None
            
            query = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = ?"
            update_params.append(user_id)
            self._execute(query, tuple(update_params))
            return True, None
        except Exception as e:
            return False, str(e)

    def update_user_practice_preferences(self, user_id, categories, difficulties):
        try:
            self._execute("UPDATE users SET last_practice_categories = ?, last_practice_difficulties = ? WHERE id = ?", 
                          (json.dumps(categories), json.dumps(difficulties), user_id))
            return True, None
        except Exception as e:
            return False, str(e)

    def save_or_update_session(self, user_id, session_type, question_ids, answers, current_index, time_remaining):
        try:
            if self.is_postgres:
                query = """
                    INSERT INTO active_sessions (user_id, session_type, question_ids, answers, current_index, time_remaining, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(user_id) DO UPDATE SET
                        question_ids = EXCLUDED.question_ids, answers = EXCLUDED.answers, current_index = EXCLUDED.current_index,
                        time_remaining = EXCLUDED.time_remaining, last_updated = EXCLUDED.last_updated;
                """
            else: # SQLite
                query = """
                    INSERT OR REPLACE INTO active_sessions (user_id, session_type, question_ids, answers, current_index, time_remaining, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                """
            self._execute(query, (user_id, session_type, json.dumps(question_ids), json.dumps(answers), current_index, time_remaining, datetime.now()))
            return True, None
        except Exception as e:
            return False, str(e)

    def get_active_session(self, user_id):
        session_data = self._execute("SELECT * FROM active_sessions WHERE user_id = ?", (user_id,), fetch='one')
        if session_data:
            session_data['question_ids'] = json.loads(session_data['question_ids'])
            session_data['answers'] = json.loads(session_data['answers'])
            return session_data
        return None

    def delete_active_session(self, user_id):
        try:
            self._execute("DELETE FROM active_sessions WHERE user_id = ?", (user_id,))
            return True, None
        except Exception as e:
            return False, str(e)

    def get_questions(self, user_id, categories=None, difficulties=None, limit=None):
        query = "SELECT q.*, p.times_shown, p.times_correct, p.ease_factor, p.interval FROM questions q LEFT JOIN user_question_progress p ON q.id = p.question_id AND p.user_id = ?"
        params = [user_id]
        where_clauses = []

        if categories and 'Kaikki kategoriat' not in categories:
            cat_list = categories if isinstance(categories, list) else [categories]
            if cat_list:
                where_clauses.append(f"q.category IN ({', '.join(['?']*len(cat_list))})")
                params.extend(cat_list)
        
        if difficulties:
            diff_list = difficulties if isinstance(difficulties, list) else [difficulties]
            if diff_list:
                where_clauses.append(f"q.difficulty IN ({', '.join(['?']*len(diff_list))})")
                params.extend(diff_list)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY RANDOM()"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        rows = self._execute(query, tuple(params), fetch='all')
        
        questions = []
        for row in rows if rows else []:
            try:
                row['options'] = json.loads(row.get('options', '[]'))
                for key, default in [('times_shown', 0), ('times_correct', 0), ('ease_factor', 2.5), ('interval', 1)]:
                    if row.get(key) is None: row[key] = default
                questions.append(Question(**row))
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Virheellinen data kysymykselle ID {row.get('id')}: {e}")
                continue
                
        return questions

    def get_question_by_id(self, question_id, user_id):
        query = """
            SELECT q.*, COALESCE(p.times_shown, 0) as times_shown, COALESCE(p.times_correct, 0) as times_correct,
                   p.last_shown, COALESCE(p.ease_factor, 2.5) as ease_factor, COALESCE(p.interval, 1) as interval
            FROM questions q
            LEFT JOIN user_question_progress p ON q.id = p.question_id AND p.user_id = ?
            WHERE q.id = ?
        """
        row = self._execute(query, (user_id, question_id), fetch='one')
        if not row: return None
        try:
            row['options'] = json.loads(row['options']) if row['options'] else []
            return Question(**row)
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Virhe Question-objektin luonnissa ID:llä {question_id}: {e}")
            return None

    def update_question_stats(self, question_id, is_correct, time_taken, user_id):
        try:
            if self.is_postgres:
                self._execute("INSERT INTO user_question_progress (user_id, question_id) VALUES (?, ?) ON CONFLICT (user_id, question_id) DO NOTHING", (user_id, question_id))
            else:
                self._execute("INSERT OR IGNORE INTO user_question_progress (user_id, question_id) VALUES (?, ?)", (user_id, question_id))
            
            self._execute("UPDATE user_question_progress SET times_shown = times_shown + 1, times_correct = times_correct + ?, last_shown = ? WHERE user_id = ? AND question_id = ?",
                          (1 if is_correct else 0, datetime.now(), user_id, question_id))
            self._execute("INSERT INTO question_attempts (user_id, question_id, correct, time_taken) VALUES (?, ?, ?, ?)",
                          (user_id, question_id, is_correct, time_taken))
        except Exception as e:
            print(f"Virhe päivitettäessä kysymystilastoja: {e}")

    def get_categories(self):
        rows = self._execute("SELECT DISTINCT category FROM questions ORDER BY category", fetch='all')
        return [row['category'] for row in rows] if rows else []
        
    def delete_user_by_id(self, user_id):
        try:
            self._execute("DELETE FROM users WHERE id = ?", (user_id,))
            return True, None
        except Exception as e:
            return False, str(e)