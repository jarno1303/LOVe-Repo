# TARKISTUSKOMMENTTI 14.10. KLO 10:00
# -*- coding: utf-8 -*-
# data_access/database_manager.py
import sqlite3
import json
import os
import logging
from datetime import datetime
from models.models import Question
import random
from difflib import SequenceMatcher
import psycopg2
from psycopg2.extras import DictCursor

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path=None):
        self.database_url = os.environ.get('DATABASE_URL')
        self.is_postgres = self.database_url is not None
        self.param_style = '%s' if self.is_postgres else '?'
        
        if not self.is_postgres:
            self.db_path = db_path if db_path else 'love_enhanced_web.db'
        
        # Suoritetaan migraatiot vasta yhteyden ollessa varma
        try:
            self.migrate_database()
        except Exception as e:
            logger.error(f"Tietokannan alustus tai migraatio epäonnistui käynnistyksessä: {e}")

    def get_connection(self):
        """Luo ja palauttaa tietokantayhteyden."""
        try:
            if self.is_postgres:
                if not self.database_url:
                    raise ValueError("DATABASE_URL-ympäristömuuttujaa ei ole asetettu.")
                return psycopg2.connect(self.database_url)
            else:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                return conn
        except Exception as e:
            logger.error(f"KRIITTINEN VIRHE: Tietokantayhteyden luonti epäonnistui: {e}")
            raise

    def _execute(self, query, params=(), fetch=None):
        """
        Suorittaa SQL-kyselyn ja palauttaa tulokset.
        Huolehtii parametrien oikeasta muodosta sekä PostgreSQL:lle että SQLite:lle.
        """
        query = query.replace('?', self.param_style)
        conn = self.get_connection()
        try:
            with conn:
                cursor_factory = DictCursor if self.is_postgres else None
                with conn.cursor(cursor_factory=cursor_factory) as cur:
                    cur.execute(query, params)
                    if fetch == 'one':
                        return cur.fetchone()
                    if fetch == 'all':
                        return cur.fetchall()
        finally:
            if conn:
                conn.close()

    def init_database(self):
        """Luo kaikki tarvittavat tietokantataulut."""
        id_type = "SERIAL PRIMARY KEY" if self.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        bool_type = "BOOLEAN" if self.is_postgres else "INTEGER"

        create_tables_sql = f"""
            CREATE TABLE IF NOT EXISTS questions (
                id {id_type}, 
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
                id {id_type}, 
                username TEXT NOT NULL UNIQUE, 
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL, 
                role TEXT NOT NULL DEFAULT 'user', 
                status TEXT NOT NULL DEFAULT 'active',
                distractors_enabled {bool_type} NOT NULL DEFAULT true, 
                distractor_probability INTEGER NOT NULL DEFAULT 25,
                last_practice_categories TEXT, 
                last_practice_difficulties TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                expires_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_question_progress (
                user_id INTEGER NOT NULL, 
                question_id INTEGER NOT NULL, 
                times_shown INTEGER DEFAULT 0,
                times_correct INTEGER DEFAULT 0, 
                last_shown TIMESTAMP, 
                ease_factor REAL DEFAULT 2.5,
                interval INTEGER DEFAULT 1, 
                PRIMARY KEY (user_id, question_id)
            );
            CREATE TABLE IF NOT EXISTS question_attempts (
                id {id_type}, 
                user_id INTEGER NOT NULL, 
                question_id INTEGER NOT NULL,
                correct {bool_type} NOT NULL, 
                time_taken REAL NOT NULL, 
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS active_sessions (
                user_id INTEGER PRIMARY KEY, 
                session_type TEXT NOT NULL, 
                question_ids TEXT NOT NULL,
                answers TEXT NOT NULL, 
                current_index INTEGER NOT NULL, 
                time_remaining INTEGER NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS user_achievements (
                user_id INTEGER NOT NULL, 
                achievement_id TEXT NOT NULL, 
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, achievement_id)
            );
        """
        conn = self.get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    for statement in create_tables_sql.split(';'):
                        if statement.strip():
                            cur.execute(statement)
        except (psycopg2.Error, sqlite3.Error) as e:
            logger.error(f"Virhe tietokannan alustuksessa: {e}")
            raise
        finally:
            conn.close()

    def migrate_database(self):
        """Lisää puuttuvat sarakkeet olemassa oleviin tauluihin."""
        bool_type = "BOOLEAN DEFAULT false" if self.is_postgres else "INTEGER DEFAULT 0"
        self._add_column_if_not_exists('user_question_progress', 'mistake_acknowledged', bool_type)
        self._add_column_if_not_exists('questions', 'status', "TEXT DEFAULT 'validated'")
        self._add_column_if_not_exists('questions', 'validated_by', 'INTEGER')
        self._add_column_if_not_exists('questions', 'validated_at', 'TIMESTAMP')
        self._add_column_if_not_exists('questions', 'validation_comment', 'TEXT')

    # data_access/database_manager.py

    def _add_column_if_not_exists(self, table_name, column_name, column_type):
        """Apufunktio sarakkeen lisäämiseksi, jos sitä ei ole olemassa."""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor if self.is_postgres else None) as cur:
                    column_exists = False
                    
                    # --- TÄMÄ LOGIIKKA ON KORJATTU ---
                    if self.is_postgres:
                        # PostgreSQL: Tarkista, palauttaako kysely rivin.
                        cur.execute("""
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name = %s AND column_name = %s
                        """, (table_name.lower(), column_name.lower()))
                        if cur.fetchone():
                            column_exists = True
                    else:
                        # SQLite: Tarkista sarakkeet PRAGMA-lauseella.
                        cur.execute(f"PRAGMA table_info({table_name})")
                        columns = [row[1] for row in cur.fetchall()]
                        if column_name in columns:
                            column_exists = True
                    # --- KORJAUKSEN LOPPU ---

                    if not column_exists:
                        alter_query = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                        cur.execute(alter_query)
                        logger.info(f"Sarake '{column_name}' lisätty tauluun '{table_name}'.")
                    else:
                        logger.debug(f"Sarake '{column_name}' on jo olemassa taulussa '{table_name}'.")
        except Exception as e:
            logger.error(f"Virhe sarakkeen '{column_name}' lisäämisessä tauluun '{table_name}': {e}")

    def create_user(self, username, email, hashed_password, expires_at=None):
        """Luo uuden käyttäjän."""
        try:
            self._execute(
                "INSERT INTO users (username, email, password, expires_at, created_at) VALUES (?, ?, ?, ?, ?)", 
                (username, email, hashed_password, expires_at, datetime.now())
            )
            return True, None
        except Exception as e:
            logger.error(f"Virhe käyttäjän luomisessa: {e}")
            return False, str(e)

    def get_user_by_username(self, username):
        """Hakee käyttäjän käyttäjänimen perusteella."""
        return self._execute("SELECT * FROM users WHERE username = ?", (username,), fetch='one')

    def get_user_by_id(self, user_id):
        """Hakee käyttäjän ID:n perusteella."""
        return self._execute("SELECT * FROM users WHERE id = ?", (user_id,), fetch='one')

    def get_all_users(self):
        """Hakee kaikki käyttäjät."""
        return self._execute("SELECT * FROM users ORDER BY created_at DESC", fetch='all')

    def update_user_role(self, user_id, new_role):
        """Päivittää käyttäjän roolin."""
        try:
            self._execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
            return True, None
        except Exception as e:
            logger.error(f"Virhe roolin päivityksessä: {e}")
            return False, str(e)

    def update_user_status(self, user_id, new_status):
        """Päivittää käyttäjän statuksen."""
        try:
            self._execute("UPDATE users SET status = ? WHERE id = ?", (new_status, user_id))
            return True, None
        except Exception as e:
            logger.error(f"Virhe statuksen päivityksessä: {e}")
            return False, str(e)

    def update_user_expiration(self, user_id, new_expiration):
        """Päivittää käyttäjän vanhentumispäivän."""
        try:
            self._execute("UPDATE users SET expires_at = ? WHERE id = ?", (new_expiration, user_id))
            return True, None
        except Exception as e:
            logger.error(f"Virhe vanhentumispäivän päivityksessä: {e}")
            return False, str(e)

    def delete_user(self, user_id):
        """Poistaa käyttäjän ja siihen liittyvät tiedot."""
        try:
            self._execute("DELETE FROM user_question_progress WHERE user_id = ?", (user_id,))
            self._execute("DELETE FROM question_attempts WHERE user_id = ?", (user_id,))
            self._execute("DELETE FROM active_sessions WHERE user_id = ?", (user_id,))
            self._execute("DELETE FROM user_achievements WHERE user_id = ?", (user_id,))
            self._execute("DELETE FROM users WHERE id = ?", (user_id,))
            return True, None
        except Exception as e:
            logger.error(f"Virhe käyttäjän poistossa: {e}")
            return False, str(e)

    def update_last_practice_preferences(self, user_id, categories, difficulties):
        """Päivittää käyttäjän viimeisimmät harjoitusasetukset."""
        try:
            self._execute(
                "UPDATE users SET last_practice_categories = ?, last_practice_difficulties = ? WHERE id = ?", 
                (json.dumps(categories), json.dumps(difficulties), user_id)
            )
            return True, None
        except Exception as e:
            logger.error(f"Virhe asetusten päivityksessä: {e}")
            return False, str(e)

    def get_categories(self):
        """Hakee kaikki kategoriat."""
        result = self._execute("SELECT DISTINCT category FROM questions ORDER BY category", fetch='all')
        return [row['category'] for row in result] if result else []

    def get_difficulties(self):
        """Hakee kaikki vaikeustasot."""
        result = self._execute("SELECT DISTINCT difficulty FROM questions ORDER BY difficulty", fetch='all')
        return [row['difficulty'] for row in result] if result else []

    def get_question_by_id(self, question_id):
        """Hakee kysymyksen ID:n perusteella."""
        row = self._execute("SELECT * FROM questions WHERE id = ?", (question_id,), fetch='one')
        if row:
            q_dict = dict(row)
            q_dict['options'] = json.loads(q_dict['options'])
            return q_dict
        return None

    def get_random_questions(self, categories=None, difficulties=None, count=20, exclude_ids=None):
        """Hakee satunnaisia kysymyksiä annetuilla kriteereillä."""
        try:
            query_parts = ["SELECT * FROM questions WHERE 1=1"]
            params = []

            if categories:
                placeholders = ','.join(['?'] * len(categories))
                query_parts.append(f"AND category IN ({placeholders})")
                params.extend(categories)

            if difficulties:
                placeholders = ','.join(['?'] * len(difficulties))
                query_parts.append(f"AND difficulty IN ({placeholders})")
                params.extend(difficulties)

            if exclude_ids:
                placeholders = ','.join(['?'] * len(exclude_ids))
                query_parts.append(f"AND id NOT IN ({placeholders})")
                params.extend(exclude_ids)

            query = " ".join(query_parts) + " ORDER BY RANDOM() LIMIT ?"
            params.append(count)

            rows = self._execute(query, tuple(params), fetch='all')
            
            questions = []
            for row in rows:
                q_dict = dict(row)
                q_dict['options'] = json.loads(q_dict['options'])
                questions.append(q_dict)
            
            return questions
        except Exception as e:
            logger.error(f"Virhe kysymysten haussa: {e}")
            return []

    def get_questions_by_category(self, category, difficulty=None, count=20):
        """Hakee kysymyksiä tietystä kategoriasta."""
        try:
            if difficulty:
                query = "SELECT * FROM questions WHERE category = ? AND difficulty = ? ORDER BY RANDOM() LIMIT ?"
                params = (category, difficulty, count)
            else:
                query = "SELECT * FROM questions WHERE category = ? ORDER BY RANDOM() LIMIT ?"
                params = (category, count)
            
            rows = self._execute(query, params, fetch='all')
            
            questions = []
            for row in rows:
                q_dict = dict(row)
                q_dict['options'] = json.loads(q_dict['options'])
                questions.append(q_dict)
            
            return questions
        except Exception as e:
            logger.error(f"Virhe kategorian kysymysten haussa: {e}")
            return []

    def record_question_attempt(self, user_id, question_id, correct, time_taken):
        """Tallentaa kysymykseen vastaamisen yrityksen."""
        try:
            self._execute(
                "INSERT INTO question_attempts (user_id, question_id, correct, time_taken, timestamp) VALUES (?, ?, ?, ?, ?)", 
                (user_id, question_id, correct, time_taken, datetime.now())
            )
            return True, None
        except Exception as e:
            logger.error(f"Virhe yrityksen tallennuksessa: {e}")
            return False, str(e)

    def update_question_progress(self, user_id, question_id, correct):
        """Päivittää käyttäjän edistymisen kysymyksessä."""
        try:
            existing = self._execute(
                "SELECT * FROM user_question_progress WHERE user_id = ? AND question_id = ?", 
                (user_id, question_id), 
                fetch='one'
            )

            if existing:
                new_times_shown = existing['times_shown'] + 1
                new_times_correct = existing['times_correct'] + (1 if correct else 0)
                self._execute(
                    "UPDATE user_question_progress SET times_shown = ?, times_correct = ?, last_shown = ? WHERE user_id = ? AND question_id = ?", 
                    (new_times_shown, new_times_correct, datetime.now(), user_id, question_id)
                )
            else:
                self._execute(
                    "INSERT INTO user_question_progress (user_id, question_id, times_shown, times_correct, last_shown) VALUES (?, ?, 1, ?, ?)", 
                    (user_id, question_id, 1 if correct else 0, datetime.now())
                )
            
            return True, None
        except Exception as e:
            logger.error(f"Virhe edistymisen päivityksessä: {e}")
            return False, str(e)

    def get_user_progress(self, user_id, question_id):
        """Hakee käyttäjän edistymisen tietyssä kysymyksessä."""
        return self._execute(
            "SELECT * FROM user_question_progress WHERE user_id = ? AND question_id = ?", 
            (user_id, question_id), 
            fetch='one'
        )

    def get_all_questions(self, limit=None, offset=0):
        """Hakee kaikki kysymykset."""
        try:
            if limit:
                query = "SELECT * FROM questions ORDER BY id LIMIT ? OFFSET ?"
                params = (limit, offset)
            else:
                query = "SELECT * FROM questions ORDER BY id"
                params = ()
            
            rows = self._execute(query, params, fetch='all')
            
            questions = []
            for row in rows:
                q_dict = dict(row)
                q_dict['options'] = json.loads(q_dict['options'])
                questions.append(q_dict)
            
            return questions
        except Exception as e:
            logger.error(f"Virhe kysymysten haussa: {e}")
            return []

    def get_total_question_count(self):
        """Palauttaa kysymysten kokonaismäärän."""
        result = self._execute("SELECT COUNT(*) as count FROM questions", fetch='one')
        return result['count'] if result else 0

    def update_question(self, question_id, question_data):
        """Päivittää kysymyksen tiedot."""
        try:
            options_json = json.dumps(question_data['options'])
            self._execute(
                """UPDATE questions SET 
                   question = ?, explanation = ?, options = ?, correct = ?, 
                   category = ?, difficulty = ? 
                   WHERE id = ?""",
                (question_data['question'], question_data['explanation'], options_json,
                 question_data['correct'], question_data['category'], question_data['difficulty'], question_id)
            )
            return True, None
        except Exception as e:
            logger.error(f"Virhe kysymyksen päivityksessä: {e}")
            return False, str(e)

    def add_question(self, question_data):
        """Lisää uuden kysymyksen."""
        try:
            options_json = json.dumps(question_data['options'])
            normalized = question_data['question'].lower().strip()
            
            self._execute(
                """INSERT INTO questions 
                   (question, question_normalized, explanation, options, correct, category, difficulty, created_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (question_data['question'], normalized, question_data['explanation'], options_json,
                 question_data['correct'], question_data['category'], question_data['difficulty'], datetime.now())
            )
            return True, None
        except Exception as e:
            logger.error(f"Virhe kysymyksen lisäämisessä: {e}")
            return False, str(e)

    def bulk_add_questions(self, questions_list):
        """Lisää useita kysymyksiä kerralla."""
        stats = {'added': 0, 'skipped': 0, 'errors': []}
        
        for q_data in questions_list:
            try:
                options_json = json.dumps(q_data['options'])
                normalized = q_data['question'].lower().strip()
                
                existing = self._execute(
                    "SELECT id FROM questions WHERE question_normalized = ?", 
                    (normalized,), 
                    fetch='one'
                )
                
                if existing:
                    stats['skipped'] += 1
                    continue
                
                self._execute(
                    """INSERT INTO questions 
                       (question, question_normalized, explanation, options, correct, category, difficulty, created_at) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (q_data['question'], normalized, q_data['explanation'], options_json, 
                     q_data['correct'], q_data['category'], q_data['difficulty'], datetime.now())
                )
                stats['added'] += 1
                
            except Exception as e:
                stats['skipped'] += 1
                stats['errors'].append(f"Virhe kysymyksessä '{q_data.get('question', 'N/A')[:30]}': {str(e)}")
                logger.error(f"Bulk add error: {e}")
        
        return True, stats

    def find_similar_questions(self, threshold=0.95):
        """Etsii samankaltaiset kysymykset."""
        try:
            all_questions = self._execute("SELECT id, question, category FROM questions ORDER BY id", fetch='all')
            if not all_questions:
                return []
            
            similar_pairs = []
            questions_list = list(all_questions)
            
            for i, q1 in enumerate(questions_list):
                for q2 in questions_list[i+1:]:
                    similarity = SequenceMatcher(None, q1['question'].lower(), q2['question'].lower()).ratio()
                    if similarity >= threshold:
                        similar_pairs.append({
                            'id1': q1['id'],
                            'question1': q1['question'],
                            'category1': q1['category'],
                            'id2': q2['id'],
                            'question2': q2['question'],
                            'category2': q2['category'],
                            'similarity': round(similarity * 100, 1)
                        })
            
            return similar_pairs
        except Exception as e:
            logger.error(f"Virhe samankaltaisuushaussa: {e}")
            return []

    def delete_question(self, question_id):
        """Poistaa kysymyksen ja siihen liittyvät tiedot."""
        try:
            self._execute("DELETE FROM user_question_progress WHERE question_id = ?", (question_id,))
            self._execute("DELETE FROM question_attempts WHERE question_id = ?", (question_id,))
            self._execute("DELETE FROM questions WHERE id = ?", (question_id,))
            return True, None
        except Exception as e:
            logger.error(f"Virhe kysymyksen poistossa: {e}")
            return False, str(e)

    def clear_all_questions(self):
        """Tyhjentää kaikki kysymykset tietokannasta."""
        try:
            count_result = self._execute("SELECT COUNT(*) as count FROM questions", fetch='one')
            count = count_result['count'] if count_result else 0
            
            self._execute("DELETE FROM question_attempts")
            self._execute("DELETE FROM user_question_progress")
            self._execute("DELETE FROM questions")
            
            return True, {'deleted_count': count}
        except Exception as e:
            logger.error(f"Virhe tietokannan tyhjennykesesä: {e}")
            return False, str(e)

    def merge_categories_to_standard(self):
        """Yhdistää kategoriat standardikategorioihin."""
        category_mapping = {
            'lääkelaskut': 'laskut',
            'lääkkeiden jako': 'annosjakelu',
            'lääkehoidon turvallisuus': 'turvallisuus',
            'potilasturvallisuus': 'turvallisuus',
            'ammattietiikka': 'etiikka',
            'etiikka ja turvallisuus': 'etiikka',
            'kliininen': 'kliininen farmakologia',
            'farmakologia': 'kliininen farmakologia'
        }
        
        try:
            updated_count = 0
            for old_cat, new_cat in category_mapping.items():
                result = self._execute(
                    "UPDATE questions SET category = ? WHERE LOWER(category) = LOWER(?)", 
                    (new_cat, old_cat)
                )
            
            categories = self.get_categories()
            category_counts = {}
            for cat in categories:
                count_result = self._execute("SELECT COUNT(*) as count FROM questions WHERE category = ?", (cat,), fetch='one')
                category_counts[cat] = count_result['count'] if count_result else 0
            
            return True, {'updated': sum(category_counts.values()), 'categories': category_counts}
        except Exception as e:
            logger.error(f"Virhe kategorioiden yhdistämisessä: {e}")
            return False, str(e)

    def save_or_update_session(self, user_id, session_type, question_ids, answers, current_index, time_remaining):
        """Tallentaa tai päivittää aktiivisen session."""
        try:
            if self.is_postgres:
                query = """
                    INSERT INTO active_sessions 
                        (user_id, session_type, question_ids, answers, current_index, time_remaining, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(user_id) DO UPDATE SET
                        session_type = EXCLUDED.session_type, 
                        question_ids = EXCLUDED.question_ids, 
                        answers = EXCLUDED.answers, 
                        current_index = EXCLUDED.current_index, 
                        time_remaining = EXCLUDED.time_remaining, 
                        last_updated = EXCLUDED.last_updated
                """
            else:
                query = """
                    INSERT OR REPLACE INTO active_sessions 
                        (user_id, session_type, question_ids, answers, current_index, time_remaining, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """
            self._execute(
                query, 
                (user_id, session_type, json.dumps(question_ids), json.dumps(answers), current_index, time_remaining, datetime.now())
            )
            return True, None
        except Exception as e:
            logger.error(f"Virhe session tallennuksessa: {e}")
            return False, str(e)

    def get_active_session(self, user_id):
        """Hakee aktiivisen session."""
        try:
            session_data = self._execute("SELECT * FROM active_sessions WHERE user_id = ?", (user_id,), fetch='one')
            if session_data:
                session_dict = dict(session_data)
                session_dict['question_ids'] = json.loads(session_dict['question_ids'])
                session_dict['answers'] = json.loads(session_dict['answers'])
                return session_dict
            return None
        except Exception as e:
            logger.error(f"Virhe session haussa: {e}")
            return None

    def delete_active_session(self, user_id):
        """Poistaa aktiivisen session."""
        try:
            self._execute("DELETE FROM active_sessions WHERE user_id = ?", (user_id,))
            return True, None
        except Exception as e:
            logger.error(f"Virhe session poistossa: {e}")
            return False, str(e)

    def get_user_achievements(self, user_id):
        """Hakee käyttäjän saavutukset."""
        return self._execute(
            "SELECT achievement_id, unlocked_at FROM user_achievements WHERE user_id = ?", 
            (user_id,), 
            fetch='all'
        )

    def unlock_achievement(self, user_id, achievement_id):
        """Avaa saavutuksen käyttäjälle."""
        try:
            if self.is_postgres:
                self._execute(
                    "INSERT INTO user_achievements (user_id, achievement_id) VALUES (?, ?) ON CONFLICT DO NOTHING", 
                    (user_id, achievement_id)
                )
            else:
                self._execute(
                    "INSERT OR IGNORE INTO user_achievements (user_id, achievement_id) VALUES (?, ?)", 
                    (user_id, achievement_id)
                )
            return True
        except Exception as e:
            logger.error(f"Virhe saavutuksen avaamisessa: {e}")
            return False

    # ============================================================================
    # UUDET KATEGORIATESTIT METODIT v1.1.0
    # ============================================================================

    def get_questions_by_categories(self, categories, count=30, difficulty=None):
        """Hae kysymyksiä valituista kategorioista"""
        try:
            placeholders = ','.join(['?'] * len(categories))
            query = f"""
                SELECT * FROM questions
                WHERE category IN ({placeholders})
                AND status = 'approved'
            """
            params = list(categories)
            
            if difficulty:
                query += " AND difficulty = ?"
                params.append(difficulty)
            
            query += " ORDER BY RANDOM() LIMIT ?"
            params.append(count)
            
            rows = self._execute(query, tuple(params), fetch='all')
            
            questions = []
            for row in rows:
                q_dict = dict(row)
                q_dict['options'] = json.loads(q_dict['options'])
                questions.append(q_dict)
            
            return questions
        except Exception as e:
            logger.error(f"Virhe kategorioiden kysymysten haussa: {e}")
            return []

    def create_test_session(self, user_id, test_type, categories, question_count, time_limit, questions):
        """Luo uusi testi-sessio"""
        try:
            query = """
                INSERT INTO test_sessions 
                (user_id, test_type, categories, question_count, time_limit, questions, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            if self.is_postgres:
                query += " RETURNING id"
            
            result = self._execute(query, (
                user_id,
                test_type,
                json.dumps(categories),
                question_count,
                time_limit,
                json.dumps(questions),
                datetime.now()
            ), fetch='one' if self.is_postgres else None)
            
            if self.is_postgres and result:
                return result['id']
            else:
                # SQLite: Hae viimeinen lisätty ID
                last_id = self._execute("SELECT last_insert_rowid() as id", fetch='one')
                return last_id['id'] if last_id else None
                
        except Exception as e:
            logger.error(f"Virhe testi-session luomisessa: {e}")
            return None

    def save_test_results(self, test_id, user_id, score, total_questions, passed, answers):
        """Tallenna testin tulokset"""
        try:
            query = """
                INSERT INTO test_results
                (test_id, user_id, score, total_questions, percentage, passed, answers, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            if self.is_postgres:
                query += " RETURNING id"
            
            percentage = (score / total_questions) * 100
            
            result = self._execute(query, (
                test_id,
                user_id,
                score,
                total_questions,
                percentage,
                passed,
                json.dumps(answers),
                datetime.now()
            ), fetch='one' if self.is_postgres else None)
            
            if self.is_postgres and result:
                return result['id']
            else:
                # SQLite: Hae viimeinen lisätty ID
                last_id = self._execute("SELECT last_insert_rowid() as id", fetch='one')
                return last_id['id'] if last_id else None
                
        except Exception as e:
            logger.error(f"Virhe testin tulosten tallennuksessa: {e}")
            return None

    def get_test_session(self, test_id):
        """Hae testi-sessio"""
        try:
            session = self._execute(
                "SELECT * FROM test_sessions WHERE id = ?",
                (test_id,),
                fetch='one'
            )
            
            if session:
                session_dict = dict(session)
                session_dict['categories'] = json.loads(session_dict['categories'])
                session_dict['questions'] = json.loads(session_dict['questions'])
                return session_dict
            return None
            
        except Exception as e:
            logger.error(f"Virhe testi-session haussa: {e}")
            return None

    def get_all_categories(self):
        """Hae kaikki kategoriat kysymysmäärien kanssa"""
        try:
            rows = self._execute("""
                SELECT 
                    category as name,
                    COUNT(*) as question_count
                FROM questions
                WHERE status = 'approved' OR status = 'validated'
                GROUP BY category
                ORDER BY category
            """, fetch='all')
            
            return [dict(row) for row in rows] if rows else []
            
        except Exception as e:
            logger.error(f"Virhe kategorioiden haussa: {e}")
            return []