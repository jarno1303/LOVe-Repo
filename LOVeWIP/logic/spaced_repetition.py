import json
from models.models import Question
from typing import List

class SpacedRepetitionManager:
    """SM-2 algoritmin toteutus, nyt käyttäjäkohtainen."""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def calculate_next_review(self, question: Question, performance_rating: int) -> tuple:
        """Laskee seuraavan kertausajan SM-2 algoritmin mukaan."""
        if performance_rating < 3:
            interval = 1
            ease_factor = max(1.3, question.ease_factor - 0.8 + 0.28 * performance_rating - 0.02 * (performance_rating**2))
        else:
            if question.times_shown <= 1:
                interval = 6
            else:
                interval = round(question.interval * question.ease_factor)
            ease_factor = question.ease_factor + (0.1 - (5 - performance_rating) * (0.08 + (5 - performance_rating) * 0.02))
            ease_factor = max(1.3, ease_factor)
        return interval, ease_factor
    
    def get_due_questions(self, user_id, limit=20) -> List[Question]:
        """Hakee käyttäjän erääntyvät kertauskysymykset."""
        date_func = "DATE" if not self.db_manager.is_postgres else ""
        query = f"""
            SELECT 
                q.*,
                p.times_shown, p.times_correct, p.last_shown, p.ease_factor, p.interval
            FROM questions q
            JOIN user_question_progress p ON q.id = p.question_id
            WHERE p.user_id = ?
              AND p.last_shown IS NOT NULL
              AND {date_func}(p.last_shown, '+' || p.interval || ' days') <= {date_func}('now')
            ORDER BY {date_func}(p.last_shown, '+' || p.interval || ' days') ASC
            LIMIT ?
        """
        if self.db_manager.is_postgres:
             query = """
                SELECT 
                    q.*,
                    p.times_shown, p.times_correct, p.last_shown, p.ease_factor, p.interval
                FROM questions q
                JOIN user_question_progress p ON q.id = p.question_id
                WHERE p.user_id = %s
                  AND p.last_shown IS NOT NULL
                  AND p.last_shown + (p.interval * INTERVAL '1 day') <= NOW()
                ORDER BY p.last_shown + (p.interval * INTERVAL '1 day') ASC
                LIMIT %s
            """
        
        rows = self.db_manager._execute(query, (user_id, limit), fetch='all')
            
        questions = []
        if rows:
            for row in rows:
                try:
                    questions.append(Question(
                        id=row['id'], question=row['question'], explanation=row['explanation'],
                        options=json.loads(row['options']), correct=row['correct'], category=row['category'],
                        difficulty=row['difficulty'], created_at=row.get('created_at'),
                        times_shown=row.get('times_shown', 0) or 0, 
                        times_correct=row.get('times_correct', 0) or 0,
                        last_shown=row.get('last_shown'), 
                        ease_factor=row.get('ease_factor', 2.5) or 2.5,
                        interval=row.get('interval', 1) or 1
                    ))
                except (json.JSONDecodeError, TypeError) as e:
                    print(f"Error parsing question data in get_due_questions: {e}")
                    continue
        return questions

    def record_review(self, user_id, question_id, interval, ease_factor):
        """Päivittää käyttäjän SR-tiedot kysymykselle."""
        self.db_manager._execute("""
            UPDATE user_question_progress
            SET interval = ?, ease_factor = ?
            WHERE user_id = ? AND question_id = ?
        """, (interval, ease_factor, user_id, question_id), fetch='none')