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
        """Suorittaa tarvittavat tietokantamigraatiot."""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor if self.is_postgres else None) as cur:
                    if self.is_postgres:
                        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users' AND table_schema = 'public'")
                        user_columns = [row['column_name'] for row in cur.fetchall()]
                    else:
                        cur.execute("PRAGMA table_info(users)")
                        user_columns = [row['name'] for row in cur.fetchall()]
                    
                    if 'expires_at' not in user_columns:
                        self._execute("ALTER TABLE users ADD COLUMN expires_at TIMESTAMP")
        except Exception as e:
            logger.warning(f"Migraatiovirhe (voi olla normaali jos tauluja ei ole vielä luotu): {e}")

    def normalize_question(self, text):
        """Normalisoi kysymystekstin vertailua varten."""
        if not text: 
            return ""
        return " ".join(text.split()).lower().rstrip('?!. ')

    def create_user(self, username, email, hashed_password, expires_at=None):
        """Luo uuden käyttäjän ja käsittelee tietokantavirheet oikein."""
        try:
            # Tarkistetaan ensin, onko käyttäjiä olemassa
            count_result = self._execute("SELECT COUNT(*) as count FROM users", fetch='one')
            count = count_result['count'] if count_result else 0
            role = 'admin' if count == 0 else 'user'
            
            # Suoritetaan lisäys
            self._execute(
                "INSERT INTO users (username, email, password, role, expires_at) VALUES (?, ?, ?, ?, ?)",
                (username, email, hashed_password, role, expires_at)
            )
            return True, None
        except (psycopg2.IntegrityError, sqlite3.IntegrityError) as e:
            error_str = str(e).lower()
            if 'unique constraint' in error_str or 'duplicate key value' in error_str:
                if 'username' in error_str:
                    return False, "UNIQUE constraint failed: users.username"
                elif 'email' in error_str:
                    return False, "UNIQUE constraint failed: users.email"
            return False, str(e)
        except (psycopg2.Error, sqlite3.Error) as e:
            logger.error(f"Odottamaton tietokantavirhe käyttäjän luonnissa: {e}")
            return False, str(e)

    def get_user_by_id(self, user_id):
        """Hakee käyttäjän ID:n perusteella."""
        return self._execute("SELECT * FROM users WHERE id = ?", (user_id,), fetch='one')

    def get_user_by_username(self, username):
        """Hakee käyttäjän käyttäjänimen perusteella."""
        return self._execute("SELECT * FROM users WHERE username = ?", (username,), fetch='one')

    def get_user_by_email(self, email):
        """Hakee käyttäjän sähköpostin perusteella."""
        return self._execute("SELECT * FROM users WHERE email = ?", (email,), fetch='one')

    def get_all_users_for_admin(self):
        """Hakee kaikki käyttäjät admin-näkymää varten."""
        return self._execute(
            "SELECT id, username, email, role, status, created_at, distractors_enabled, distractor_probability, expires_at FROM users ORDER BY id", 
            fetch='all'
        )

    def get_next_test_user_number(self):
        """Palauttaa seuraavan vapaan testuser-numeron."""
        try:
            test_users = self._execute("SELECT username FROM users WHERE username LIKE 'testuser%'", fetch='all')
            if not test_users: 
                return 1
            max_num = 0
            for user in test_users:
                num_part = user['username'].replace('testuser', '')
                if num_part.isdigit():
                    num = int(num_part)
                    if num > max_num: 
                        max_num = num
            return max_num + 1
        except Exception as e:
            logger.error(f"Virhe testuser-numeron haussa: {e}")
            return 1

    def update_user_password(self, user_id, new_hashed_password):
        """Päivittää käyttäjän salasanan."""
        try:
            self._execute("UPDATE users SET password = ? WHERE id = ?", (new_hashed_password, user_id))
            return True, None
        except Exception as e:
            logger.error(f"Virhe salasanan päivityksessä: {e}")
            return False, str(e)

    def update_user_role(self, user_id, new_role):
        """Päivittää käyttäjän roolin."""
        try:
            self._execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
            return True, None
        except Exception as e:
            logger.error(f"Virhe roolin päivityksessä: {e}")
            return False, str(e)

    def update_user(self, user_id, data):
        """Päivittää käyttäjän tietoja."""
        try:
            set_clauses = []
            update_params = []
            if 'distractors_enabled' in data:
                set_clauses.append("distractors_enabled = ?")
                update_params.append(bool(data['distractors_enabled']))
            if 'distractor_probability' in data:
                set_clauses.append("distractor_probability = ?")
                update_params.append(max(0, min(100, int(data['distractor_probability']))))
            
            if not set_clauses: 
                return True, None
            
            query = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = ?"
            update_params.append(user_id)
            self._execute(query, tuple(update_params))
            return True, None
        except Exception as e:
            logger.error(f"Virhe käyttäjätietojen päivityksessä: {e}")
            return False, str(e)

    def update_user_practice_preferences(self, user_id, categories, difficulties):
        """Tallentaa käyttäjän harjoittelupreferenssit."""
        try:
            self._execute(
                "UPDATE users SET last_practice_categories = ?, last_practice_difficulties = ? WHERE id = ?", 
                (json.dumps(categories), json.dumps(difficulties), user_id)
            )
            return True, None
        except Exception as e:
            logger.error(f"Virhe preferenssien tallennuksessa: {e}")
            return False, str(e)

    def delete_user_by_id(self, user_id):
        """Poistaa käyttäjän ja kaikki siihen liittyvät tiedot."""
        try:
            # Poistetaan ensin viiteavaimet
            self._execute("DELETE FROM user_question_progress WHERE user_id = ?", (user_id,))
            self._execute("DELETE FROM question_attempts WHERE user_id = ?", (user_id,))
            self._execute("DELETE FROM active_sessions WHERE user_id = ?", (user_id,))
            self._execute("DELETE FROM user_achievements WHERE user_id = ?", (user_id,))
            # Poistetaan itse käyttäjä
            self._execute("DELETE FROM users WHERE id = ?", (user_id,))
            return True, None
        except Exception as e:
            logger.error(f"Virhe käyttäjän poistossa: {e}")
            return False, str(e)

    def get_categories(self):
        """Hakee kaikki kategoriat tietokannasta."""
        rows = self._execute("SELECT DISTINCT category FROM questions ORDER BY category", fetch='all')
        return [row['category'] for row in rows] if rows else []

    # =========================================================================
    # TÄMÄ FUNKTIO ON KORJATTU ✅
    # =========================================================================
    def get_questions(self, user_id, categories=None, difficulties=None, limit=10):
        """Hakee satunnaisia kysymyksiä tehokkaasti annettujen suodattimien perusteella."""
        try:
            limit = int(limit) # Varmista, että limit on kokonaisluku
            logger.info(f"Fetching {limit} questions for user_id={user_id}, categories={categories}, difficulties={difficulties}")
            
            # --- Vaihe 1: Hae vain suodatusta vastaavien kysymysten ID:t ---
            query_ids = "SELECT id FROM questions"
            params = []
            where_clauses = []

            if categories and isinstance(categories, list) and 'Kaikki kategoriat' not in categories and len(categories) > 0:
                placeholders = ', '.join([self.param_style] * len(categories))
                where_clauses.append(f"category IN ({placeholders})")
                params.extend(categories)

            if difficulties and isinstance(difficulties, list) and len(difficulties) > 0:
                placeholders = ', '.join([self.param_style] * len(difficulties))
                where_clauses.append(f"difficulty IN ({placeholders})")
                params.extend(difficulties)

            if where_clauses:
                query_ids += " WHERE " + " AND ".join(where_clauses)

            id_rows = self._execute(query_ids, tuple(params), fetch='all')
            
            if not id_rows:
                logger.warning("No question IDs found for the given filters.")
                return []

            question_ids = [row['id'] for row in id_rows]
            
            # --- Vaihe 2: Sekoita ID:t ja valitse haluttu määrä ---
            random.shuffle(question_ids)
            selected_ids = question_ids[:limit]

            if not selected_ids:
                return []

            # --- Vaihe 3: Hae valittujen ID:iden täydet tiedot ---
            final_query_placeholders = ', '.join([self.param_style] * len(selected_ids))
            final_query = f"""
                SELECT q.*, 
                       COALESCE(p.times_shown, 0) as times_shown, 
                       COALESCE(p.times_correct, 0) as times_correct, 
                       COALESCE(p.ease_factor, 2.5) as ease_factor, 
                       COALESCE(p.interval, 1) as interval
                FROM questions q 
                LEFT JOIN user_question_progress p ON q.id = p.question_id AND p.user_id = {self.param_style}
                WHERE q.id IN ({final_query_placeholders})
            """
            
            final_params = [user_id] + selected_ids
            rows = self._execute(final_query, tuple(final_params), fetch='all')

            questions = []
            if rows:
                for row in rows:
                    try:
                        row_dict = dict(row)
                        row_dict['options'] = json.loads(row_dict.get('options', '[]'))
                        questions.append(Question(**row_dict))
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.error(f"Error processing question data for ID {row.get('id', 'N/A')}: {e}")
            
            # Sekoita lopullinen lista vielä kerran, koska IN-lauseke ei takaa järjestystä
            random.shuffle(questions)
            logger.info(f"Successfully fetched and processed {len(questions)} questions.")
            return questions

        except Exception as e:
            logger.error(f"Critical error in get_questions: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_question_by_id(self, question_id, user_id):
        """Hakee yksittäisen kysymyksen ID:n perusteella."""
        query = """
            SELECT q.*, 
                   COALESCE(p.times_shown, 0) as times_shown, 
                   COALESCE(p.times_correct, 0) as times_correct,
                   p.last_shown, 
                   COALESCE(p.ease_factor, 2.5) as ease_factor, 
                   COALESCE(p.interval, 1) as interval
            FROM questions q
            LEFT JOIN user_question_progress p ON q.id = p.question_id AND p.user_id = ?
            WHERE q.id = ?
        """
        row = self._execute(query, (user_id, question_id), fetch='one')
        if not row: 
            return None
        try:
            row_dict = dict(row)
            row_dict['options'] = json.loads(row_dict['options']) if row_dict['options'] else []
            return Question(**row_dict)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Virhe Question-objektin luonnissa ID:llä {question_id}: {e}")
            return None

    def update_question_stats(self, question_id, is_correct, time_taken, user_id):
        """Päivittää kysymyksen tilastot käyttäjälle."""
        try:
            if self.is_postgres:
                self._execute(
                    "INSERT INTO user_question_progress (user_id, question_id) VALUES (?, ?) ON CONFLICT (user_id, question_id) DO NOTHING", 
                    (user_id, question_id)
                )
            else:
                self._execute(
                    "INSERT OR IGNORE INTO user_question_progress (user_id, question_id) VALUES (?, ?)", 
                    (user_id, question_id)
                )
            
            self._execute(
                "UPDATE user_question_progress SET times_shown = times_shown + 1, times_correct = times_correct + ?, last_shown = ? WHERE user_id = ? AND question_id = ?",
                (1 if is_correct else 0, datetime.now(), user_id, question_id)
            )
            self._execute(
                "INSERT INTO question_attempts (user_id, question_id, correct, time_taken) VALUES (?, ?, ?, ?)",
                (user_id, question_id, bool(is_correct), time_taken)
            )
        except Exception as e:
            logger.error(f"Virhe päivitettäessä kysymystilastoja: {e}")

    def check_question_duplicate(self, question_text):
        """Tarkistaa onko samanlainen kysymys jo olemassa."""
        try:
            normalized = self.normalize_question(question_text)
            existing = self._execute(
                "SELECT id, question, category FROM questions WHERE question_normalized = ?", 
                (normalized,), 
                fetch='one'
            )
            if existing:
                return True, dict(existing)
            return False, None
        except Exception as e:
            logger.error(f"Virhe duplikaattitarkistuksessa: {e}")
            return False, None

    def bulk_add_questions(self, questions_data):
        """Lisää useita kysymyksiä kerralla."""
        stats = {'added': 0, 'duplicates': 0, 'skipped': 0, 'errors': []}
        
        for q_data in questions_data:
            try:
                # Validoi pakollliset kentät
                required_fields = ['question', 'explanation', 'options', 'correct', 'category', 'difficulty']
                if not all(field in q_data for field in required_fields):
                    stats['skipped'] += 1
                    stats['errors'].append(f"Puutteelliset tiedot: {q_data.get('question', 'N/A')[:50]}")
                    continue
                
                # Tarkista duplikaatti
                is_dup, _ = self.check_question_duplicate(q_data['question'])
                if is_dup:
                    stats['duplicates'] += 1
                    continue
                
                # Lisää kysymys
                normalized = self.normalize_question(q_data['question'])
                options_json = json.dumps(q_data['options'])
                
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
                # PostgreSQL ja SQLite palauttavat eri tavalla - ei lasketa tässä
            
            # Laske lopputulema
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