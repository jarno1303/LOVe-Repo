"""
Stats Manager - Oppimistilastojen hallinta ja analytiikka
"""

import sqlite3
import json
import datetime
from config import config


class EnhancedStatsManager:
    """Käyttäjäkohtaisten oppimistilastojen hallinta."""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def start_session(self, user_id, session_type, categories=None):
        """
        Aloita käyttäjäkohtainen opiskelusessio.
        
        Args:
            user_id: Käyttäjän ID
            session_type: Session tyyppi (practice, simulation, review)
            categories: Lista kategorioita (None = kaikki)
        
        Returns:
            Session ID tai None jos epäonnistui
        """
        try:
            with sqlite3.connect(self.db_manager.db_path) as conn:
                cursor = conn.execute("""
                    INSERT INTO study_sessions (user_id, start_time, session_type, categories)
                    VALUES (?, datetime('now'), ?, ?)
                """, (user_id, session_type, json.dumps(categories or [])))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            print(f"Virhe session aloituksessa: {e}")
            return None

    def end_session(self, user_id, session_id=None, questions_answered=0, questions_correct=0):
        """
        Lopeta käyttäjäkohtainen opiskelusessio.
        
        Args:
            user_id: Käyttäjän ID
            session_id: Session ID (jos None, päivitetään viimeisin sessio)
            questions_answered: Vastattujen kysymysten määrä
            questions_correct: Oikeiden vastausten määrä
        """
        try:
            with sqlite3.connect(self.db_manager.db_path) as conn:
                if session_id:
                    conn.execute("""
                        UPDATE study_sessions 
                        SET end_time = datetime('now'), 
                            questions_answered = ?, 
                            questions_correct = ?
                        WHERE id = ? AND user_id = ?
                    """, (questions_answered, questions_correct, session_id, user_id))
                else:
                    # Päivitä viimeisin sessio
                    conn.execute("""
                        UPDATE study_sessions 
                        SET end_time = datetime('now'), 
                            questions_answered = ?, 
                            questions_correct = ?
                        WHERE user_id = ? AND end_time IS NULL
                        ORDER BY start_time DESC
                        LIMIT 1
                    """, (questions_answered, questions_correct, user_id))
                conn.commit()
        except Exception as e:
            print(f"Virhe session lopetuksessa: {e}")

    def get_learning_analytics(self, user_id):
        """
        Hae kattavat käyttäjäkohtaiset oppimistilastot.
        
        Args:
            user_id: Käyttäjän ID
        
        Returns:
            Dictionary joka sisältää:
            - general: Yleiset tilastot
            - categories: Kategoriakohtaiset tilastot
            - difficulties: Vaikeustasokohtaiset tilastot
            - weekly_progress: Viikon edistyminen
            - recent_sessions: Viimeisimmät sessiot
        """
        with sqlite3.connect(self.db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # ========== YLEISET TILASTOT ==========
            general_stats_query = """
                SELECT 
                    COUNT(DISTINCT p.question_id) as answered_questions,
                    AVG(CASE WHEN p.times_shown > 0 
                        THEN CAST(p.times_correct AS FLOAT) / p.times_shown 
                        ELSE 0 END) as avg_success_rate,
                    SUM(p.times_shown) as total_attempts,
                    SUM(p.times_correct) as total_correct,
                    AVG(qa.time_taken) as avg_time_per_question
                FROM user_question_progress p
                LEFT JOIN question_attempts qa ON p.user_id = qa.user_id AND p.question_id = qa.question_id
                WHERE p.user_id = ?
            """
            general_stats = conn.execute(general_stats_query, (user_id,)).fetchone()

            # Kokonaiskysymysmäärä tietokannassa
            total_questions_in_db = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            
            general_dict = {
                'answered_questions': general_stats['answered_questions'] or 0,
                'total_questions_in_db': total_questions_in_db,
                'avg_success_rate': general_stats['avg_success_rate'] or 0.0,
                'total_attempts': general_stats['total_attempts'] or 0,
                'total_correct': general_stats['total_correct'] or 0,
                'avg_time_per_question': round(general_stats['avg_time_per_question'] or 0, 1)
            }
            
            # ========== KATEGORIAKOHTAISET TILASTOT ==========
            category_stats_query = """
                SELECT 
                    q.category,
                    COUNT(DISTINCT p.question_id) as question_count,
                    AVG(CASE WHEN p.times_shown > 0 
                        THEN CAST(p.times_correct AS FLOAT) / p.times_shown 
                        ELSE 0 END) as success_rate,
                    SUM(p.times_shown) as attempts,
                    SUM(p.times_correct) as corrects
                FROM questions q
                LEFT JOIN user_question_progress p ON q.id = p.question_id AND p.user_id = ?
                WHERE p.question_id IS NOT NULL
                GROUP BY q.category
                ORDER BY success_rate ASC
            """
            category_stats = conn.execute(category_stats_query, (user_id,)).fetchall()
            
            # ========== VAIKEUSTASOKOHTAISET TILASTOT ==========
            difficulty_stats_query = """
                SELECT 
                    q.difficulty,
                    COUNT(DISTINCT p.question_id) as question_count,
                    AVG(CASE WHEN p.times_shown > 0 
                        THEN CAST(p.times_correct AS FLOAT) / p.times_shown 
                        ELSE 0 END) as success_rate,
                    SUM(p.times_shown) as attempts
                FROM questions q
                LEFT JOIN user_question_progress p ON q.id = p.question_id AND p.user_id = ?
                WHERE p.question_id IS NOT NULL
                GROUP BY q.difficulty
                ORDER BY 
                    CASE q.difficulty
                        WHEN 'helppo' THEN 1
                        WHEN 'keskivaikea' THEN 2
                        WHEN 'vaikea' THEN 3
                        ELSE 4
                    END
            """
            difficulty_stats = conn.execute(difficulty_stats_query, (user_id,)).fetchall()
            
            # ========== VIIKOTTAINEN EDISTYMINEN ==========
            weekly_progress_query = """
                SELECT 
                    date(timestamp) as date,
                    COUNT(*) as questions_answered,
                    SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as corrects
                FROM question_attempts
                WHERE user_id = ? AND timestamp >= date('now', '-30 days')
                GROUP BY date(timestamp)
                ORDER BY date
            """
            weekly_progress = conn.execute(weekly_progress_query, (user_id,)).fetchall()
            
            # ========== VIIMEISIMMÄT SESSIOT ==========
            try:
                recent_sessions_query = """
                    SELECT 
                        session_type,
                        start_time,
                        end_time,
                        questions_answered,
                        questions_correct,
                        categories
                    FROM study_sessions
                    WHERE user_id = ? AND end_time IS NOT NULL
                    ORDER BY start_time DESC
                    LIMIT 5
                """
                recent_sessions = conn.execute(recent_sessions_query, (user_id,)).fetchall()
            except:
                recent_sessions = []
            
            return {
                'general': general_dict,
                'categories': [dict(row) for row in category_stats],
                'difficulties': [dict(row) for row in difficulty_stats],
                'weekly_progress': [dict(row) for row in weekly_progress],
                'recent_sessions': [dict(row) for row in recent_sessions]
            }

    def get_recommendations(self, user_id):
        """
        Anna käyttäjäkohtaiset oppimissuositukset perustuen analytiikkaan.
        
        Args:
            user_id: Käyttäjän ID
        
        Returns:
            Lista suosituksia, jokainen sisältää:
            - type: Suosituksen tyyppi
            - title: Otsikko
            - description: Kuvaus
            - action: Toiminto
            - data: Lisätiedot
        """
        analytics = self.get_learning_analytics(user_id)
        recommendations = []

        # ========== HEIKOT KATEGORIAT ==========
        weak_categories = [
            cat for cat in analytics['categories'] 
            if cat['success_rate'] is not None 
            and cat['success_rate'] < 0.7 
            and cat['attempts'] >= 5
        ]
        
        if weak_categories:
            weakest = min(weak_categories, key=lambda x: x['success_rate'])
            recommendations.append({
                'type': 'focus_area',
                'title': f"Keskity kategoriaan: {weakest['category'].title()}",
                'description': f"Onnistumisprosenttisi on {weakest['success_rate']*100:.1f}%. Harjoittele lisää tätä aihealuetta.",
                'action': 'practice_category',
                'priority': 'high',
                'data': {'category': weakest['category']}
            })
        
        # ========== PÄIVITTÄISEN TAVOITTEEN TARKISTUS ==========
        today_answered = 0
        today_str = datetime.date.today().isoformat()
        
        for day in analytics['weekly_progress']:
            if day['date'] == today_str:
                today_answered = day['questions_answered']
                break

        daily_goal = config.daily_goal
        if today_answered < daily_goal:
            remaining = daily_goal - today_answered
            recommendations.append({
                'type': 'daily_goal',
                'title': f"Päivittäinen tavoite: {today_answered}/{daily_goal}",
                'description': f"Vastaa vielä {remaining} kysymykseen saavuttaaksesi päivän tavoitteen!",
                'action': 'daily_practice',
                'priority': 'medium',
                'data': {'remaining': remaining, 'completed': today_answered}
            })
        elif today_answered >= daily_goal:
            recommendations.append({
                'type': 'daily_goal_complete',
                'title': "🎉 Päivän tavoite saavutettu!",
                'description': f"Hienoa! Olet vastannut jo {today_answered} kysymykseen tänään.",
                'action': 'celebrate',
                'priority': 'low',
                'data': {'completed': today_answered}
            })
        
        # ========== AKTIIVISUUDEN TARKISTUS ==========
        if analytics['weekly_progress']:
            last_activity = analytics['weekly_progress'][-1]['date']
            last_date = datetime.datetime.strptime(last_activity, '%Y-%m-%d').date()
            days_since = (datetime.date.today() - last_date).days
            
            if days_since > 1:
                recommendations.append({
                    'type': 'inactivity',
                    'title': f"Tervetuloa takaisin!",
                    'description': f"Viimeksi harjoittelit {days_since} päivää sitten. Jatka säännöllistä harjoittelua!",
                    'action': 'continue_learning',
                    'priority': 'high',
                    'data': {'days_since': days_since}
                })
        
        # ========== VAHVAT KATEGORIAT (POSITIIVINEN PALAUTE) ==========
        strong_categories = [
            cat for cat in analytics['categories'] 
            if cat['success_rate'] is not None 
            and cat['success_rate'] >= 0.9 
            and cat['attempts'] >= 10
        ]
        
        if strong_categories:
            strongest = max(strong_categories, key=lambda x: x['success_rate'])
            recommendations.append({
                'type': 'strength',
                'title': f"Loistavaa! Osaat {strongest['category'].title()}-kategorian hyvin",
                'description': f"Onnistumisprosenttisi on {strongest['success_rate']*100:.1f}%. Jatka samaan malliin!",
                'action': 'celebrate',
                'priority': 'low',
                'data': {'category': strongest['category']}
            })
        
        # ========== SIMULAATIO-SUOSITUS ==========
        if analytics['general']['answered_questions'] >= 50:
            # Tarkista onko jo tehnyt simulaation
            with sqlite3.connect(self.db_manager.db_path) as conn:
                try:
                    simulation_count = conn.execute("""
                        SELECT COUNT(*) as count 
                        FROM study_sessions 
                        WHERE user_id = ? AND session_type = 'simulation'
                    """, (user_id,)).fetchone()[0]
                    
                    if simulation_count == 0:
                        recommendations.append({
                            'type': 'simulation',
                            'title': "Kokeile koesimulaatiota!",
                            'description': "Olet vastannut yli 50 kysymykseen. Kokeile koesimulaatiota testataksesi osaamistasi!",
                            'action': 'start_simulation',
                            'priority': 'medium',
                            'data': {}
                        })
                except:
                    pass
        
        # Järjestä suositukset prioriteetin mukaan
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        recommendations.sort(key=lambda x: priority_order.get(x.get('priority', 'low'), 2))
        
        return recommendations

    def get_user_streak(self, user_id):
        """
        Laske käyttäjän nykyinen harjoitteluputki.
        
        Args:
            user_id: Käyttäjän ID
        
        Returns:
            Dictionary joka sisältää current_streak ja longest_streak
        """
        with sqlite3.connect(self.db_manager.db_path) as conn:
            # Hae kaikki uniikit päivät joina on harjoiteltu
            rows = conn.execute("""
                SELECT DISTINCT date(timestamp) as practice_date 
                FROM question_attempts 
                WHERE user_id = ? 
                ORDER BY practice_date DESC
            """, (user_id,)).fetchall()
            
            if not rows:
                return {'current_streak': 0, 'longest_streak': 0}
            
            dates = [datetime.datetime.strptime(row[0], '%Y-%m-%d').date() for row in rows]
            
            # Laske nykyinen putki
            current_streak = 0
            today = datetime.date.today()
            
            for i, date in enumerate(dates):
                expected_date = today - datetime.timedelta(days=i)
                if date == expected_date:
                    current_streak += 1
                else:
                    break
            
            # Laske pisin putki
            longest_streak = 0
            temp_streak = 1
            
            for i in range(len(dates) - 1):
                if (dates[i] - dates[i + 1]).days == 1:
                    temp_streak += 1
                    longest_streak = max(longest_streak, temp_streak)
                else:
                    temp_streak = 1
            
            longest_streak = max(longest_streak, temp_streak)
            
            return {
                'current_streak': current_streak,
                'longest_streak': longest_streak
            }