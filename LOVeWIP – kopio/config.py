from dataclasses import dataclass, field
from typing import Dict

@dataclass
class AppConfig:
    theme: str = "modern_light"
    language: str = "fi"
    sound_effects: bool = True
    animations: bool = True
    auto_save_interval: int = 60
    spaced_repetition_enabled: bool = True
    daily_goal: int = 20
    
    notifications: Dict[str, bool] = field(default_factory=lambda: {
        'achievements': True,
        'daily_reminders': True,
        'study_suggestions': True,
        'streak_warnings': True
    })
    
THEMES = {
    'modern_light': {
        'primary': '#5A67D8', 'primary_light': '#7F9CF5', 'primary_dark': '#4C51BF',
        'secondary': '#718096', 'accent': '#ED64A6', 'success': '#48BB78',
        'success_light': '#A0AEC0', 'warning': '#ECC94B', 'danger': '#F56565',
        'light': '#F7FAFC', 'light_hover': '#EDF2F7', 'medium': '#A0AEC0',
        'dark': '#2D3748', 'white': '#FFFFFF', 'border': '#E2E8F0',
        'text_primary': '#2D3748', 'text_secondary': '#718096', 'gold': '#ECC94B',
        'silver': '#E2E8F0', 'bronze': '#CD7F32'
    },
    'dark': {
        'primary': '#bb86fc', 'primary_light': '#c998fc', 'primary_dark': '#a374e6',
        'secondary': '#03dac6', 'accent': '#cf6679', 'success': '#4caf50',
        'success_light': '#81c784', 'warning': '#ff9800', 'danger': '#f44336',
        'light': '#1e1e1e', 'light_hover': '#2d2d2d', 'medium': '#757575',
        'dark': '#121212', 'white': '#1e1e1e', 'border': '#333333',
        'text_primary': '#ffffff', 'text_secondary': '#b3b3b3', 'gold': '#ffd700',
        'silver': '#c0c0c0', 'bronze': '#cd7f32'
    }
}

config = AppConfig()
COLORS = THEMES[config.theme]