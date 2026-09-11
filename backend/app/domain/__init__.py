"""Módulo Domain: Entidades de negócio puras, enums e invariantes de domínio.

Exporta a classe Base declarativa do SQLAlchemy e a totalidade dos
16 modelos de dados do ecossistema ThothCVs AI.
"""

from app.domain.base import Base
from app.domain.models import (
    Application,
    ApplicationContact,
    ApplicationNote,
    ApplicationStage,
    Certification,
    CoverLetter,
    Education,
    Experience,
    GeneratedResume,
    Language,
    Notification,
    Project,
    PromptSkill,
    Skill,
    User,
    UserSettings,
)

__all__ = [
    "Base",
    "User",
    "UserSettings",
    "Experience",
    "Education",
    "Certification",
    "Project",
    "Skill",
    "Language",
    "PromptSkill",
    "Application",
    "ApplicationStage",
    "ApplicationContact",
    "ApplicationNote",
    "GeneratedResume",
    "CoverLetter",
    "Notification",
]
