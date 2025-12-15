# database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os
from contextlib import contextmanager

# Определяем URL базы данных
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Для PostgreSQL на Render
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    # Для локальной разработки с SQLite
    DATABASE_URL = "sqlite:///./vocabulary.db"

# Создаем движок
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=bool(os.getenv("SQL_DEBUG", False))
)

# Создаем фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для моделей
Base = declarative_base()

# Зависимость для получения сессии БД
def get_db():
    """Генератор сессий БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Функция для инициализации БД
def init_db():
    """Инициализация базы данных"""
    Base.metadata.create_all(bind=engine)
    print("✅ База данных инициализирована")