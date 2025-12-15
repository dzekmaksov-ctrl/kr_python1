# main.py
from fastapi import FastAPI, HTTPException, Query, Path, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List
import sqlite3
from datetime import datetime, timedelta, date
from pathlib import Path as PathLib
import os

# Импорт из ваших модулей
from auth import get_password_hash, verify_password, create_access_token, verify_token, create_user_access_token
from database import get_db, init_db
from models import User, Card
from schemas import UserCreate, UserLogin, CardCreate, CardUpdate, CardResponse, UserResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, text

app = FastAPI(
    title="Vocabulary Learning API",
    description="API для изучения иностранных слов с карточками",
    version="1.0.0"
)

# Подключаем статические файлы и шаблоны
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

security = HTTPBearer()

# ========== DATABASE INIT ==========
init_db()  # Инициализируем БД при старте

# ========== DEPENDENCIES ==========
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Получить текущего пользователя из JWT токена"""
    token = credentials.credentials
    payload = verify_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id: int = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user

# ========== HELPER FUNCTIONS ==========
def should_review_today(created_at: datetime, review_count: int) -> bool:
    """Определяет, нужно ли повторять карточку сегодня"""
    days_since_creation = (datetime.utcnow() - created_at).days
    
    # Алгоритм интервальных повторений (по дням)
    if review_count == 0:
        return days_since_creation >= 1  # Первое повторение через 1 день
    elif review_count == 1:
        return days_since_creation >= 3  # Второе через 3 дня
    elif review_count == 2:
        return days_since_creation >= 7  # Третье через неделю
    elif review_count == 3:
        return days_since_creation >= 14  # Четвертое через 2 недели
    elif review_count == 4:
        return days_since_creation >= 30  # Пятое через месяц
    else:
        # После 5 повторений - карточка освоена, повторять раз в месяц
        return days_since_creation % 30 == 0

def calculate_progress(user_id: int, db: Session) -> dict:
    """Расчет прогресса изучения (автоматический)"""
    # Общее количество карточек
    cards = db.query(Card).filter(Card.user_id == user_id).all()
    total_cards = len(cards)
    
    if total_cards == 0:
        return {
            "total_cards": 0,
            "due_today": 0,
            "mastered_cards": 0,
            "total_reviews": 0,
            "daily_progress": 0,
            "overall_progress": 0,
            "streak_days": 0,
            "level": 1,
            "achievements": [],
            "next_level_cards": 10
        }
    
    # Автоматически обновляем повторения для карточек
    due_today = 0
    mastered_cards = 0
    total_reviews = 0
    today = datetime.utcnow().date()
    
    for card in cards:
        # Проверяем, нужно ли повторять карточку сегодня
        if should_review_today(card.created_at, card.review_count):
            due_today += 1
        
        # Карточка освоена после 5+ повторений
        if card.review_count >= 5:
            mastered_cards += 1
        
        total_reviews += card.review_count
    
    # Рассчитываем прогресс
    if total_cards > 0:
        # Процент освоенных карточек
        mastery_percentage = (mastered_cards / total_cards) * 100
        
        # Активность (чем больше карточек, тем выше активность)
        activity_score = min(100, (total_cards / 20) * 100)
        
        # Общий прогресс (70% освоение + 30% активность)
        overall_progress = (mastery_percentage * 0.7) + (activity_score * 0.3)
        
        # Ежедневный прогресс (процент карточек для повторения сегодня)
        daily_progress = min(100, (due_today / total_cards) * 100) if total_cards > 0 else 0
    else:
        mastery_percentage = 0
        activity_score = 0
        overall_progress = 0
        daily_progress = 0
    
    # Уровень пользователя (основан на количестве карточек)
    level = min(10, (total_cards // 5) + 1)
    
    # Достижения
    achievements = []
    if total_cards >= 5:
        achievements.append("Новичок (5 карточек)")
    if total_cards >= 10:
        achievements.append("Любитель слов (10 карточек)")
    if mastered_cards >= 5:
        achievements.append("Мастер слов (5 освоенных карточек)")
    if total_cards >= 20:
        achievements.append("Коллекционер (20 карточек)")
    
    # Стрик дней (сколько дней подряд пользователь заходит)
    streak_days = 1  # Базовая реализация
    
    # Карточек до следующего уровня
    next_level_cards = max(0, (level * 5) - total_cards)
    
    return {
        "total_cards": total_cards,
        "due_today": due_today,
        "mastered_cards": mastered_cards,
        "total_reviews": total_reviews,
        "daily_progress": round(daily_progress, 1),
        "mastery_percentage": round(mastery_percentage, 1),
        "activity_score": round(activity_score, 1),
        "overall_progress": round(overall_progress, 1),
        "streak_days": streak_days,
        "level": level,
        "achievements": achievements,
        "next_level_cards": next_level_cards
    }

# ========== HTML PAGES ==========
@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Главная страница"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Страница входа"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Страница регистрации"""
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, user_id: Optional[int] = None):
    """Панель управления с автоматическим прогрессом"""
    if not user_id:
        return RedirectResponse("/login", status_code=302)
    
    db: Session = next(get_db())
    
    # Получаем пользователя
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    # Получаем уникальные карточки пользователя (без дубликатов по front_text)
    cards = db.query(Card).filter(
        Card.user_id == user_id
    ).order_by(Card.created_at.desc()).all()
    
    # Убираем дубликаты (оставляем только последнюю версию)
    unique_cards = []
    seen_words = set()
    for card in cards:
        if card.front_text not in seen_words:
            seen_words.add(card.front_text)
            unique_cards.append(card)
    
    # Рассчитываем прогресс
    progress = calculate_progress(user_id, db)
    
    # Ближайшие повторения (карточки для повторения сегодня)
    due_cards = []
    for card in unique_cards:
        if should_review_today(card.created_at, card.review_count):
            hours_until = max(0, 24 - ((datetime.utcnow() - card.created_at).seconds // 3600))
            due_cards.append({
                "id": card.id,
                "front_text": card.front_text[:20] + "..." if len(card.front_text) > 20 else card.front_text,
                "back_text": card.back_text,
                "review_count": card.review_count,
                "hours_until": hours_until
            })
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": {"id": user.id, "username": user.username, "email": user.email},
        "cards": unique_cards[:50],  # Ограничиваем показ
        "progress": progress,
        "due_cards": due_cards[:5],  # Показываем только 5 ближайших
        "total_cards": progress["total_cards"],
        "due_today": progress["due_today"]
    })

# ========== FORM HANDLERS ==========
@app.post("/login-form")
async def login_form_handler(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Обработка формы входа"""
    user = db.query(User).filter(User.email == email).first()
    
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Неверный email или пароль"
        })
    
    # Создаем JWT токен
    access_token = create_user_access_token(user.id)
    
    # Перенаправляем на dashboard с user_id
    response = RedirectResponse(f"/dashboard?user_id={user.id}", status_code=302)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response

@app.post("/register-form")
async def register_form_handler(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Обработка формы регистрации"""
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Пароли не совпадают"
        })
    
    if len(password) < 6:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Пароль должен быть не менее 6 символов"
        })
    
    # Проверяем существование пользователя
    existing_user = db.query(User).filter(
        (User.email == email) | (User.username == username)
    ).first()
    
    if existing_user:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Email или имя пользователя уже заняты"
        })
    
    # Создаем нового пользователя
    hashed_password = get_password_hash(password)
    new_user = User(
        email=email,
        username=username,
        hashed_password=hashed_password,
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Создаем JWT токен
    access_token = create_user_access_token(new_user.id)
    
    # Перенаправляем на dashboard
    response = RedirectResponse(f"/dashboard?user_id={new_user.id}", status_code=302)
    response.set_cookie(key="access_token", value=access_token, httponly=True)
    return response

@app.get("/logout")
async def logout_handler(request: Request):
    """Выход из системы"""
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(key="access_token")
    return response

# ========== API ENDPOINTS (JWT защищенные) ==========
@app.post("/api/token")
async def login_for_access_token(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Получить JWT токен для API"""
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password"
        )
    
    access_token = create_user_access_token(user.id)
    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id}

@app.post("/api/cards")
async def create_or_update_card_api(
    card_data: CardCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """API: Создать или обновить карточку (без дубликатов)"""
    # Проверяем, есть ли уже такая карточка у пользователя
    existing_card = db.query(Card).filter(
        Card.user_id == current_user.id,
        Card.front_text == card_data.front_text
    ).first()
    
    if existing_card:
        # Если карточка уже есть, увеличиваем счетчик повторений
        existing_card.review_count += 1
        existing_card.last_reviewed = datetime.utcnow()
        existing_card.next_review = datetime.utcnow() + timedelta(days=30)
        db.commit()
        db.refresh(existing_card)
        
        return JSONResponse({
            "success": True,
            "message": "Карточка обновлена (повторение засчитано)",
            "action": "updated",
            "review_count": existing_card.review_count,
            "card": CardResponse.from_orm(existing_card).dict()
        })
    else:
        # Создаем новую карточку
        new_card = Card(
            user_id=current_user.id,
            front_text=card_data.front_text,
            back_text=card_data.back_text,
            example=card_data.example,
            language=card_data.language,
            difficulty=card_data.difficulty,
            next_review=datetime.utcnow() + timedelta(days=1),  # Первое повторение завтра
            review_count=0,
            is_public=card_data.is_public,
            interval=1.0,
            ease_factor=2.5
        )
        
        db.add(new_card)
        db.commit()
        db.refresh(new_card)
        
        return JSONResponse({
            "success": True,
            "message": "Карточка создана",
            "action": "created",
            "card": CardResponse.from_orm(new_card).dict()
        })

@app.get("/api/cards")
async def get_cards_api(
    current_user: User = Depends(get_current_user),
    public_only: bool = Query(False, description="Показать только публичные карточки"),
    db: Session = Depends(get_db)
):
    """API: Получить карточки пользователя (без дубликатов)"""
    query = db.query(Card).filter(Card.user_id == current_user.id)
    
    if public_only:
        query = query.filter(Card.is_public == True)
    
    cards = query.order_by(Card.created_at.desc()).all()
    
    # Убираем дубликаты
    unique_cards = []
    seen_words = set()
    for card in cards:
        if card.front_text not in seen_words:
            seen_words.add(card.front_text)
            unique_cards.append(card)
    
    return JSONResponse([
        CardResponse.from_orm(card).dict() for card in unique_cards
    ])

@app.get("/api/cards/{card_id}")
async def get_card_api(
    card_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """API: Получить конкретную карточку"""
    card = db.query(Card).filter(
        Card.id == card_id,
        Card.user_id == current_user.id
    ).first()
    
    if not card:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    
    return JSONResponse(CardResponse.from_orm(card).dict())

@app.put("/api/cards/{card_id}")
async def update_card_api(
    card_id: int,
    card_update: CardUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """API: Обновить карточку"""
    card = db.query(Card).filter(
        Card.id == card_id,
        Card.user_id == current_user.id
    ).first()
    
    if not card:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    
    # Обновляем только переданные поля
    update_data = card_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(card, field, value)
    
    db.commit()
    db.refresh(card)
    
    return JSONResponse({
        "success": True,
        "message": "Карточка обновлена",
        "card": CardResponse.from_orm(card).dict()
    })

@app.delete("/api/cards/{card_id}")
async def delete_card_api(
    card_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """API: Удалить карточку"""
    card = db.query(Card).filter(
        Card.id == card_id,
        Card.user_id == current_user.id
    ).first()
    
    if not card:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    
    db.delete(card)
    db.commit()
    
    return JSONResponse({
        "success": True,
        "message": "Карточка удалена",
        "card_id": card_id
    })

@app.post("/api/cards/{card_id}/review")
async def review_card_api(
    card_id: int,
    quality: int = Query(..., ge=0, le=5, description="Качество ответа (0-5)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """API: Ручное повторение карточки (опционально)"""
    card = db.query(Card).filter(
        Card.id == card_id,
        Card.user_id == current_user.id
    ).first()
    
    if not card:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    
    # Увеличиваем счетчик повторений
    card.review_count += 1
    card.last_reviewed = datetime.utcnow()
    
    # Обновляем следующий повтор
    if quality >= 3:
        card.next_review = card.last_reviewed + timedelta(days=card.interval * card.ease_factor)
        card.ease_factor = max(1.3, card.ease_factor + 0.1 - (5 - quality) * 0.08)
    else:
        card.next_review = card.last_reviewed + timedelta(days=1)
        card.interval = 1.0
    
    db.commit()
    
    return JSONResponse({
        "success": True,
        "message": "Повторение зарегистрировано",
        "review_count": card.review_count,
        "next_review": card.next_review.isoformat()
    })

@app.get("/api/stats")
async def get_stats_api(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """API: Получить статистику (автоматический прогресс)"""
    progress = calculate_progress(current_user.id, db)
    
    return JSONResponse({
        "user_id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        **progress
    })

# ========== LEGACY API ENDPOINTS (без JWT для совместимости) ==========
@app.post("/api/legacy/cards")
async def create_or_update_card_legacy(
    user_id: int = Query(..., description="ID пользователя"),
    front_text: str = Query(..., description="Иностранное слово"),
    back_text: str = Query(..., description="Перевод"),
    example: Optional[str] = Query(None, description="Пример"),
    language: str = Query("english", description="Язык"),
    difficulty: int = Query(1, ge=1, le=5, description="Сложность 1-5"),
    db: Session = Depends(get_db)
):
    """Совместимый эндпоинт для создания/обновления карточки (без дубликатов)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Проверяем, есть ли уже такая карточка
    existing_card = db.query(Card).filter(
        Card.user_id == user_id,
        Card.front_text == front_text
    ).first()
    
    if existing_card:
        # Если карточка уже есть, увеличиваем счетчик повторений
        existing_card.review_count += 1
        existing_card.last_reviewed = datetime.utcnow()
        existing_card.next_review = datetime.utcnow() + timedelta(days=30)
        db.commit()
        
        return JSONResponse({
            "success": True,
            "message": "Карточка обновлена (повторение засчитано)",
            "action": "updated",
            "review_count": existing_card.review_count,
            "card_id": existing_card.id
        })
    else:
        # Создаем новую карточку
        new_card = Card(
            user_id=user_id,
            front_text=front_text,
            back_text=back_text,
            example=example,
            language=language,
            difficulty=difficulty,
            next_review=datetime.utcnow() + timedelta(days=1),
            review_count=0,
            is_public=False,
            interval=1.0,
            ease_factor=2.5
        )
        
        db.add(new_card)
        db.commit()
        db.refresh(new_card)
        
        return JSONResponse({
            "success": True,
            "message": "Карточка создана",
            "action": "created",
            "card_id": new_card.id
        })

@app.post("/api/legacy/cards/{card_id}/review")
async def review_card_legacy(
    card_id: int,
    quality: int = Query(..., ge=0, le=5, description="Качество ответа (0-5)"),
    db: Session = Depends(get_db)
):
    """Совместимый эндпоинт для ручных повторений (опционально)"""
    card = db.query(Card).filter(Card.id == card_id).first()
    
    if not card:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    
    # Увеличиваем счетчик повторений
    card.review_count += 1
    card.last_reviewed = datetime.utcnow()
    
    # Обновляем следующий повтор
    if quality >= 3:
        card.next_review = card.last_reviewed + timedelta(days=card.interval * card.ease_factor)
    else:
        card.next_review = card.last_reviewed + timedelta(days=1)
    
    db.commit()
    
    return JSONResponse({
        "success": True,
        "message": "Повторение зарегистрировано",
        "review_count": card.review_count,
        "next_review": card.next_review.strftime("%d.%m.%Y")
    })

@app.get("/api/legacy/stats")
async def get_stats_legacy(
    user_id: int = Query(..., description="ID пользователя"),
    db: Session = Depends(get_db)
):
    """Совместимый эндпоинт для статистики (автоматический прогресс)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    progress = calculate_progress(user_id, db)
    
    return JSONResponse({
        "user_id": user_id,
        "username": user.username,
        "progress": progress
    })

# ========== PUBLIC API ENDPOINTS ==========
@app.get("/api/users/{username}/cards")
async def get_user_public_cards(
    username: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """API: Получить публичные карточки пользователя"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    cards = db.query(Card).filter(
        Card.user_id == user.id,
        Card.is_public == True
    ).order_by(Card.created_at.desc()).offset(offset).limit(limit).all()
    
    # Убираем дубликаты
    unique_cards = []
    seen_words = set()
    for card in cards:
        if card.front_text not in seen_words:
            seen_words.add(card.front_text)
            unique_cards.append(card)
    
    return JSONResponse({
        "user": UserResponse.from_orm(user).dict(),
        "cards": [CardResponse.from_orm(card).dict() for card in unique_cards],
        "total": len(unique_cards),
        "limit": limit,
        "offset": offset
    })

@app.get("/profile/{username}")
async def view_public_profile(
    request: Request,
    username: str,
    db: Session = Depends(get_db)
):
    """Публичный профиль пользователя"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    cards = db.query(Card).filter(
        Card.user_id == user.id,
        Card.is_public == True
    ).order_by(Card.created_at.desc()).limit(50).all()
    
    # Убираем дубликаты
    unique_cards = []
    seen_words = set()
    for card in cards:
        if card.front_text not in seen_words:
            seen_words.add(card.front_text)
            unique_cards.append(card)
    
    cards_data = []
    for card in unique_cards:
        cards_data.append({
            "id": card.id,
            "front_text": card.front_text,
            "back_text": card.back_text,
            "example": card.example,
            "language": card.language,
            "created_at": card.created_at.strftime("%d.%m.%Y"),
            "difficulty": card.difficulty,
            "review_count": card.review_count
        })
    
    return templates.TemplateResponse("public_profile.html", {
        "request": request,
        "profile_user": user,
        "cards": cards_data,
        "total_cards": len(cards_data)
    })

# ========== HEALTH CHECK ==========
@app.get("/health")
async def health_check():
    """Проверка здоровья приложения"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# ========== RUN APPLICATION ==========
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)