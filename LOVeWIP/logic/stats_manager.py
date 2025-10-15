"""
Stats Manager - Oppimistilastojen hallinta ja analytiikka
"""
import json
from datetime import datetime, date, timedelta

class EnhancedStatsManager:
    """Käyttäjäkohtaisten oppimistilastojen hallinta."""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def start_session(self, user_id, session_type, categories=None):
        """Aloita käyttäjäkohtainen opiskelusessio."""
        query = """
            INSERT INTO study_sessions (user_id, start_time, session_type, categories)
            VALUES (?, ?, ?, ?)
        """
        params = (user_id, datetime.now(), session_type, json.dumps(categories or []))
        try:
            self.db_manager._execute(query, params, fetch='none')
            return True
        except Exception as e:
            print(f"Virhe session aloituksessa: {e}")
            return False

    def end_session(self, user_id, session_id=None, questions_answered=0, questions_correct=0):
        """Lopeta käyttäjäkohtainen opiskelusessio."""
        try:
            session_id_to_update = session_id
            if not session_id_to_update:
                # Etsi viimeisin avoin sessio ja päivitä se
                find_query = "SELECT id FROM study_sessions WHERE user_id = ? AND end_time IS NULL ORDER BY start_time DESC LIMIT 1"
                latest_session = self.db_manager._execute(find_query, (user_id,), fetch='one')
                if latest_session:
                    session_id_to_update = latest_session['id']
            
            if session_id_to_update:
                update_query = """
                    UPDATE study_sessions 
                    SET end_time = ?, questions_answered = ?, questions_correct = ?
                    WHERE id = ? AND user_id = ?
                """
                update_params = (datetime.now(), questions_answered, questions_correct, session_id_to_update, user_id)
                self.db_manager._execute(update_query, update_params, fetch='none')
        except Exception as e:
            print(f"Virhe session lopetuksessa: {e}")

    def get_learning_analytics(self, user_id):
        """Hae kattavat käyttäjäkohtaiset oppimistilastot."""
        analytics_data = {'general': {}, 'categories': [], 'difficulties': [], 'weekly_progress': [], 'recent_sessions': []}
        try:
            general_stats_q = """
                SELECT 
                    COUNT(DISTINCT p.question_id) as answered_questions,
                    SUM(p.times_shown) as total_attempts,
                    SUM(p.times_correct) as total_correct,
                    AVG(qa.time_taken) as avg_time_per_question
                FROM user_question_progress p
                LEFT JOIN question_attempts qa ON p.user_id = qa.user_id AND p.question_id = qa.question_id
                WHERE p.user_id = ?"""
            general_stats = self.db_manager._execute(general_stats_q, (user_id,), fetch='one') or {}

            total_q_in_db_res = self.db_manager._execute("SELECT COUNT(*) as count FROM questions", fetch='one')
            total_q_in_db = total_q_in_db_res['count'] if total_q_in_db_res else 0
            
            total_attempts = general_stats.get('total_attempts') or 0
            total_correct = general_stats.get('total_correct') or 0
            
            analytics_data['general'] = {
                'answered_questions': general_stats.get('answered_questions') or 0,
                'total_questions_in_db': total_q_in_db,
                'avg_success_rate': (total_correct / total_attempts) if total_attempts > 0 else 0,
                'total_attempts': total_attempts,
                'total_correct': total_correct,
                'avg_time_per_question': round(general_stats.get('avg_time_per_question') or 0, 1)
            }

            category_stats_q = """
                SELECT q.category, SUM(p.times_shown) as attempts, SUM(p.times_correct) as corrects
                FROM questions q JOIN user_question_progress p ON q.id = p.question_id
                WHERE p.user_id = ? AND p.times_shown > 0 GROUP BY q.category"""
            category_stats = self.db_manager._execute(category_stats_q, (user_id,), fetch='all') or []
            analytics_data['categories'] = [{'category': r['category'], 'attempts': r['attempts'], 'success_rate': (r['corrects'] / r['attempts']) if r['attempts'] > 0 else 0} for r in category_stats]

            difficulty_stats_q = """
                SELECT q.difficulty, SUM(p.times_shown) as attempts, SUM(p.times_correct) as corrects
                FROM questions q JOIN user_question_progress p ON q.id = p.question_id
                WHERE p.user_id = ? AND p.times_shown > 0 GROUP BY q.difficulty"""
            difficulty_stats = self.db_manager._execute(difficulty_stats_q, (user_id,), fetch='all') or []
            analytics_data['difficulties'] = [{'difficulty': r['difficulty'], 'attempts': r['attempts'], 'success_rate': (r['corrects'] / r['attempts']) if r['attempts'] > 0 else 0} for r in difficulty_stats]

            days_ago_30 = date.today() - timedelta(days=30)
            
            if self.db_manager.is_postgres:
                weekly_progress_q = """
                    SELECT CAST(timestamp AS DATE) as date, COUNT(*) as questions_answered,
                           SUM(CASE WHEN correct THEN 1 ELSE 0 END) as corrects
                    FROM question_attempts WHERE user_id = %s AND timestamp >= %s
                    GROUP BY CAST(timestamp AS DATE) ORDER BY date"""
            else:
                weekly_progress_q = """
                    SELECT date(timestamp) as date, COUNT(*) as questions_answered,
                           SUM(CASE WHEN correct THEN 1 ELSE 0 END) as corrects
                    FROM question_attempts WHERE user_id = ? AND date(timestamp) >= ?
                    GROUP BY date(timestamp) ORDER BY date"""
            weekly_progress = self.db_manager._execute(weekly_progress_q, (user_id, days_ago_30), fetch='all') or []
            analytics_data['weekly_progress'] = [dict(row) for row in weekly_progress]

            return analytics_data
        except Exception as e:
            print(f"CRITICAL ERROR fetching analytics: {e}")
            return analytics_data

    def get_recommendations(self, user_id):
        """Anna käyttäjäkohtaiset oppimissuositukset."""
        analytics = self.get_learning_analytics(user_id)
        recommendations = []
        if not analytics: return recommendations

        weak_categories = [c for c in analytics.get('categories', []) if c['success_rate'] < 0.7 and c['attempts'] >= 5]
        if weak_categories:
            weakest = min(weak_categories, key=lambda x: x['success_rate'])
            recommendations.append({'type': 'weakest_category', 'title': f"Keskity: {weakest['category'].title()}", 'description': f"Onnistumisprosenttisi on {weakest['success_rate']*100:.1f}%. Harjoittele lisää.", 'action': 'practice_category', 'priority': 'high', 'data': {'category': weakest['category']}, 'category': weakest['category'], 'accuracy': weakest['success_rate']*100})

        if analytics.get('general', {}).get('answered_questions', 0) >= 50:
            try:
                sim_q = "SELECT COUNT(*) as count FROM study_sessions WHERE user_id = ? AND session_type = 'simulation'"
                sim_count_res = self.db_manager._execute(sim_q, (user_id,), fetch='one')
                if sim_count_res and sim_count_res['count'] == 0:
                    recommendations.append({'type': 'simulation', 'title': "Kokeile koesimulaatiota!", 'description': "Olet vastannut yli 50 kysymykseen. Testaa osaamistasi!", 'action': 'start_simulation', 'priority': 'medium', 'data': {}})
            except Exception as e:
                print(f"Virhe simulaatiosuosituksessa: {e}")

        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        recommendations.sort(key=lambda x: priority_order.get(x.get('priority', 'low'), 2))
        return recommendations

    def get_user_streak(self, user_id):
        """Laske käyttäjän harjoitteluputki."""
        date_func = "DATE" if not self.db_manager.is_postgres else "CAST(timestamp AS DATE)"
        query = f"SELECT DISTINCT {date_func} as practice_date FROM question_attempts WHERE user_id = ? ORDER BY practice_date DESC"
        rows = self.db_manager._execute(query, (user_id,), fetch='all')
        
        if not rows:
            return {'current_streak': 0, 'longest_streak': 0}
        
        dates = [row['practice_date'] for row in rows]
        if isinstance(dates[0], str):
            dates = [datetime.strptime(d_str, '%Y-%m-%d').date() for d_str in dates]

        current_streak = 0
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        if dates[0] == today or dates[0] == yesterday:
            current_streak = 1
            for i in range(len(dates) - 1):
                if (dates[i] - dates[i+1]).days == 1:
                    current_streak += 1
                else:
                    break
        
        longest_streak = 0
        if dates:
            longest_streak = 1
            temp_streak = 1
            for i in range(len(dates) - 1):
                if (dates[i] - dates[i+1]).days == 1:
                    temp_streak += 1
                else:
                    temp_streak = 1
                longest_streak = max(longest_streak, temp_streak)

        return {'current_streak': current_streak, 'longest_streak': longest_streak}