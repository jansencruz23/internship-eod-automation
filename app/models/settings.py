from sqlalchemy import Column, Integer, Boolean

from app.core.database import Base


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, default=1)
    auto_post_enabled = Column(Boolean, default=False)
