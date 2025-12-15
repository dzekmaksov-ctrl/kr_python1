from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    
    cards = relationship("Card", back_populates="owner", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"

class Card(Base):
    __tablename__ = "cards"
    
    id = Column(Integer, primary_key=True, index=True)
    front_text = Column(String, nullable=False)  # Иностранное слово
    back_text = Column(String, nullable=False)   # Перевод/объяснение
    example = Column(Text, nullable=True)        # Пример использования
    language = Column(String, default="english") # Язык слова
    difficulty = Column(Integer, default=1)      # Сложность 1-5
    next_review = Column(DateTime(timezone=True), server_default=func.now())
    review_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_public = Column(Boolean, default=False)   # Видна ли другим пользователям
    
    # Поля для алгоритма повторений
    interval = Column(Float, default=1.0)         # Интервал в днях
    ease_factor = Column(Float, default=2.5)      # Фактор легкости (SM2 алгоритм)
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    owner = relationship("User", back_populates="cards")
    
    def __repr__(self):
        return f"<Card(id={self.id}, front='{self.front_text[:20]}...', user_id={self.user_id})>"
    
    def calculate_next_review(self, quality: int):
        """
        Алгоритм SM-2 для интервальных повторений
        quality: 0-5 (0 - полное незнание, 5 - мгновенный правильный ответ)
        """
        if quality < 3:
            # Неправильный ответ - сброс интервала
            self.interval = 1.0
            self.ease_factor = max(1.3, self.ease_factor - 0.2)
        else:
            # Правильный ответ
            if self.review_count == 0:
                self.interval = 1.0
            elif self.review_count == 1:
                self.interval = 6.0
            else:
                self.interval = self.interval * self.ease_factor
            
            # Обновляем фактор легкости
            self.ease_factor = self.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
            self.ease_factor = max(1.3, self.ease_factor)
        
        # Конвертируем дни в часы для next_review
        hours_to_add = self.interval * 24
        self.next_review = datetime.datetime.utcnow() + datetime.timedelta(hours=hours_to_add)