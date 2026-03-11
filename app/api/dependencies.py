from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.teams_service import TeamsPoster


def get_teams_poster(settings: Settings = Depends(get_settings)) -> TeamsPoster:
    return TeamsPoster(power_automate_url=settings.POWER_AUTOMATE_URL)
