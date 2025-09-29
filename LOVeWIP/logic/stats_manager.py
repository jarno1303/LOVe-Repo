import sqlite3
import json
import datetime
from config import config

class EnhancedStatsManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def start_session(self, user_id, session_type, categories=None):
        """Aloita käyttäjäkohtainen opiskelusessio."""
        with sqlite3.connect(self.db_manager.db_path) as conn:
            conn.execute("""
                INSERT INTO study_sessions (user_id, start_time, session_type, categories)
                VALUES (?, datetime('now'), ?, ?)
            """, (user_id, session_type, json.dumps(categories or [])))

    def end_session(self, user_id, session_id, questions_answered=0, questions_correct=0):
        """Lopeta käyttäjäkohtainen opiskelusessio."""
        with sqlite3.connect(self.db_manager.db_path) as conn:
            conn.execute("""
                UPDATE study_sessions 
                SET end_time = datetime('now'), questions_answered = ?, questions_correct = ?
                WHERE id = ? AND user_id = ?
            """, (questions_answered, questions_correct, session_id, user_id))

    def get_learning_analytics(self, user_id):
        """Hae käyttäjäkohtaiset oppimistilastot."""
        with sqlite3.connect(self.db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Yleistilastot käyttäjän edistymisestä
            general_stats_query = """
                SELECT 
                    COUNT(p.question_id) as answered_questions,
                    AVG(CASE WHEN p.times_shown > 0 THEN p.times_correct * 1.0 / p.times_shown ELSE 0 END) as avg_success_rate,
                    SUM(p.times_shown) as total_attempts,
                    SUM(p.times_correct) as total_correct
                FROM user_question_progress p
                WHERE p.user_id = ?
            """
            general_stats = conn.execute(general_stats_query, (user_id,)).fetchone()

            total_questions_in_db = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            
            general_dict = {
                'answered_questions': general_stats['answered_questions'] or 0,
                'total_questions_in_db': total_questions_in_db,
                'avg_success_rate': general_stats['avg_success_rate'] or 0.0,
                'total_attempts': general_stats['total_attempts'] or 0,
                'total_correct': general_stats['total_correct'] or 0
            }
            
            # Kategoriakohtaiset tilastot käyttäjälle
            category_stats_query = """
                SELECT 
                    q.category,
                    COUNT(p.question_id) as question_count,
                    AVG(CASE WHEN p.times_shown > 0 THEN p.times_correct * 1.0 / p.times_shown ELSE 0 END) as success_rate,
                    SUM(p.times_shown) as attempts,
                    SUM(p.times_correct) as corrects
                FROM questions q
                JOIN user_question_progress p ON q.id = p.question_id
                WHERE p.user_id = ?
                GROUP BY q.category
                ORDER BY success_rate ASC
            """
            category_stats = conn.execute(category_stats_query, (user_id,)).fetchall()
            
            # Viikottainen edistyminen käyttäjälle
            weekly_progress_query = """
                SELECT 
                    date(timestamp) as date,
                    COUNT(*) as questions_answered,
                    SUM(CASE WHEN correct THEN 1 ELSE 0 END) as corrects
                FROM question_attempts
                WHERE user_id = ? AND timestamp >= date('now', '-7 days')
                GROUP BY date(timestamp)
                ORDER BY date
            """
            weekly_progress = conn.execute(weekly_progress_query, (user_id,)).fetchall()
            
            return {
                'general': general_dict,
                'categories': [dict(row) for row in category_stats],
                'weekly_progress': [dict(row) for row in weekly_progress]
            }

    def get_recommendations(self, user_id):
        """Anna käyttäjäkohtaiset oppimissuositukset."""
        analytics = self.get_learning_analytics(user_id)
        recommendations = []

        weak_categories = [cat for cat in analytics['categories'] 
                           if cat['success_rate'] is not None and cat['success_rate'] < 0.7 and cat['attempts'] >= 5]
        
        if weak_categories:
            weakest = min(weak_categories, key=lambda x: x['success_rate'])
            recommendations.append({
                'type': 'focus_area',
                'title': f"Keskity kategoriaan: {weakest['category']}",
                'description': f"Onnistumisprosenttisi on {weakest['success_rate']*100:.1f}%",
                'action': 'practice_category',
                'data': {'category': weakest['category']}
            })
        
        # Päivittäisen tavoitteen tarkistus
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
                'description': f"Vastaa vielä {remaining} kysymykseen",
                'action': 'daily_practice',
                'data': {'remaining': remaining}
            })
        
        return recommendations
