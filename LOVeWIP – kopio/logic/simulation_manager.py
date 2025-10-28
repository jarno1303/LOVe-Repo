# logic/simulation_manager.py
from datetime import datetime

def calculate_remaining_time(start_time_iso, total_duration_seconds):
    """Laskee jäljellä olevan ajan ISO-formatoidusta aikaleimasta."""
    if not start_time_iso:
        return total_duration_seconds
    
    try:
        # Muunnetaan ISO-merkkijono datetime-objektiksi
        start_time = datetime.fromisoformat(start_time_iso)
        
        # Lasketaan kulunut aika sekunteina
        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        
        # Palautetaan jäljellä oleva aika, vähintään 0
        return max(0, int(total_duration_seconds - elapsed_seconds))
    except (ValueError, TypeError):
        # Jos aikaleima on virheellinen, palautetaan koko aika
        return total_duration_seconds