import random
import sqlite3
from models.models import Question
from typing import List
import json

# Lista häiriöskenaarioista (ei muutoksia)
DISTRACTORS = [
    {
        "scenario": "Potilaan omainen tulee kysymään, voisitko tuoda hänen läheiselleen lasin vettä.",
        "options": ["Lupaan tuoda veden heti lääkkeenjaon jälkeen.", "Keskeytän ja haen veden välittömästi."]
    },
    # ... (muut häiriöskenaariot säilyvät ennallaan)
]

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
        with sqlite3.connect(self.db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = """
                SELECT 
                    q.*,
                    p.times_shown, p.times_correct, p.last_shown, p.ease_factor, p.interval
                FROM questions q
                JOIN user_question_progress p ON q.id = p.question_id
                WHERE p.user_id = ?
                  AND p.last_shown IS NOT NULL
                  AND datetime(p.last_shown, '+' || p.interval || ' days') <= datetime('now')
                ORDER BY datetime(p.last_shown, '+' || p.interval || ' days') ASC
                LIMIT ?
            """
            rows = conn.execute(query, (user_id, limit)).fetchall()
            
            # Korjattu: Poistettu 'updated_at', jota Question-luokka ei odota.
            questions = [Question(
                id=row['id'], question=row['question'], explanation=row['explanation'],
                options=json.loads(row['options']), correct=row['correct'], category=row['category'],
                difficulty=row['difficulty'], created_at=row['created_at'],
                times_shown=row['times_shown'] or 0, times_correct=row['times_correct'] or 0,
                last_shown=row['last_shown'], ease_factor=row['ease_factor'] or 2.5,
                interval=row['interval'] or 1
            ) for row in rows]
            return questions

    # Korjattu: Metodi nimetty uudelleen vastaamaan app.py:n kutsua.
    def record_review(self, user_id, question_id, interval, ease_factor):
        """Päivittää käyttäjän SR-tiedot kysymykselle."""
        with sqlite3.connect(self.db_manager.db_path) as conn:
            conn.execute("""
                UPDATE user_question_progress
                SET interval = ?, ease_factor = ?
                WHERE user_id = ? AND question_id = ?
            """, (interval, ease_factor, user_id, question_id))