"""
Achievement Manager - Saavutusten hallinta ja tarkistus
"""

import sqlite3
import datetime
from models.models import Achievement

# Saavutusten määrittelyt
ENHANCED_ACHIEVEMENTS = {
    'first_steps': Achievement(
        'first_steps', 
        'Ensimmäiset askeleet', 
        'Vastasit ensimmäiseen kysymykseen', 
        '🌟'
    ),
    'quick_learner': Achievement(
        'quick_learner', 
        'Nopea oppija', 
        'Vastasit 10 kysymykseen alle 10 sekunnissa', 
        '⚡'
    ),
    'perfectionist': Achievement(
        'perfectionist', 
        'Perfektionisti', 
        '100% oikein 20 kysymyksessä peräkkäin', 
        '💯'
    ),
    'dedicated': Achievement(
        'dedicated', 
        'Omistautunut', 
        'Vastasit 100 kysymykseen', 
        '📚'
    ),
    'expert': Achievement(
        'expert', 
        'Asiantuntija', 
        'Vastasit 500 kysymykseen', 
        '🎓'
    ),
    'master': Achievement(
        'master', 
        'Mestari', 
        'Vastasit 1000 kysymykseen', 
        '👑'
    ),
    'streak_3': Achievement(
        'streak_3', 
        'Kolmen päivän putki', 
        'Harjoittelit 3 päivää peräkkäin', 
        '🔥'
    ),
    'streak_7': Achievement(
        'streak_7', 
        'Viikon putki', 
        'Harjoittelit 7 päivää peräkkäin', 
        '🔥🔥'
    ),
    'streak_30': Achievement(
        'streak_30', 
        'Kuukauden putki', 
        'Harjoittelit 30 päivää peräkkäin', 
        '🔥🔥🔥'
    ),
    'category_master_farmakologia': Achievement(
        'category_master_farmakologia', 
        'Farmakologian mestari', 
        'Sait 90% farmakologia-kategorian kysymyksistä oikein', 
        '💊'
    ),
    'category_master_annosjakelu': Achievement(
        'category_master_annosjakelu', 
        'Annosjakelun mestari', 
        'Sait 90% annosjakelu-kategorian kysymyksistä oikein', 
        '📦'
    ),
    'simulation_complete': Achievement(
        'simulation_complete', 
        'Simulaattori', 
        'Suoritit ensimmäisen koesimulaation', 
        '🎯'
    ),
    'simulation_perfect': Achievement(
        'simulation_perfect', 
        'Täydellinen simulaatio', 
        'Sait 100% oikein koesimulaatiossa', 
        '🏆'
    ),
    'early_bird': Achievement(
        'early_bird', 
        'Aamulintu', 
        'Harjoittelit ennen klo 8:00', 
        '🌅'
    ),
    'night_owl': Achievement(
        'night_owl', 
        'Yöpöllö', 
        'Harjoittelit klo 22:00 jälkeen', 
        '🦉'
    ),
    'speed_demon': Achievement(
        'speed_demon', 
        'Salamannopea', 
        'Vastasit kysymykseen alle 5 sekunnissa (oikein)', 
        '💨'
    ),
}


class EnhancedAchievementManager:
    """Saavutusten hallinta ja tarkistus."""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.ENHANCED_ACHIEVEMENTS = ENHANCED_ACHIEVEMENTS
    
    def check_achievements(self, user_id, context=None):
        """
        Tarkistaa ja avaa uudet saavutukset tietylle käyttäjälle.
        
        Args:
            user_id: Käyttäjän ID
            context: Lisätietoja nykyisestä tilanteesta (esim. fast_answer, simulation_perfect)
        
        Returns:
            Lista uusien saavutusten ID:itä
        """
        new_achievements = []
        context = context or {}
        
        with sqlite3.connect(self.db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Hae jo avatut saavutukset
            unlocked = conn.execute(
                "SELECT achievement_id FROM user_achievements WHERE user_id = ?", 
                (user_id,)
            ).fetchall()
            unlocked_ids = {row['achievement_id'] for row in unlocked}
            
            # Lista tarkistettavista saavutuksista ja niiden funktioista
            achievements_to_check = [
                ('first_steps', self.check_first_steps),
                ('quick_learner', self.check_quick_learner),
                ('perfectionist', self.check_perfectionist),
                ('dedicated', self.check_dedicated),
                ('expert', self.check_expert),
                ('master', self.check_master),
                ('streak_3', self.check_streak_3),
                ('streak_7', self.check_streak_7),
                ('streak_30', self.check_streak_30),
                ('category_master_farmakologia', lambda c, u: self.check_category_master(c, u, 'farmakologia')),
                ('category_master_annosjakelu', lambda c, u: self.check_category_master(c, u, 'annosjakelu')),
                ('simulation_complete', self.check_simulation_complete),
                ('early_bird', self.check_early_bird),
                ('night_owl', self.check_night_owl),
            ]
            
            # Konteksti-riippuvaiset saavutukset
            if context.get('simulation_perfect'):
                achievements_to_check.append(('simulation_perfect', lambda c, u: True))
            
            if context.get('fast_answer') and context['fast_answer'] < 5:
                achievements_to_check.append(('speed_demon', lambda c, u: True))
            
            # Tarkista jokainen saavutus
            for achievement_id, check_func in achievements_to_check:
                if achievement_id not in unlocked_ids:
                    try:
                        if check_func(conn, user_id):
                            self.unlock_achievement(conn, user_id, achievement_id)
                            new_achievements.append(achievement_id)
                            print(f"✅ Saavutus avattu: {achievement_id} (käyttäjä: {user_id})")
                    except Exception as e:
                        print(f"❌ Virhe saavutuksen {achievement_id} tarkistuksessa: {e}")
        
        return new_achievements

    # ========== SAAVUTUSTARKISTUKSET ==========

    def check_first_steps(self, conn, user_id):
        """Vastasi ensimmäiseen kysymykseen."""
        count = conn.execute(
            "SELECT COUNT(*) as count FROM question_attempts WHERE user_id = ?", 
            (user_id,)
        ).fetchone()['count']
        return count >= 1

    def check_quick_learner(self, conn, user_id):
        """Vastasi 10 kysymykseen alle 10 sekunnissa."""
        count = conn.execute(
            "SELECT COUNT(*) as count FROM question_attempts WHERE user_id = ? AND time_taken < 10", 
            (user_id,)
        ).fetchone()['count']
        return count >= 10

    def check_perfectionist(self, conn, user_id):
        """100% oikein 20 kysymyksessä peräkkäin."""
        rows = conn.execute(
            "SELECT correct FROM question_attempts WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20", 
            (user_id,)
        ).fetchall()
        
        if len(rows) < 20:
            return False
        
        return all(row['correct'] for row in rows)

    def check_dedicated(self, conn, user_id):
        """Vastasi 100 kysymykseen."""
        count = conn.execute(
            "SELECT COUNT(*) as count FROM question_attempts WHERE user_id = ?", 
            (user_id,)
        ).fetchone()['count']
        return count >= 100

    def check_expert(self, conn, user_id):
        """Vastasi 500 kysymykseen."""
        count = conn.execute(
            "SELECT COUNT(*) as count FROM question_attempts WHERE user_id = ?", 
            (user_id,)
        ).fetchone()['count']
        return count >= 500

    def check_master(self, conn, user_id):
        """Vastasi 1000 kysymykseen."""
        count = conn.execute(
            "SELECT COUNT(*) as count FROM question_attempts WHERE user_id = ?", 
            (user_id,)
        ).fetchone()['count']
        return count >= 1000

    def check_streak_3(self, conn, user_id):
        """Harjoitteli 3 päivää peräkkäin."""
        return self._check_streak(conn, user_id, 3)

    def check_streak_7(self, conn, user_id):
        """Harjoitteli 7 päivää peräkkäin."""
        return self._check_streak(conn, user_id, 7)

    def check_streak_30(self, conn, user_id):
        """Harjoitteli 30 päivää peräkkäin."""
        return self._check_streak(conn, user_id, 30)

    def _check_streak(self, conn, user_id, days):
        """Apufunktio putken tarkistamiseen."""
        # Hae viimeiset X päivää joina käyttäjä on harjoitellut
        rows = conn.execute("""
            SELECT DISTINCT date(timestamp) as practice_date 
            FROM question_attempts 
            WHERE user_id = ? 
            ORDER BY practice_date DESC 
            LIMIT ?
        """, (user_id, days)).fetchall()
        
        if len(rows) < days:
            return False
        
        # Tarkista että päivät ovat peräkkäisiä
        from datetime import datetime, timedelta
        dates = [datetime.strptime(row['practice_date'], '%Y-%m-%d').date() for row in rows]
        
        for i in range(len(dates) - 1):
            if (dates[i] - dates[i + 1]).days != 1:
                return False
        
        return True

    def check_category_master(self, conn, user_id, category):
        """Sai 90% kategorian kysymyksistä oikein."""
        result = conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN qa.correct = 1 THEN 1 ELSE 0 END) as correct
            FROM question_attempts qa
            JOIN questions q ON qa.question_id = q.id
            WHERE qa.user_id = ? AND q.category = ?
        """, (user_id, category)).fetchone()
        
        if result['total'] < 20:  # Vähintään 20 kysymystä kategoriasta
            return False
        
        success_rate = result['correct'] / result['total']
        return success_rate >= 0.9

    def check_simulation_complete(self, conn, user_id):
        """Suoritti ensimmäisen koesimulaation."""
        # Tarkista onko study_sessions taulua
        try:
            count = conn.execute("""
                SELECT COUNT(*) as count 
                FROM study_sessions 
                WHERE user_id = ? AND session_type = 'simulation' AND end_time IS NOT NULL
            """, (user_id,)).fetchone()['count']
            return count >= 1
        except:
            # Jos taulua ei ole, käytä question_attempts määrää
            count = conn.execute(
                "SELECT COUNT(*) as count FROM question_attempts WHERE user_id = ?", 
                (user_id,)
            ).fetchone()['count']
            return count >= 50

    def check_early_bird(self, conn, user_id):
        """Harjoitteli ennen klo 8:00."""
        count = conn.execute("""
            SELECT COUNT(*) as count 
            FROM question_attempts 
            WHERE user_id = ? AND time(timestamp) < '08:00:00'
        """, (user_id,)).fetchone()['count']
        return count >= 1

    def check_night_owl(self, conn, user_id):
        """Harjoitteli klo 22:00 jälkeen."""
        count = conn.execute("""
            SELECT COUNT(*) as count 
            FROM question_attempts 
            WHERE user_id = ? AND time(timestamp) >= '22:00:00'
        """, (user_id,)).fetchone()['count']
        return count >= 1

    # ========== MUUT METODIT ==========

    def unlock_achievement(self, conn, user_id, achievement_id):
        """
        Tallentaa avatun saavutuksen käyttäjälle.
        
        Args:
            conn: SQLite connection
            user_id: Käyttäjän ID
            achievement_id: Saavutuksen ID
        """
        try:
            conn.execute("""
                INSERT OR IGNORE INTO user_achievements (user_id, achievement_id, unlocked_at) 
                VALUES (?, ?, datetime('now'))
            """, (user_id, achievement_id))
            conn.commit()
        except Exception as e:
            print(f"Virhe saavutuksen tallennuksessa: {e}")
    
    def get_unlocked_achievements(self, user_id):
        """
        Hakee kaikki käyttäjän avaamat saavutukset.
        
        Args:
            user_id: Käyttäjän ID
        
        Returns:
            Lista Achievement-objekteja
        """
        with sqlite3.connect(self.db_manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM user_achievements WHERE user_id = ?", 
                (user_id,)
            ).fetchall()
            
            achievements = []
            for row in rows:
                ach_id = row['achievement_id']
                if ach_id in ENHANCED_ACHIEVEMENTS:
                    ach = ENHANCED_ACHIEVEMENTS[ach_id]
                    # Luo uusi instanssi jossa unlocked tiedot
                    unlocked_ach = Achievement(
                        id=ach.id,
                        name=ach.name,
                        description=ach.description,
                        icon=ach.icon,
                        unlocked=True,
                        unlocked_at=row['unlocked_at']
                    )
                    achievements.append(unlocked_ach)
            
            return achievements
    
    def get_achievement_progress(self, user_id):
        """
        Hakee käyttäjän edistymisen saavutuksissa.
        
        Args:
            user_id: Käyttäjän ID
        
        Returns:
            Dictionary joka sisältää edistymistiedot
        """
        unlocked = self.get_unlocked_achievements(user_id)
        total = len(ENHANCED_ACHIEVEMENTS)
        unlocked_count = len(unlocked)
        
        return {
            'total': total,
            'unlocked': unlocked_count,
            'percentage': round((unlocked_count / total) * 100, 1) if total > 0 else 0,
            'unlocked_achievements': unlocked
        }