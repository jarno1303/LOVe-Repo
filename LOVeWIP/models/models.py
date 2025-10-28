# -*- coding: utf-8 -*-
# models/models.py
from dataclasses import dataclass, field # Lisää 'field', jos tarvitset oletusarvoja listoille tms.
from typing import List, Optional
from datetime import datetime
from flask_login import UserMixin

@dataclass
class User(UserMixin):
    """
    Käyttäjämalli Flask-Login yhteensopiva.
    PÄIVITETTY: Lisätty organization_id ja helper-metodit rooleille.
    """
    id: int
    username: str
    email: str
    role: str = 'user' # Voi olla 'user', 'admin', 'superuser'

    # --- LISÄTTY MULTI-TENANT varten ---
    organization_id: Optional[int] = None # Voi olla None superuserille/irrallisille

    # --- Olemassa olevat kentät ---
    distractors_enabled: bool = False # Oletusarvo, jos ei haeta tietokannasta
    distractor_probability: int = 25 # Oletusarvo
    status: str = 'active'
    created_at: Optional[datetime] = None # Muuta tyyppi datetimeksi
    expires_at: Optional[datetime] = None

    # HUOM: 'password'-kenttää ei yleensä tarvita User-oliossa itsessään,
    # koska sitä käytetään vain autentikoinnissa (bcrypt.check_password_hash).
    # Poistetaan se mallista selkeyden vuoksi. Jos tarvitset sitä johonkin
    # muuhun, voit lisätä sen takaisin.
    # password: Optional[str] = None

    # --- UserMixin vaatimat metodit (osa automaattisia, osa hyvä lisätä) ---
    def get_id(self):
        """Palauttaa käyttäjän ID:n merkkijonona (vaadittu UserMixin)."""
        return str(self.id)

    @property
    def is_active(self):
        """Palauttaa True, jos käyttäjän status on 'active'."""
        # Vaikka user_loader tarkistaa tämän, on hyvä olla myös oliossa.
        return self.status == 'active'

    @property
    def is_authenticated(self):
        """Palauttaa aina True kirjautuneille käyttäjille."""
        return True

    @property
    def is_anonymous(self):
        """Palauttaa aina False kirjautuneille käyttäjille."""
        return False

    # --- Helper-metodit rooleille (käytetään app.py:ssä) ---
    def is_admin(self) -> bool:
        """Tarkistaa, onko käyttäjä admin TAI superuser."""
        return self.role in ['admin', 'superuser']

    def is_superuser(self) -> bool:
        """Tarkistaa, onko käyttäjä superuser."""
        return self.role == 'superuser'


@dataclass
class Question:
    """Kysymysmalli."""
    id: int
    question: str
    options: List[str] # Varmista, että tämä on lista
    correct: int
    explanation: str
    category: str
    difficulty: str

    # Käyttäjäkohtaiset progress-tiedot (tulevat LEFT JOINilla)
    times_shown: int = 0
    times_correct: int = 0
    last_shown: Optional[datetime] = None # Käytä Optionalia
    ease_factor: float = 2.5
    interval: int = 1
    mistake_acknowledged: bool = False # Lisätty aiemmissa vaiheissa

    # Muut kysymyskentät
    status: str = 'validated' # Muutettu oletus 'validated'
    validated_by: Optional[int] = None # Käytä Optionalia
    validated_at: Optional[datetime] = None # Käytä Optionalia
    validation_comment: Optional[str] = None
    question_normalized: Optional[str] = None # Käytä Optionalia
    created_at: Optional[datetime] = None # Käytä Optionalia
    hint_type: Optional[str] = None # Käytä Optionalia


# --- Muut dataclassit (pysyvät ennallaan) ---
# Voit säilyttää nämä, jos käytät niitä jossain sovelluksen osassa.

@dataclass
class QuestionAttempt:
    """Kysymykseen vastaamisen yritys."""
    id: int
    user_id: int
    question_id: int
    is_correct: bool # Muutettu booliksi
    time_taken: float # Muutettu floatiksi (sekunnit)
    timestamp: Optional[datetime] = None # Muutettu datetimeksi

@dataclass
class Achievement:
    """Saavutus."""
    id: str
    name: str
    description: str
    icon: str
    unlocked: bool = False
    unlocked_at: Optional[datetime] = None

# UserStats, DistractorAttempt, SpacedRepetitionCard, LearningSession, CategoryProgress
# dataclassit voivat myös pysyä ennallaan, jos käytät niitä esim. tilastojen koostamiseen.
# Muutin kuitenkin aikaleimat datetime-objekteiksi selkeyden vuoksi.

@dataclass
class UserStats:
    """Käyttäjän tilastot."""
    user_id: int
    total_attempts: int
    correct_attempts: int
    success_rate: float
    avg_time_per_question: float
    current_streak: int
    longest_streak: int # Muutettu nimestä 'best_streak'
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
    response_time: Optional[int] = None # Voi olla None, jos ei mitattu
    created_at: Optional[datetime] = None # Muutettu datetimeksi

# @dataclass
# class SpacedRepetitionCard: # Tämä ei välttämättä ole tarpeen, jos SR-logiikka on managerissa
#     # ...

# @dataclass
# class LearningSession: # Tämä ei välttämättä ole tarpeen, jos sessiologiikka on managerissa
#     # ...

# @dataclass
# class CategoryProgress: # Tämä ei välttämättä ole tarpeen, jos tilastot kootaan lennosta
#     # ...