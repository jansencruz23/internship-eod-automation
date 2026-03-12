from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.teams.poster import TeamsPoster
from app.services.internity.poster import InternityPoster


def get_teams_poster(settings: Settings = Depends(get_settings)) -> TeamsPoster:
    return TeamsPoster(power_automate_url=settings.POWER_AUTOMATE_URL)


def get_internity_poster(
    settings: Settings = Depends(get_settings),
) -> InternityPoster:
    return InternityPoster(
        username=settings.INTERNITY_USERNAME,
        password=settings.INTERNITY_PASSWORD,
        form_url=settings.INTERNITY_FORM_URL,
    )
