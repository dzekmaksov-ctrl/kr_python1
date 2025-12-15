from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional

# User schemas
class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)

class UserCreate(UserBase):
    password: str = Field(min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True  # Исправлено с orm_mode

# Card schemas
class CardBase(BaseModel):
    front_text: str = Field(min_length=1, max_length=200)
    back_text: str = Field(min_length=1, max_length=200)
    example: Optional[str] = Field(None, max_length=500)
    language: str = Field("english", max_length=50)
    difficulty: int = Field(1, ge=1, le=5)
    is_public: bool = Field(False, description="Видна ли карточка другим пользователям")

class CardCreate(CardBase):
    pass

class CardUpdate(BaseModel):
    front_text: Optional[str] = Field(None, min_length=1, max_length=200)
    back_text: Optional[str] = Field(None, min_length=1, max_length=200)
    example: Optional[str] = Field(None, max_length=500)
    language: Optional[str] = Field(None, max_length=50)
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    is_public: Optional[bool] = Field(None, description="Видна ли карточка другим пользователям")

class CardResponse(CardBase):
    id: int
    user_id: int
    next_review: datetime
    review_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True  # Исправлено с orm_mode

# Token schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[int] = None

# Stats schema
class StatsResponse(BaseModel):
    user_id: int
    total_cards: int
    due_cards: int
    average_difficulty: float
    total_reviews: int
    progress_percentage: float
    public_cards_count: int