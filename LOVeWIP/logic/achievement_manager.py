import sqlite3
import datetime
from models.models import Achievement

# Saavutusten määrittelyt pysyvät ennallaan
ENHANCED_ACHIEVEMENTS = {
    'first_steps': Achievement('first_steps', 'Ensimmäiset askeleet', 'Vastasit ensimmäiseen kysymykseen', '🌟'),
    'quick_learner': Achievement('quick_learner', 'Nopea oppija', 'Vastasit 10 kysymykseen alle 10 sekunnissa', '⚡'),
    'perfectionist': Achievement('perfectionist', 'Perfektionisti', '100% oikein 20 kysymyksessä peräkkäin', '💯'),
    # ... ja niin edelleen, lisää loput saavutukset tähän
}

class EnhancedAchievementManager:
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def check_achievements(self, user_id, context=None):
        """Tarkistaa ja avaa uudet saavutukset tietylle käyttäjälle."""
        new_achievements = []
        
        with sqlite3.connect(self.db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            unlocked = conn.execute("SELECT achievement_id FROM user_achievements WHERE user_id = ?", (user_id,)).fetchall()
            unlocked_ids = {row['achievement_id'] for row in unlocked}
            
            # Lista tarkistettavista saavutuksista ja niiden funktioista
            achievements_to_check = [
                ('first_steps', self.check_first_steps),
                ('quick_learner', self.check_quick_learner),
                ('perfectionist', self.check_perfectionist),
            ]
            
            for achievement_id, check_func in achievements_to_check:
                if achievement_id not in unlocked_ids and check_func(conn, user_id):
                    self.unlock_achievement(conn, user_id, achievement_id)
                    new_achievements.append(achievement_id)
        
        return new_achievements

    # Tarkistusfunktiot ottavat nyt conn ja user_id parametreiksi
    def check_first_steps(self, conn, user_id):
        count = conn.execute("SELECT COUNT(*) FROM question_attempts WHERE user_id = ?", (user_id,)).fetchone()[0]
        return count >= 1
    
    def check_quick_learner(self, conn, user_id):
        count = conn.execute("SELECT COUNT(*) FROM question_attempts WHERE user_id = ? AND time_taken < 10", (user_id,)).fetchone()[0]
        return count >= 10

    def check_perfectionist(self, conn, user_id):
        rows = conn.execute("SELECT correct FROM question_attempts WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20", (user_id,)).fetchall()
        if len(rows) < 20: return False
        return all(row['correct'] for row in rows)

    def unlock_achievement(self, conn, user_id, achievement_id):
        """Tallentaa avatun saavutuksen käyttäjälle."""
        conn.execute("""
            INSERT OR IGNORE INTO user_achievements (user_id, achievement_id) VALUES (?, ?)
        """, (user_id, achievement_id))
    
    def get_unlocked_achievements(self, user_id):
        """Hakee kaikki käyttäjän avaamat saavutukset."""
        with sqlite3.connect(self.db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM user_achievements WHERE user_id = ?", (user_id,)).fetchall()
            
            achievements = []
            for row in rows:
                ach_id = row['achievement_id']
                if ach_id in ENHANCED_ACHIEVEMENTS:
                    ach = ENHANCED_ACHIEVEMENTS[ach_id]
                    ach.unlocked = True
                    ach.unlocked_at = row['unlocked_at']
                    achievements.append(ach)
            return achievements
