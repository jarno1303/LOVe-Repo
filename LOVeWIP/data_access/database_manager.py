# data_access/database_manager.py
# -*- coding: utf-8 -*-
import sqlite3
import json
import os
import logging
from datetime import datetime
from models.models import Question # Varmista, että models.py on ajan tasalla
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

        try:
            # Suoritetaan migraatiot heti alussa
            self.migrate_database()
        except Exception as e:
            logger.error(f"Tietokannan alustus tai migraatio epäonnistui käynnistyksessä: {e}")
            raise # Pysäytä sovellus, jos migraatio epäonnistuu

    def get_connection(self):
        """Luo ja palauttaa tietokantayhteyden."""
        try:
            if self.is_postgres:
                if not self.database_url:
                    raise ValueError("DATABASE_URL-ympäristömuuttujaa ei ole asetettu.")
                return psycopg2.connect(self.database_url)
            else:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row # Käytä Row-objekteja SQLite:ssa
                return conn
        except Exception as e:
            logger.error(f"KRIITTINEN VIRHE: Tietokantayhteyden luonti epäonnistui: {e}")
            raise

    def _execute(self, query, params=(), fetch=None):
        """
        Suorittaa SQL-kyselyn ja palauttaa tulokset.
        Huolehtii parametrien oikeasta muodosta sekä PostgreSQL:lle että SQLite:lle.
        Käyttää DictCursoria PostgreSQL:lle ja sqlite3.Row SQLite:lle.
        """
        query = query.replace('?', self.param_style)
        conn = self.get_connection()
        try:
            with conn:
                # Käytä oikeaa cursor_factorya tietokannan mukaan
                cursor_factory = DictCursor if self.is_postgres else None
                # SQLite:ssa row_factory hoitaa rivien muodon
                with conn.cursor(cursor_factory=cursor_factory) as cur:
                    cur.execute(query, params)
                    if fetch == 'one':
                        result = cur.fetchone()
                        # Muunna sqlite3.Row Dictiksi yhteensopivuuden vuoksi
                        return dict(result) if result and not self.is_postgres else result
                    if fetch == 'all':
                        results = cur.fetchall()
                        # Muunna sqlite3.Row Dictiksi yhteensopivuuden vuoksi
                        return [dict(row) for row in results] if results and not self.is_postgres else results
        except (psycopg2.Error, sqlite3.Error) as e:
            logger.error(f"Tietokantavirhe kyselyssä '{query[:100]}...': {e}")
            raise # Heitä virhe eteenpäin, jotta Flask voi käsitellä sen
        finally:
            if conn:
                conn.close()

    def init_database(self):
        """
        Luo kaikki tarvittavat tietokantataulut, mukaan lukien organizations.
        Päivittää users-taulun.
        """
        id_type = "SERIAL PRIMARY KEY" if self.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        bool_type = "BOOLEAN" if self.is_postgres else "INTEGER"
        fk_type = "INTEGER" # Yhteensopiva molemmille
        timestamp_type = "TIMESTAMP WITH TIME ZONE" if self.is_postgres else "TIMESTAMP"
        current_timestamp = "CURRENT_TIMESTAMP" if self.is_postgres else "DATETIME('now')"


        # Käytä yhtä transaktiota tehokkuuden ja atomisuuden vuoksi
        conn = self.get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    # Organizations taulu ensin
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS organizations (
                            id {id_type},
                            name TEXT NOT NULL UNIQUE,
                            contact_person TEXT,
                            contact_email TEXT,
                            created_at {timestamp_type} DEFAULT {current_timestamp},
                            status TEXT NOT NULL DEFAULT 'active' -- active, inactive
                        );
                    """)
                    logger.info("Tarkistettu/Luotu organizations-taulu.")

                    # Users taulu
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS users (
                            id {id_type},
                            username TEXT NOT NULL UNIQUE,
                            email TEXT NOT NULL UNIQUE,
                            password TEXT NOT NULL,
                            role TEXT NOT NULL DEFAULT 'user', -- user, admin, superuser
                            status TEXT NOT NULL DEFAULT 'active', -- active, inactive
                            organization_id {fk_type},
                            distractors_enabled {bool_type} NOT NULL DEFAULT true,
                            distractor_probability INTEGER NOT NULL DEFAULT 25,
                            last_practice_categories TEXT,
                            last_practice_difficulties TEXT,
                            created_at {timestamp_type} DEFAULT {current_timestamp},
                            expires_at {timestamp_type},
                            CONSTRAINT fk_organization
                                FOREIGN KEY (organization_id)
                                REFERENCES organizations(id)
                                ON DELETE SET NULL
                        );
                    """)
                    logger.info("Tarkistettu/Luotu users-taulu.")

                    # Muut taulut
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS questions (
                            id {id_type},
                            question TEXT NOT NULL,
                            question_normalized TEXT,
                            explanation TEXT NOT NULL,
                            options TEXT NOT NULL, -- JSON-merkkijono
                            correct INTEGER NOT NULL,
                            category TEXT NOT NULL,
                            difficulty TEXT NOT NULL,
                            created_at {timestamp_type} DEFAULT {current_timestamp},
                            hint_type TEXT,
                            status TEXT DEFAULT 'validated', -- needs_review, validated
                            validated_by INTEGER,
                            validated_at {timestamp_type},
                            validation_comment TEXT
                        );
                    """)
                    logger.info("Tarkistettu/Luotu questions-taulu.")

                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS user_question_progress (
                            user_id INTEGER NOT NULL,
                            question_id INTEGER NOT NULL,
                            times_shown INTEGER DEFAULT 0,
                            times_correct INTEGER DEFAULT 0,
                            last_shown {timestamp_type},
                            ease_factor REAL DEFAULT 2.5,
                            interval INTEGER DEFAULT 1,
                            mistake_acknowledged {bool_type} DEFAULT FALSE,
                            PRIMARY KEY (user_id, question_id),
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
                        );
                    """)
                    logger.info("Tarkistettu/Luotu user_question_progress-taulu.")

                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS question_attempts (
                            id {id_type},
                            user_id INTEGER NOT NULL,
                            question_id INTEGER NOT NULL,
                            correct {bool_type} NOT NULL,
                            time_taken REAL NOT NULL, -- sekunteina
                            timestamp {timestamp_type} DEFAULT {current_timestamp},
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
                        );
                    """)
                    logger.info("Tarkistettu/Luotu question_attempts-taulu.")

                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS active_sessions (
                            user_id INTEGER PRIMARY KEY,
                            session_type TEXT NOT NULL,
                            question_ids TEXT NOT NULL, -- JSON list of ids
                            answers TEXT NOT NULL, -- JSON list of answers
                            current_index INTEGER NOT NULL,
                            time_remaining INTEGER NOT NULL, -- sekunteina
                            last_updated {timestamp_type} DEFAULT {current_timestamp},
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                        );
                    """)
                    logger.info("Tarkistettu/Luotu active_sessions-taulu.")

                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS user_achievements (
                            user_id INTEGER NOT NULL,
                            achievement_id TEXT NOT NULL,
                            unlocked_at {timestamp_type} DEFAULT {current_timestamp},
                            PRIMARY KEY (user_id, achievement_id),
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                        );
                    """)
                    logger.info("Tarkistettu/Luotu user_achievements-taulu.")

                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS distractor_attempts (
                            id {id_type},
                            user_id INTEGER NOT NULL,
                            distractor_scenario TEXT NOT NULL,
                            user_choice INTEGER NOT NULL,
                            correct_choice INTEGER NOT NULL,
                            is_correct {bool_type} NOT NULL,
                            response_time INTEGER, -- millisekunteina
                            created_at {timestamp_type} DEFAULT {current_timestamp},
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                        );
                    """)
                    logger.info("Tarkistettu/Luotu distractor_attempts-taulu.")

                    # Indeksit (lisätään erikseen virheiden välttämiseksi, jos ne ovat jo olemassa)
                    index_commands = [
                        "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);",
                        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
                        "CREATE INDEX IF NOT EXISTS idx_users_organization_id ON users(organization_id);",
                        "CREATE INDEX IF NOT EXISTS idx_questions_category ON questions(category);",
                        "CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty);",
                        "CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);",
                        "CREATE INDEX IF NOT EXISTS idx_qa_user_timestamp ON question_attempts(user_id, timestamp);",
                        "CREATE INDEX IF NOT EXISTS idx_uqp_last_shown ON user_question_progress(last_shown);",
                    ]
                    for cmd in index_commands:
                        try:
                            cur.execute(cmd)
                        except (psycopg2.Error, sqlite3.Error) as idx_e:
                            # Usein tapahtuu, jos indeksi on jo olemassa, ei haittaa
                            logger.debug(f"Indeksin luonti epäonnistui (mahdollisesti jo olemassa): {idx_e}")

                    logger.info("Tietokannan alustus valmis.")

        except (psycopg2.Error, sqlite3.Error) as e:
            logger.error(f"Kriittinen virhe tietokannan alustuksessa: {e}")
            raise
        finally:
            conn.close()

    def migrate_database(self):
        """
        Lisää puuttuvat sarakkeet olemassa oleviin tauluihin.
        Tarkistaa ensin, onko sarake jo olemassa.
        """
        logger.info("Aloitetaan tietokannan migraatio...")
        # (A) Varmista organizations-taulun olemassaolo ensin
        try:
            id_type = "SERIAL PRIMARY KEY" if self.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
            timestamp_type = "TIMESTAMP WITH TIME ZONE" if self.is_postgres else "TIMESTAMP"
            current_timestamp = "CURRENT_TIMESTAMP" if self.is_postgres else "DATETIME('now')"
            self._execute(f"""
                CREATE TABLE IF NOT EXISTS organizations (
                    id {id_type}, name TEXT NOT NULL UNIQUE, contact_person TEXT,
                    contact_email TEXT, created_at {timestamp_type} DEFAULT {current_timestamp},
                    status TEXT NOT NULL DEFAULT 'active'
                );
            """)
            logger.info("Tarkistettu/Luotu organizations-taulu migraatiossa.")
        except Exception as e:
            # Voi epäonnistua jos taulu on jo olemassa, mikä on ok.
            if "already exists" not in str(e).lower():
                logger.error(f"Virhe organizations-taulun luonnissa migraatiossa: {e}")
                # Ei heitetä virhettä, yritetään jatkaa muiden sarakkeiden kanssa

        # (B) Lisää sarakkeet olemassa oleviin tauluihin
        fk_type = "INTEGER"
        bool_type = "BOOLEAN DEFAULT false" if self.is_postgres else "INTEGER DEFAULT 0"
        timestamp_type = "TIMESTAMP WITH TIME ZONE" if self.is_postgres else "TIMESTAMP"

        self._add_column_if_not_exists('users', 'organization_id', fk_type)
        self._add_column_if_not_exists('user_question_progress', 'mistake_acknowledged', bool_type)
        self._add_column_if_not_exists('questions', 'status', "TEXT DEFAULT 'validated'")
        self._add_column_if_not_exists('questions', 'validated_by', 'INTEGER')
        self._add_column_if_not_exists('questions', 'validated_at', timestamp_type)
        self._add_column_if_not_exists('questions', 'validation_comment', 'TEXT')
        # Lisää questions.question_normalized jos se puuttuu
        self._add_column_if_not_exists('questions', 'question_normalized', 'TEXT')

        # Varmista, että vanhoilla kysymyksillä on normalisoitu arvo
        try:
            unnormalized = self._execute("SELECT id, question FROM questions WHERE question_normalized IS NULL", fetch='all')
            if unnormalized:
                logger.info(f"Normalisoidaan {len(unnormalized)} olemassa olevaa kysymystä...")
                for row in unnormalized:
                    normalized_text = self.normalize_question(row['question'])
                    self._execute("UPDATE questions SET question_normalized = ? WHERE id = ?", (normalized_text, row['id']))
                logger.info("Vanhat kysymykset normalisoitu.")
        except Exception as e:
            logger.warning(f"Virhe vanhojen kysymysten normalisoinnissa: {e}")

        logger.info("Tietokannan migraatio valmis.")

    def _add_column_if_not_exists(self, table_name, column_name, column_type):
        """Apufunktio sarakkeen lisäämiseksi, jos sitä ei ole olemassa."""
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor if self.is_postgres else None) as cur:
                    column_exists = False
                    if self.is_postgres:
                        # PostgreSQL: Tarkista information_schema
                        cur.execute("""
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
                        """, (table_name.lower(), column_name.lower()))
                        if cur.fetchone():
                            column_exists = True
                    else:
                        # SQLite: Käytä PRAGMA table_info
                        cur.execute(f"PRAGMA table_info({table_name})")
                        columns = [row[1].lower() for row in cur.fetchall()] # Vertaile pienillä kirjaimilla
                        if column_name.lower() in columns:
                            column_exists = True

                    if not column_exists:
                        logger.info(f"Lisätään sarake '{column_name}' tauluun '{table_name}'...")
                        # Käytä _executeä ?-/%s muunnoksen vuoksi
                        self._execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                        logger.info(f"Sarake '{column_name}' lisätty onnistuneesti.")
                    else:
                        logger.debug(f"Sarake '{column_name}' on jo olemassa taulussa '{table_name}'. Ohitetaan.")

        except Exception as e:
            # Jos taulua ei ole (esim. ensimmäinen ajo), se on ok
            if "no such table" in str(e).lower() or "does not exist" in str(e).lower() or "relation" in str(e).lower() and "does not exist" in str(e).lower():
                logger.warning(f"Taulua '{table_name}' ei löytynyt sarakkeen '{column_name}' lisäyksen yhteydessä (mahdollisesti luodaan myöhemmin). Ohitetaan.")
            else:
                logger.error(f"Virhe lisättäessä saraketta '{column_name}' tauluun '{table_name}': {e}")
                raise # Heitä virhe eteenpäin

    def normalize_question(self, text):
        """Normalisoi kysymystekstin vertailua varten (poistaa välilyönnit, pienet kirjaimet)."""
        if not text:
            return ""
        # Poista välimerkit ja ylimääräiset välilyönnit, muunna pieniksi kirjaimiksi
        import re
        text = re.sub(r'[^\w\s]', '', text) # Poista välimerkit paitsi välilyönnit
        return " ".join(text.split()).lower()

    def create_user(self, username, email, hashed_password, role='user', organization_id=None, expires_at=None):
        """
        Luo uuden käyttäjän ja liittää hänet organisaatioon.
        Huom: Superuser-roolia EI voi asettaa tätä kautta turvallisuussyistä.
        """
        try:
            # Varmista, että rooli on sallittu
            role = role if role in ['user', 'admin'] else 'user'

            # Jos rooli on 'admin', organization_id on pakollinen
            if role == 'admin' and organization_id is None:
                return False, "Admin-käyttäjälle (opettaja) täytyy määrittää organisaatio."

            # Tarkista, onko organisaatio olemassa, jos ID annettiin
            if organization_id:
                 org = self._execute("SELECT id FROM organizations WHERE id = ?", (organization_id,), fetch='one')
                 if not org:
                     return False, f"Organisaatiota ID:llä {organization_id} ei löydy."

            # Tarkista, onko tämä ensimmäinen käyttäjä (potentiaalinen superuser)
            user_count_result = self._execute("SELECT COUNT(*) as count FROM users", fetch='one')
            user_count = user_count_result['count'] if user_count_result else 0

            # HUOM: Superuser luodaan manuaalisesti tai erillisellä skriptillä.
            # Tämä funktio luo vain 'user' tai 'admin' rooleja.
            # if user_count == 0:
            #     role = 'superuser' # ÄLÄ TEE NÄIN AUTOMAATTISESTI TÄSSÄ

            self._execute(
                "INSERT INTO users (username, email, password, role, organization_id, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                (username, email, hashed_password, role, organization_id, expires_at)
            )
            logger.info(f"Käyttäjä '{username}' luotu roolilla '{role}'" + (f" organisaatioon ID {organization_id}." if organization_id else "."))
            return True, None
        except (psycopg2.IntegrityError, sqlite3.IntegrityError) as e:
            error_str = str(e).lower()
            if 'unique constraint' in error_str or 'duplicate key value' in error_str:
                if 'username' in error_str:
                    logger.warning(f"Käyttäjän luonti epäonnistui: Käyttäjänimi '{username}' on varattu.")
                    return False, "Käyttäjänimi on jo käytössä."
                elif 'email' in error_str:
                    logger.warning(f"Käyttäjän luonti epäonnistui: Sähköposti '{email}' on varattu.")
                    return False, "Sähköpostiosoite on jo käytössä."
            logger.error(f"Odottamaton IntegrityError käyttäjän '{username}' luonnissa: {e}")
            return False, f"Tietokantavirhe: {e}"
        except Exception as e:
            logger.error(f"Odottamaton virhe käyttäjän '{username}' luonnissa: {e}", exc_info=True)
            return False, f"Odottamaton virhe: {e}"

    def get_user_by_id(self, user_id):
        """Hakee käyttäjän ID:n perusteella, mukaan lukien organization_id."""
        return self._execute("SELECT * FROM users WHERE id = ?", (user_id,), fetch='one')

    def get_user_by_username(self, username):
        """Hakee käyttäjän käyttäjänimen perusteella, mukaan lukien organization_id."""
        return self._execute("SELECT * FROM users WHERE username = ?", (username,), fetch='one')

    def get_user_by_email(self, email):
        """Hakee käyttäjän sähköpostin perusteella."""
        return self._execute("SELECT * FROM users WHERE email = ?", (email,), fetch='one')

    def get_users_for_organization(self, organization_id):
        """Hakee kaikki AKTIIVISET käyttäjät tietystä organisaatiosta admin-näkymää varten."""
        return self._execute(
            """SELECT u.id, u.username, u.email, u.role, u.status, u.created_at,
                      u.distractors_enabled, u.distractor_probability, u.expires_at,
                      o.name as organization_name
               FROM users u
               LEFT JOIN organizations o ON u.organization_id = o.id
               WHERE u.organization_id = ? AND u.status = 'active'
               ORDER BY u.username""",
            (organization_id,),
            fetch='all'
        )

    def get_all_active_users_for_superuser(self):
        """Hakee kaikki AKTIIVISET käyttäjät superuserille."""
        return self._execute(
            """SELECT u.id, u.username, u.email, u.role, u.status, u.created_at,
                      u.expires_at, o.name as organization_name
               FROM users u
               LEFT JOIN organizations o ON u.organization_id = o.id
               WHERE u.status = 'active'
               ORDER BY o.name, u.username""",
            fetch='all'
        )

    def get_all_organizations(self):
        """Hakee kaikki organisaatiot superuserille."""
        return self._execute(
             """SELECT o.*, COUNT(u.id) as user_count
                FROM organizations o
                LEFT JOIN users u ON o.id = u.organization_id AND u.status = 'active'
                WHERE o.status = 'active'
                GROUP BY o.id
                ORDER BY o.name""",
             fetch='all'
        )

    def create_organization(self, name, contact_person=None, contact_email=None):
        """Luo uuden organisaation."""
        try:
            self._execute(
                "INSERT INTO organizations (name, contact_person, contact_email) VALUES (?, ?, ?)",
                (name, contact_person, contact_email)
            )
            logger.info(f"Organisaatio '{name}' luotu.")
            return True, None
        except (psycopg2.IntegrityError, sqlite3.IntegrityError) as e:
            logger.warning(f"Organisaation '{name}' luonti epäonnistui: Nimi on jo käytössä.")
            return False, "Organisaation nimi on jo käytössä."
        except Exception as e:
            logger.error(f"Virhe organisaation '{name}' luonnissa: {e}", exc_info=True)
            return False, f"Odottamaton virhe: {e}"

    def update_user_password(self, user_id, new_hashed_password):
        """Päivittää käyttäjän salasanan."""
        try:
            self._execute("UPDATE users SET password = ? WHERE id = ?", (new_hashed_password, user_id))
            logger.info(f"Käyttäjän ID {user_id} salasana päivitetty.")
            return True, None
        except Exception as e:
            logger.error(f"Virhe salasanan päivityksessä käyttäjälle ID {user_id}: {e}", exc_info=True)
            return False, f"Odottamaton virhe: {e}"

    def update_user_role(self, user_id, new_role):
        """Päivittää käyttäjän roolin (vain 'user' tai 'admin'). Superuser-rooli asetetaan manuaalisesti."""
        if new_role not in ['user', 'admin']:
            logger.warning(f"Yritettiin asettaa virheellinen rooli '{new_role}' käyttäjälle ID {user_id}.")
            return False, "Virheellinen rooli."
        try:
            # Varmista, että admin-rooliin liitetään organisaatio
            if new_role == 'admin':
                user = self.get_user_by_id(user_id)
                if not user or not user.get('organization_id'):
                    return False, "Admin-rooli vaatii organisaation."

            self._execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
            logger.info(f"Käyttäjän ID {user_id} rooli päivitetty: {new_role}.")
            return True, None
        except Exception as e:
            logger.error(f"Virhe roolin päivityksessä käyttäjälle ID {user_id}: {e}", exc_info=True)
            return False, f"Odottamaton virhe: {e}"

    def update_user(self, user_id, data):
        """Päivittää käyttäjän tietoja (esim. asetukset)."""
        set_clauses = []
        update_params = []
        valid_keys = ['distractors_enabled', 'distractor_probability', 'email', 'expires_at', 'organization_id', 'status'] # Sallitut päivitettävät kentät

        for key, value in data.items():
            if key in valid_keys:
                set_clauses.append(f"{key} = ?")
                if key == 'distractors_enabled':
                    update_params.append(bool(value))
                elif key == 'distractor_probability':
                    update_params.append(max(0, min(100, int(value))))
                elif key == 'expires_at':
                    # Varmista, että arvo on None tai datetime-objekti
                    update_params.append(value if isinstance(value, datetime) or value is None else None)
                else:
                    update_params.append(value)
            else:
                logger.warning(f"Yritettiin päivittää tuntematon kenttä '{key}' käyttäjälle ID {user_id}.")

        if not set_clauses:
            logger.info(f"Ei päivitettäviä kenttiä käyttäjälle ID {user_id}.")
            return True, None # Ei virhe, mutta mitään ei tehty

        query = f"UPDATE users SET {', '.join(set_clauses)} WHERE id = ?"
        update_params.append(user_id)

        try:
            self._execute(query, tuple(update_params))
            logger.info(f"Käyttäjän ID {user_id} tiedot päivitetty: {', '.join(data.keys())}.")
            return True, None
        except Exception as e:
            logger.error(f"Virhe käyttäjätietojen päivityksessä ID {user_id}: {e}", exc_info=True)
            return False, f"Odottamaton virhe: {e}"

    def update_user_practice_preferences(self, user_id, categories, difficulties):
        """Tallentaa käyttäjän harjoittelupreferenssit."""
        try:
            self._execute(
                "UPDATE users SET last_practice_categories = ?, last_practice_difficulties = ? WHERE id = ?",
                (json.dumps(categories), json.dumps(difficulties), user_id)
            )
            return True, None
        except Exception as e:
            logger.error(f"Virhe preferenssien tallennuksessa käyttäjälle ID {user_id}: {e}", exc_info=True)
            return False, f"Odottamaton virhe: {e}"

    def deactivate_user(self, user_id):
        """
        Poistaa käyttäjän käytöstä (soft delete) asettamalla tilan 'inactive'.
        Tämä on oletustapa adminille poistaa käyttäjä.
        """
        # Estä pääkäyttäjän deaktivointi (oletetaan ID 1) tai itsensä deaktivointi
        if user_id == 1: # Tai tarkista roolin perusteella, jos ID voi vaihdella
             logger.warning("Yritettiin deaktivoida pääkäyttäjää (ID 1).")
             return False, "Pääkäyttäjää ei voi deaktivoida."

        try:
            result = self._execute("UPDATE users SET status = 'inactive' WHERE id = ?", (user_id,))
            # _execute ei palauta rivien määrää suoraan, tarkista käyttäjä haulla jos tarpeen
            user_check = self.get_user_by_id(user_id)
            if user_check and user_check['status'] == 'inactive':
                logger.info(f"Käyttäjä ID {user_id} deaktivoitu (soft delete).")
                return True, None
            elif not user_check:
                 logger.warning(f"Käyttäjää ID {user_id} ei löytynyt deaktivointia varten.")
                 return False, "Käyttäjää ei löytynyt."
            else:
                 logger.error(f"Käyttäjän ID {user_id} deaktivointi epäonnistui tuntemattomasta syystä.")
                 return False, "Deaktivointi epäonnistui."
        except Exception as e:
            logger.error(f"Virhe käyttäjän ID {user_id} deaktivoinnissa: {e}", exc_info=True)
            return False, f"Odottamaton virhe: {e}" 
    
    def reactivate_user(self, user_id):
        """
        UUSI FUNKTIO: Palauttaa 'inactive'-tilassa olevan käyttäjän 'active'-tilaan.
        """
        try:
            # Varmista ensin, että käyttäjä on olemassa ja inaktiivinen
            user = self.get_user_by_id(user_id)
            if not user:
                logger.warning(f"Yritettiin aktivoida olematonta käyttäjää ID {user_id}.")
                return False, "Käyttäjää ei löytynyt."
            if user['status'] == 'active':
                logger.info(f"Käyttäjä ID {user_id} on jo aktiivinen.")
                return True, None # Ei virhe, mutta mitään ei tarvinnut tehdä

            # Päivitä status
            result = self._execute("UPDATE users SET status = 'active' WHERE id = ?", (user_id,))
            
            # Varmista päivitys (tarpeellinen, koska _execute ei palauta rivimäärää helposti)
            updated_user = self.get_user_by_id(user_id)
            if updated_user and updated_user['status'] == 'active':
                logger.info(f"Käyttäjä ID {user_id} aktivoitu uudelleen.")
                return True, None
            else:
                 logger.error(f"Käyttäjän ID {user_id} aktivointi epäonnistui tietokantapäivityksen jälkeen.")
                 return False, "Aktivointi epäonnistui tietokantatasolla."
                 
        except Exception as e:
            logger.error(f"Virhe käyttäjän ID {user_id} aktivoinnissa: {e}", exc_info=True)
            return False, f"Odottamaton virhe aktivoinnissa: {e}"

    def hard_delete_user(self, user_id):
        """
        Poistaa käyttäjän ja kaikki hänen tietonsa pysyvästi.
        TÄTÄ SAA KUTSUA VAIN SUPERUSER varmistuksen jälkeen.
        """
        # Estä pääkäyttäjän poisto
        if user_id == 1: # Tai roolin perusteella
             logger.critical("KRIITTINEN: Yritettiin POISTAA PYSYVÄSTI pääkäyttäjä (ID 1). Estetty.")
             return False, "Pääkäyttäjää ei voi poistaa pysyvästi."

        conn = self.get_connection()
        try:
            with conn: # Käytä transaktiota
                with conn.cursor() as cur:
                    logger.warning(f"Aloitetaan käyttäjän ID {user_id} PYSYVÄ POISTO...")
                    # Poista tiedot kaikista liitetyistä tauluista JÄRJESTYKSESSÄ
                    cur.execute(self.param_style.join(["DELETE FROM distractor_attempts WHERE user_id = ", ""]), (user_id,))
                    logger.debug(f"Poistettu distractor_attempts käyttäjälle {user_id}.")
                    cur.execute(self.param_style.join(["DELETE FROM user_question_progress WHERE user_id = ", ""]), (user_id,))
                    logger.debug(f"Poistettu user_question_progress käyttäjälle {user_id}.")
                    cur.execute(self.param_style.join(["DELETE FROM question_attempts WHERE user_id = ", ""]), (user_id,))
                    logger.debug(f"Poistettu question_attempts käyttäjälle {user_id}.")
                    cur.execute(self.param_style.join(["DELETE FROM active_sessions WHERE user_id = ", ""]), (user_id,))
                    logger.debug(f"Poistettu active_sessions käyttäjälle {user_id}.")
                    cur.execute(self.param_style.join(["DELETE FROM user_achievements WHERE user_id = ", ""]), (user_id,))
                    logger.debug(f"Poistettu user_achievements käyttäjälle {user_id}.")
                    # Voit lisätä tähän muiden taulujen tyhjennykset, esim. study_sessions

                    # Viimeisenä poista itse käyttäjä users-taulusta
                    cur.execute(self.param_style.join(["DELETE FROM users WHERE id = ", ""]), (user_id,))
                    logger.warning(f"Käyttäjä ID {user_id} POISTETTU PYSYVÄSTI.")

            return True, None
        except Exception as e:
            logger.error(f"Kriittinen virhe käyttäjän ID {user_id} pysyvässä poistossa: {e}", exc_info=True)
            # Rollback tapahtuu automaattisesti 'with conn' ansiosta
            return False, f"Odottamaton virhe pysyvässä poistossa: {e}"
        finally:
            conn.close()

    # --- Kysymysfunktiot ---

    def get_all_question_ids(self):
        """Hakee kaikkien kysymysten ID:t listana."""
        query = "SELECT id FROM questions WHERE status = 'validated'" # Hae vain validoidut
        rows = self._execute(query, fetch='all')
        return [row['id'] for row in rows] if rows else []

    def get_random_question_ids(self, limit=50):
        """Hakee satunnaisen listan validoitujen kysymysten ID:itä."""
        all_ids = self.get_all_question_ids()
        if not all_ids:
            logger.warning("Ei validoituja kysymyksiä tietokannassa.")
            return []

        actual_limit = min(len(all_ids), limit)
        return random.sample(all_ids, actual_limit)

    def get_question_by_id(self, question_id, user_id=None):
        """
        Hakee yksittäisen kysymyksen ID:n perusteella.
        Jos user_id annetaan, hakee myös käyttäjän edistymisen.
        """
        if user_id:
            query = """
                SELECT q.*,
                       COALESCE(p.times_shown, 0) as times_shown,
                       COALESCE(p.times_correct, 0) as times_correct,
                       p.last_shown,
                       COALESCE(p.ease_factor, 2.5) as ease_factor,
                       COALESCE(p.interval, 1) as interval,
                       COALESCE(p.mistake_acknowledged, FALSE) as mistake_acknowledged
                FROM questions q
                LEFT JOIN user_question_progress p ON q.id = p.question_id AND p.user_id = ?
                WHERE q.id = ?
            """
            params = (user_id, question_id)
        else:
            query = "SELECT * FROM questions WHERE id = ?"
            params = (question_id,)

        row = self._execute(query, params, fetch='one')
        if not row:
            logger.warning(f"Kysymystä ID {question_id} ei löytynyt.")
            return None

        try:
            # Muunna Dictiksi, jos ei jo ole (SQLite)
            row_dict = dict(row) if not isinstance(row, dict) else row
            row_dict['options'] = json.loads(row_dict.get('options', '[]'))
            # Lisää oletusarvot progress-kentille, jos user_id:tä ei annettu
            if user_id is None:
                row_dict.setdefault('times_shown', 0)
                row_dict.setdefault('times_correct', 0)
                row_dict.setdefault('last_shown', None)
                row_dict.setdefault('ease_factor', 2.5)
                row_dict.setdefault('interval', 1)
                row_dict.setdefault('mistake_acknowledged', False)
            return Question(**row_dict)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.error(f"Virhe Question-objektin luonnissa ID:llä {question_id}: {e}", exc_info=True)
            return None

    def get_categories(self):
        """
        Hakee kaikki kategoriat tietokannasta.
        Palauttaa listan dictionaryja muodossa [{'id': 1, 'name': 'Kategoria'}, ...]
        """
        try:
            rows = self._execute(
                "SELECT id, name FROM categories ORDER BY name",
                fetch='all'
            )
            
            if not rows:
                print("VAROITUS: Ei kategorioita tietokannassa!")
                return []
            
            # Muunna dict-muotoon
            categories = []
            for row in rows:
                if isinstance(row, dict):
                    categories.append({'id': row['id'], 'name': row['name']})
                else:
                    categories.append({'id': row[0], 'name': row[1]})
            
            print(f"INFO: Haettiin {len(categories)} kategoriaa")
            return categories
        except Exception as e:
            print(f"VIRHE: Kategorioiden haussa: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_questions(self, user_id, categories=None, difficulties=None, limit=10):
        """Hakee satunnaisia validoituja kysymyksiä tehokkaasti annettujen suodattimien perusteella."""
        try:
            limit = int(limit)

            # 1. Hae kelvollisten kysymysten ID:t suodattimilla
            query_ids = "SELECT id FROM questions WHERE status = 'validated'"
            params = []
            where_clauses = []

            if categories and 'Kaikki kategoriat' not in categories:
                placeholders = ', '.join([self.param_style] * len(categories))
                where_clauses.append(f"category IN ({placeholders})")
                params.extend(categories)

            if difficulties:
                placeholders = ', '.join([self.param_style] * len(difficulties))
                where_clauses.append(f"difficulty IN ({placeholders})")
                params.extend(difficulties)

            if where_clauses:
                query_ids += " AND " + " AND ".join(where_clauses)

            id_rows = self._execute(query_ids, tuple(params), fetch='all')

            if not id_rows:
                logger.warning(f"Ei kysymyksiä valituilla suodattimilla: categories={categories}, difficulties={difficulties}")
                return []

            question_ids = [row['id'] for row in id_rows]

            # 2. Arvo ID:t
            random.shuffle(question_ids)
            selected_ids = question_ids[:limit]

            if not selected_ids:
                return [] # Ei pitäisi tapahtua, jos id_rows ei ollut tyhjä

            # 3. Hae valittujen kysymysten täydet tiedot ja käyttäjän progress
            final_query_placeholders = ', '.join([self.param_style] * len(selected_ids))
            final_query = f"""
                SELECT q.*,
                       COALESCE(p.times_shown, 0) as times_shown,
                       COALESCE(p.times_correct, 0) as times_correct,
                       COALESCE(p.ease_factor, 2.5) as ease_factor,
                       COALESCE(p.interval, 1) as interval,
                       COALESCE(p.mistake_acknowledged, FALSE) as mistake_acknowledged
                FROM questions q
                LEFT JOIN user_question_progress p ON q.id = p.question_id AND p.user_id = ?
                WHERE q.id IN ({final_query_placeholders})
            """

            final_params = [user_id] + selected_ids
            rows = self._execute(final_query, tuple(final_params), fetch='all')

            # 4. Muunna Question-objekteiksi
            questions = []
            if rows:
                # Sekoita järjestys uudelleen, koska IN-lauseke ei takaa järjestystä
                id_to_row = {dict(row)['id']: dict(row) for row in rows}
                for q_id in selected_ids: # Käy läpi arvotussa järjestyksessä
                    row_data = id_to_row.get(q_id)
                    if row_data:
                        try:
                            row_data['options'] = json.loads(row_data.get('options', '[]'))
                            questions.append(Question(**row_data))
                        except Exception as e:
                            logger.error(f"Virhe Question-objektin luonnissa (ID {q_id}): {e}", exc_info=True)

            logger.info(f"Hettiin {len(questions)} kysymystä käyttäjälle {user_id} suodattimilla: C={categories}, D={difficulties}")
            return questions

        except Exception as e:
            logger.error(f"Kriittinen virhe get_questions: {e}", exc_info=True)
            return []

    def update_question_stats(self, question_id, is_correct, time_taken, user_id):
        """Päivittää kysymyksen tilastot käyttäjälle sekä progress- että attempts-tauluihin."""
        conn = self.get_connection()
        try:
            with conn: # Käytä transaktiota
                with conn.cursor() as cur:
                    now = datetime.now()
                    # 1. Lisää rivi user_question_progress jos sitä ei ole (UPSERT)
                    if self.is_postgres:
                        cur.execute(
                            """INSERT INTO user_question_progress (user_id, question_id, times_shown, times_correct, last_shown)
                               VALUES (%s, %s, 1, %s, %s)
                               ON CONFLICT (user_id, question_id) DO UPDATE SET
                                 times_shown = user_question_progress.times_shown + 1,
                                 times_correct = user_question_progress.times_correct + EXCLUDED.times_correct,
                                 last_shown = EXCLUDED.last_shown,
                                 mistake_acknowledged = FALSE -- Nollaa kuittaus aina vastatessa
                               """,
                            (user_id, question_id, 1 if is_correct else 0, now)
                        )
                    else:
                        # SQLite vaatii kaksi vaihetta
                        cur.execute(
                            "INSERT OR IGNORE INTO user_question_progress (user_id, question_id) VALUES (?, ?)",
                            (user_id, question_id)
                        )
                        cur.execute(
                            """UPDATE user_question_progress SET
                                 times_shown = times_shown + 1,
                                 times_correct = times_correct + ?,
                                 last_shown = ?,
                                 mistake_acknowledged = 0 -- Nollaa kuittaus
                               WHERE user_id = ? AND question_id = ?""",
                            (1 if is_correct else 0, now, user_id, question_id)
                        )

                    # 2. Lisää rivi question_attempts
                    cur.execute(
                        "INSERT INTO question_attempts (user_id, question_id, correct, time_taken, timestamp) VALUES (?, ?, ?, ?, ?)",
                        (user_id, question_id, bool(is_correct), time_taken, now)
                    )
            #logger.debug(f"Päivitettiin tilastot: U={user_id}, Q={question_id}, Correct={is_correct}")
        except Exception as e:
            logger.error(f"Virhe päivitettäessä kysymystilastoja (U={user_id}, Q={question_id}): {e}", exc_info=True)
        finally:
             if conn: conn.close()

    def get_attempts_today_count(self, user_id):
        """Hakee käyttäjän tänään tekemien vastausyritysten määrän."""
        try:
            # Muodosta päivämäärä oikein tietokannan mukaan
            if self.is_postgres:
                # Olettaa, että timestamp on TIMESTAMPTZ
                 date_filter = "timestamp >= date_trunc('day', current_timestamp at time zone 'UTC')"
                 params = (user_id,)
            else:
                 # SQLite käyttää UTC-aikaa oletuksena
                 date_filter = "date(timestamp) = date('now')"
                 params = (user_id,)

            query = f"SELECT COUNT(*) as count FROM question_attempts WHERE user_id = ? AND {date_filter}"
            result = self._execute(query, params, fetch='one')
            return result['count'] if result else 0
        except Exception as e:
            logger.error(f"Virhe haettaessa päivän yrityksiä käyttäjälle {user_id}: {e}", exc_info=True)
            return 0 # Palauta 0 virhetilanteessa

    def check_question_duplicate(self, question_text):
        """Tarkistaa onko TÄYSIN SAMANLAINEN normalisoitu kysymys jo olemassa."""
        try:
            normalized = self.normalize_question(question_text)
            if not normalized: # Estä tyhjien kysymysten tarkistus
                 return False, None
                 
            existing = self._execute(
                "SELECT id, question, category FROM questions WHERE question_normalized = ?",
                (normalized,),
                fetch='one'
            )
            if existing:
                logger.warning(f"Duplikaatti löytyi kysymykselle: '{question_text[:50]}...' (ID: {existing['id']})")
                return True, dict(existing) # Varmista dict-muoto
            return False, None
        except Exception as e:
            logger.error(f"Virhe duplikaattitarkistuksessa: {e}", exc_info=True)
            return False, None # Oletetaan ei-duplikaatiksi virhetilanteessa

    def bulk_add_questions(self, questions_data):
        """Lisää useita kysymyksiä kerralla tehokkaasti."""
        stats = {'added': 0, 'duplicates': 0, 'skipped': 0, 'errors': []}
        conn = self.get_connection()
        try:
            with conn: # Käytä transaktiota
                with conn.cursor() as cur:
                    for q_data in questions_data:
                        try:
                            # 1. Validoi data
                            required_fields = ['question', 'explanation', 'options', 'correct', 'category', 'difficulty']
                            if not all(field in q_data and q_data[field] is not None for field in required_fields):
                                stats['skipped'] += 1
                                stats['errors'].append(f"Puutteelliset tiedot: {q_data.get('question', 'N/A')[:50]}")
                                continue

                            # Varmista, että options on lista ja correct on numero
                            if not isinstance(q_data['options'], list) or not isinstance(q_data['correct'], int):
                                stats['skipped'] += 1
                                stats['errors'].append(f"Virheellinen options/correct: {q_data.get('question', 'N/A')[:50]}")
                                continue

                            # 2. Tarkista duplikaatti
                            normalized = self.normalize_question(q_data['question'])
                            cur.execute(self.param_style.join(["SELECT id FROM questions WHERE question_normalized = ", ""]), (normalized,))
                            if cur.fetchone():
                                stats['duplicates'] += 1
                                continue

                            # 3. Valmistele ja lisää
                            options_json = json.dumps(q_data['options'])
                            now = datetime.now()
                            status = q_data.get('status', 'needs_review') # Oletus 'needs_review' bulkille

                            params = (
                                q_data['question'], normalized, q_data['explanation'], options_json,
                                q_data['correct'], q_data['category'], q_data['difficulty'],
                                now, status
                            )
                            query = """INSERT INTO questions
                                       (question, question_normalized, explanation, options, correct, category, difficulty, created_at, status)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                            cur.execute(query.replace('?', self.param_style), params)
                            stats['added'] += 1

                        except Exception as item_e:
                            stats['skipped'] += 1
                            error_msg = f"Virhe kysymyksessä '{q_data.get('question', 'N/A')[:30]}': {str(item_e)[:100]}"
                            stats['errors'].append(error_msg)
                            logger.error(f"Bulk add item error: {item_e}", exc_info=True)
                            # Transaktio jatkuu seuraavaan itemiin

            logger.info(f"Bulk add valmis: Lisätty={stats['added']}, Duplikaatit={stats['duplicates']}, Skipattu={stats['skipped']}")
            return True, stats
        except Exception as e:
            logger.error(f"Kriittinen virhe bulk_add_questions: {e}", exc_info=True)
            return False, f"Kriittinen virhe transaktiossa: {e}" # Palauta virheviesti
        finally:
            if conn: conn.close()

    def find_similar_questions(self, threshold=0.90):
        """Etsii samankaltaiset kysymykset käyttäen SequenceMatcher."""
        try:
            # Hae vain tarvittavat kentät ja normalisoidut tekstit
            all_questions = self._execute(
                "SELECT id, question, category, question_normalized FROM questions ORDER BY id",
                fetch='all'
                )
            if not all_questions or len(all_questions) < 2:
                logger.info("Ei tarpeeksi kysymyksiä samankaltaisuuden vertailuun.")
                return []

            similar_pairs = []
            questions_list = list(all_questions) # Varmista lista
            checked_pairs = set() # Estä (a,b) ja (b,a)

            logger.info(f"Vertaillaan {len(questions_list)} kysymystä samankaltaisuuden varalta (kynnys={threshold*100:.0f}%)...")

            for i, q1 in enumerate(questions_list):
                # Käytä normalisoitua tekstiä nopeampaan esisuodatukseen, jos se on olemassa
                q1_text = q1.get('question_normalized') or self.normalize_question(q1['question'])
                if not q1_text: continue # Ohita tyhjät

                for j in range(i + 1, len(questions_list)):
                    q2 = questions_list[j]
                    pair_key = tuple(sorted((q1['id'], q2['id'])))
                    if pair_key in checked_pairs:
                        continue

                    q2_text = q2.get('question_normalized') or self.normalize_question(q2['question'])
                    if not q2_text: continue

                    # Laske samankaltaisuus
                    similarity = SequenceMatcher(None, q1_text, q2_text).ratio()

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
                        checked_pairs.add(pair_key)

            logger.info(f"Löytyi {len(similar_pairs)} samankaltaista kysymysparia.")
            # Järjestä suurimman samankaltaisuuden mukaan
            return sorted(similar_pairs, key=lambda x: x['similarity'], reverse=True)
        except Exception as e:
            logger.error(f"Virhe samankaltaisuushaussa: {e}", exc_info=True)
            return []

    def get_single_question_for_edit(self, question_id):
         """Hakee yhden kysymyksen tiedot muokkausta varten (ei tarvitse käyttäjän progressia)."""
         row = self._execute("SELECT * FROM questions WHERE id = ?", (question_id,), fetch='one')
         if row:
             try:
                 q_dict = dict(row)
                 q_dict['options'] = json.loads(q_dict.get('options', '[]'))
                 return q_dict
             except (json.JSONDecodeError, TypeError) as e:
                 logger.error(f"Virhe muokattavan kysymyksen (ID {question_id}) datan jäsentämisessä: {e}")
         return None

    def update_question(self, question_id, data):
        """Päivittää olemassa olevan kysymyksen tiedot."""
        try:
            # Validoi data (varmista, että tarvittavat kentät ovat olemassa)
            required = ['question', 'options', 'correct', 'explanation', 'category', 'difficulty']
            if not all(k in data for k in required):
                return False, "Puutteelliset tiedot kysymyksen päivitykseen."

            normalized = self.normalize_question(data['question'])
            options_json = json.dumps(data['options'])
            status = data.get('status', 'needs_review') # Aseta 'needs_review' muokkauksen jälkeen

            params = (
                data['question'], normalized, options_json, int(data['correct']),
                data['explanation'], data['category'], data['difficulty'], status,
                question_id
            )

            query = """UPDATE questions SET
                         question = ?, question_normalized = ?, options = ?, correct = ?,
                         explanation = ?, category = ?, difficulty = ?, status = ?
                       WHERE id = ?"""

            self._execute(query, params)
            logger.info(f"Kysymys ID {question_id} päivitetty.")
            return True, None
        except Exception as e:
            logger.error(f"Virhe kysymyksen ID {question_id} päivityksessä: {e}", exc_info=True)
            return False, f"Odottamaton virhe päivityksessä: {e}"

    def delete_question(self, question_id):
        """Poistaa kysymyksen ja siihen liittyvät tiedot (progress, attempts)."""
        conn = self.get_connection()
        try:
            with conn: # Transaktio
                with conn.cursor() as cur:
                    logger.warning(f"Aloitetaan kysymyksen ID {question_id} ja liittyvien tietojen poisto...")
                    # Poista riippuvuudet ensin
                    cur.execute(self.param_style.join(["DELETE FROM user_question_progress WHERE question_id = ", ""]), (question_id,))
                    cur.execute(self.param_style.join(["DELETE FROM question_attempts WHERE question_id = ", ""]), (question_id,))
                    # Poista itse kysymys
                    cur.execute(self.param_style.join(["DELETE FROM questions WHERE id = ", ""]), (question_id,))
                    logger.warning(f"Kysymys ID {question_id} ja liittyvät tiedot poistettu.")
            return True, None
        except Exception as e:
            logger.error(f"Virhe kysymyksen ID {question_id} poistossa: {e}", exc_info=True)
            return False, f"Odottamaton virhe poistossa: {e}"
        finally:
            if conn: conn.close()

    def clear_all_questions(self):
        """Tyhjentää KAIKKI kysymykset ja niihin liittyvät vastaukset/progressin."""
        conn = self.get_connection()
        try:
            with conn: # Transaktio
                with conn.cursor() as cur:
                    logger.critical("ALOITETAAN KAIKKIEN KYSYMYSTEN JA NIIDEN DATAN TYHJENNYS!")
                    # Hae poistettavien kysymysten määrä ensin
                    cur.execute("SELECT COUNT(*) FROM questions")
                    count_result = cur.fetchone()
                    count = count_result[0] if count_result else 0

                    # Poista riippuvuudet
                    cur.execute("DELETE FROM question_attempts")
                    logger.warning("Tyhjennetty question_attempts.")
                    cur.execute("DELETE FROM user_question_progress")
                    logger.warning("Tyhjennetty user_question_progress.")
                    # Poista kysymykset
                    cur.execute("DELETE FROM questions")
                    logger.critical(f"Kaikki {count} kysymystä ja niihin liittyvä data TYHJENNETTY!")

            return True, {'deleted_count': count}
        except Exception as e:
            logger.error(f"Kriittinen virhe tietokannan tyhjennyksessä: {e}", exc_info=True)
            return False, f"Kriittinen virhe tyhjennyksessä: {e}"
        finally:
            if conn: conn.close()

    def merge_categories_to_standard(self):
        """Yhdistää tunnetut synonyymikategoriat standardikategorioihin."""
        # Voit laajentaa tätä mappia tarvittaessa
        category_mapping = {
            'lääkelaskenta': 'laskut',
            'lääkelaskut': 'laskut',
            'laskenta': 'laskut',
            'annoslaskut': 'laskut',
            'lääkkeiden jako': 'annosjakelu',
            'lääkehoito ja turvallisuus': 'turvallisuus',
            'lääkehoidon turvallisuus': 'turvallisuus',
            'potilasturvallisuus': 'turvallisuus',
            'iv-lääkehoito': 'turvallisuus', # Esimerkki, voit luoda IV-kategorian erikseenkin
            'etiikka': 'etiikka',
            'ammattietiikka': 'etiikka',
            'farmakologia': 'kliininen farmakologia',
            'kliininen': 'kliininen farmakologia'
            # Lisää muita tarvittaessa
        }
        standard_categories = set(category_mapping.values())
        conn = self.get_connection()
        updated_count = 0
        try:
            with conn:
                with conn.cursor() as cur:
                    logger.info("Aloitetaan kategorioiden yhdistäminen...")
                    for old_cat_variation, new_standard_cat in category_mapping.items():
                        # Käytä LOWER() vertailussa, jotta kirjainkoolla ei ole väliä
                        query = f"UPDATE questions SET category = ? WHERE LOWER(category) = LOWER(?)"
                        cur.execute(query.replace('?', self.param_style), (new_standard_cat, old_cat_variation))
                        if cur.rowcount > 0:
                             logger.info(f"Yhdistettiin '{old_cat_variation}' -> '{new_standard_cat}' ({cur.rowcount} kpl).")
                             updated_count += cur.rowcount

                    # Hae lopulliset kategoriat ja niiden määrät
                    cur.execute("SELECT category, COUNT(*) as count FROM questions GROUP BY category ORDER BY category")
                    final_counts = {row[0]: row[1] for row in cur.fetchall()}

            logger.info(f"Kategorioiden yhdistäminen valmis. Päivitettiin {updated_count} kysymystä.")
            return True, {'updated_total': updated_count, 'final_categories': final_counts}

        except Exception as e:
            logger.error(f"Virhe kategorioiden yhdistämisessä: {e}", exc_info=True)
            return False, f"Virhe yhdistämisessä: {e}"
        finally:
            if conn: conn.close()


    # --- Sessio- ja saavutusfunktiot (näitä ei tarvinnut muuttaa multi-tenant varten) ---

    def save_or_update_session(self, user_id, session_type, question_ids, answers, current_index, time_remaining):
        """Tallentaa tai päivittää aktiivisen session (käytetäänkö tätä enää?)."""
        # Tämä saattaa olla vanhentunut, jos siirryit Flaskin sessioihin
        try:
            now = datetime.now()
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
                (user_id, session_type, json.dumps(question_ids), json.dumps(answers), current_index, time_remaining, now)
            )
            return True, None
        except Exception as e:
            logger.error(f"Virhe session tallennuksessa käyttäjälle {user_id}: {e}", exc_info=True)
            return False, str(e)

    def get_active_session(self, user_id):
        """Hakee aktiivisen session (käytetäänkö tätä enää?)."""
        try:
            session_data = self._execute("SELECT * FROM active_sessions WHERE user_id = ?", (user_id,), fetch='one')
            if session_data:
                session_dict = dict(session_data) # Muunna dictiksi
                session_dict['question_ids'] = json.loads(session_dict.get('question_ids', '[]'))
                session_dict['answers'] = json.loads(session_dict.get('answers', '[]'))
                return session_dict
            return None
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Virhe session haussa tai jäsentämisessä käyttäjälle {user_id}: {e}", exc_info=True)
            # Yritä poistaa virheellinen sessio
            self.delete_active_session(user_id)
            return None

    def delete_active_session(self, user_id):
        """Poistaa aktiivisen session (käytetäänkö tätä enää?)."""
        try:
            self._execute("DELETE FROM active_sessions WHERE user_id = ?", (user_id,))
            return True, None
        except Exception as e:
            logger.error(f"Virhe session poistossa käyttäjälle {user_id}: {e}", exc_info=True)
            return False, str(e)

    def get_user_achievements(self, user_id):
        """Hakee käyttäjän saavutukset."""
        return self._execute(
            "SELECT achievement_id, unlocked_at FROM user_achievements WHERE user_id = ?",
            (user_id,),
            fetch='all'
        )

    def unlock_achievement(self, user_id, achievement_id):
        """Avaa saavutuksen käyttäjälle idempotently (ei tee mitään, jos jo avattu)."""
        try:
            if self.is_postgres:
                # ON CONFLICT DO NOTHING hoitaa idempotenssin
                self._execute(
                    "INSERT INTO user_achievements (user_id, achievement_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (user_id, achievement_id)
                )
            else:
                # INSERT OR IGNORE hoitaa idempotenssin
                self._execute(
                    "INSERT OR IGNORE INTO user_achievements (user_id, achievement_id) VALUES (?, ?)",
                    (user_id, achievement_id)
                )
            # Tässä voisi tarkistaa, lisättiinkö rivi vai oliko se jo olemassa, mutta usein se ei ole tarpeen
            # logger.info(f"Yritettiin avata saavutus '{achievement_id}' käyttäjälle {user_id}.")
            return True
        except Exception as e:
            logger.error(f"Virhe saavutuksen '{achievement_id}' avaamisessa käyttäjälle {user_id}: {e}", exc_info=True)
            return False
            
    # Lisää tarvittaessa muita funktioita, esim. organisaation päivitys/poisto (soft/hard)