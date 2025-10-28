# -*- coding: utf-8 -*-
# models/models.py
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from flask_login import UserMixin

@dataclass
class User(UserMixin):
    """Käyttäjämalli Flask-Login yhteensopiva."""
    id: int
    username: str
    email: str
    role: str = 'user'
    distractors_enabled: bool = False
    distractor_probability: int = 25
    password: Optional[str] = None
    status: str = 'active'
    created_at: Optional[str] = None
    expires_at: Optional[datetime] = None

    def get_id(self):
        """Palauttaa käyttäjän ID:n merkkijonona."""
        return str(self.id)
    
    def is_admin(self):
        """Tarkistaa onko käyttäjä admin."""
        return self.role == 'admin'

@dataclass
class Question:
    id: int
    question: str
    options: list
    correct: int
    explanation: str
    category: str
    difficulty: str
    times_shown: int = 0
    times_correct: int = 0
    last_shown: datetime = None
    ease_factor: float = 2.5
    interval: int = 1
    status: str = 'needs_review'             # ← UUSI
    validated_by: int = None                # ← UUSI
    validated_at: datetime = None           # ← UUSI
    validation_comment: Optional[str] = None #Uusin lisäys
    question_normalized: str = None         # ← UUSI
    created_at: datetime = None             # ← UUSI
    hint_type: str = None                   # ← UUSI

@dataclass
class QuestionAttempt:
    """Kysymykseen vastaamisen yritys."""
    id: int
    user_id: int
    question_id: int
    is_correct: bool
    time_taken: int
    created_at: Optional[str] = None

@dataclass
class Achievement:
    """Saavutus."""
    id: str
    name: str
    description: str
    icon: str
    unlocked: bool = False
    unlocked_at: Optional[datetime] = None

@dataclass
class UserStats:
    """Käyttäjän tilastot."""
    user_id: int
    total_attempts: int
    correct_attempts: int
    success_rate: float
    avg_time_per_question: float
    current_streak: int
    best_streak: int
    last_activity: Optional[datetime] = None

@dataclass
class DistractorAttempt:
    """Häiriötekijäyritys."""
    id: int
    user_id: int
    distractor_scenario: str
    user_choice: int
    correct_choice: int
    is_correct: bool
    response_time: int
    created_at: Optional[str] = None

@dataclass
class SpacedRepetitionCard:
    """Väliajoin kertauksen kortti."""
    id: int
    user_id: int
    question_id: int
    ease_factor: float
    interval_days: int
    repetitions: int
    next_review: datetime
    last_reviewed: Optional[datetime] = None
    quality: int = 0

@dataclass
class LearningSession:
    """Oppimissessio."""
    id: int
    user_id: int
    session_type: str
    questions_answered: int
    correct_answers: int
    session_duration: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    
@dataclass
class CategoryProgress:
    """Kategoriakohtainen edistyminen."""
    category: str
    total_questions: int
    attempted_questions: int
    correct_answers: int
    success_rate: float
    avg_difficulty: float
    last_activity: Optional[datetime] = None