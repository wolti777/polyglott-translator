from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    email_verified = Column(Boolean, default=False)
    language_config = Column(Text, nullable=True)  # JSON: user's language settings
    created_at = Column(DateTime, default=datetime.utcnow)

    glossaries = relationship("Glossary", back_populates="user")
    glossary_entries = relationship("GlossaryEntry", back_populates="user")
    api_keys = relationship("UserApiKey", back_populates="user")


class UserApiKey(Base):
    __tablename__ = "user_api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    service = Column(String(50), nullable=False)  # "deepl", "pons", "google"
    api_key = Column(String(500), nullable=False)  # encrypted
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="api_keys")

    __table_args__ = (
        UniqueConstraint("user_id", "service", name="uq_user_service"),
    )


class Glossary(Base):
    __tablename__ = "glossaries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="glossaries")
    entries = relationship("GlossaryEntry", back_populates="glossary")


class GlossaryEntry(Base):
    __tablename__ = "glossary_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    glossary_id = Column(Integer, ForeignKey("glossaries.id"), nullable=True)
    spanish = Column(String(500))
    german = Column(String(500))
    polish = Column(String(500))
    english = Column(String(500))
    french = Column(String(500))
    italian = Column(String(500))
    portuguese = Column(String(500))
    dutch = Column(String(500))
    russian = Column(String(500))
    learning_rate = Column(Integer, default=0)
    total_learning_rate = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="glossary_entries")
    glossary = relationship("Glossary", back_populates="entries")
