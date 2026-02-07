from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    glossaries = relationship("Glossary", back_populates="user")
    glossary_entries = relationship("GlossaryEntry", back_populates="user")


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
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="glossary_entries")
    glossary = relationship("Glossary", back_populates="entries")
