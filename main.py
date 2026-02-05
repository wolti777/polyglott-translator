from datetime import timedelta
from io import BytesIO
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from openpyxl import Workbook
from pydantic import BaseModel

from database import engine, get_db, Base
from models import User, Glossary, GlossaryEntry
from auth import (
    create_access_token,
    create_user,
    authenticate_user,
    get_user_by_username,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from translator import translate_to_all_languages

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Polyglot Translator")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class TranslateRequest(BaseModel):
    text: str
    source_language: Optional[str] = None
    target_languages: Optional[list] = None
    enabled_services: Optional[dict] = None
    explanation_services: Optional[dict] = None


class SaveGlossaryRequest(BaseModel):
    spanish: Optional[str] = None
    german: Optional[str] = None
    polish: Optional[str] = None
    english: Optional[str] = None
    glossary_id: Optional[int] = None
    # Slot-based entries: slot1, slot2, slot3, slot4 with language_config
    slot1: Optional[str] = None
    slot2: Optional[str] = None
    slot3: Optional[str] = None
    slot4: Optional[str] = None
    language_config: Optional[list] = None  # e.g., ["german", "spanish", "french", "english"]


class CreateGlossaryRequest(BaseModel):
    name: str


# ==================== Auth Routes ====================


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse(url="/translator", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse(url="/translator", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
        )

    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    response = RedirectResponse(url="/translator", status_code=303)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse(url="/translator", status_code=303)
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    # Validate input
    if len(username) < 3:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Username must be at least 3 characters"},
        )

    if len(password) < 6:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Password must be at least 6 characters"},
        )

    if password != password_confirm:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Passwords do not match"},
        )

    # Check if user already exists
    existing_user = get_user_by_username(db, username)
    if existing_user:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Username already exists"},
        )

    # Create user
    user = create_user(db, username, password)

    # Auto-login after registration
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    response = RedirectResponse(url="/translator", status_code=303)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response


# ==================== Translator Routes ====================


@app.get("/translator", response_class=HTMLResponse)
async def translator_page(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        "translator.html", {"request": request, "user": user}
    )


@app.post("/translate")
async def translate(
    request: Request,
    translate_request: TranslateRequest,
    db: Session = Depends(get_db),
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    text = translate_request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    translations = translate_to_all_languages(
        text,
        translate_request.source_language,
        translate_request.target_languages,
        translate_request.enabled_services,
        translate_request.explanation_services
    )
    return translations


# ==================== Glossary Routes ====================


def get_or_create_default_glossary(db: Session, user_id: int) -> Glossary:
    """Get user's default glossary or create one if it doesn't exist."""
    default = db.query(Glossary).filter(
        Glossary.user_id == user_id,
        Glossary.is_default == True
    ).first()

    if not default:
        default = Glossary(
            user_id=user_id,
            name="Hauptglossar",
            is_default=True
        )
        db.add(default)
        db.commit()
        db.refresh(default)

    return default


@app.get("/glossaries")
async def list_glossaries(request: Request, db: Session = Depends(get_db)):
    """List all glossaries for the current user."""
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Ensure default glossary exists
    get_or_create_default_glossary(db, user.id)

    glossaries = db.query(Glossary).filter(
        Glossary.user_id == user.id
    ).order_by(Glossary.is_default.desc(), Glossary.name).all()

    return [
        {
            "id": g.id,
            "name": g.name,
            "is_default": g.is_default,
            "entry_count": len(g.entries)
        }
        for g in glossaries
    ]


@app.post("/glossaries")
async def create_glossary(
    request: Request,
    glossary_request: CreateGlossaryRequest,
    db: Session = Depends(get_db),
):
    """Create a new glossary."""
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    name = glossary_request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    # Check if glossary with same name exists
    existing = db.query(Glossary).filter(
        Glossary.user_id == user.id,
        Glossary.name == name
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Glossary with this name already exists")

    glossary = Glossary(
        user_id=user.id,
        name=name,
        is_default=False
    )
    db.add(glossary)
    db.commit()
    db.refresh(glossary)

    return {
        "id": glossary.id,
        "name": glossary.name,
        "is_default": glossary.is_default,
        "entry_count": 0
    }


@app.post("/glossary/save")
async def save_to_glossary(
    request: Request,
    glossary_request: SaveGlossaryRequest,
    db: Session = Depends(get_db),
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Get glossary (use specified or default)
    if glossary_request.glossary_id:
        glossary = db.query(Glossary).filter(
            Glossary.id == glossary_request.glossary_id,
            Glossary.user_id == user.id
        ).first()
        if not glossary:
            raise HTTPException(status_code=404, detail="Glossary not found")
    else:
        glossary = get_or_create_default_glossary(db, user.id)

    # Handle slot-based format with language_config
    if glossary_request.language_config and glossary_request.slot1 is not None:
        # Map slots to database columns based on language_config
        lang_to_slot = {}
        slots = [glossary_request.slot1, glossary_request.slot2,
                 glossary_request.slot3, glossary_request.slot4]
        for i, lang in enumerate(glossary_request.language_config):
            if i < len(slots):
                lang_to_slot[lang] = slots[i]

        entry = GlossaryEntry(
            user_id=user.id,
            glossary_id=glossary.id,
            spanish=lang_to_slot.get("spanish", ""),
            german=lang_to_slot.get("german", ""),
            polish=lang_to_slot.get("polish", ""),
            english=lang_to_slot.get("english", ""),
        )
    else:
        # Legacy format with direct column names
        entry = GlossaryEntry(
            user_id=user.id,
            glossary_id=glossary.id,
            spanish=glossary_request.spanish or "",
            german=glossary_request.german or "",
            polish=glossary_request.polish or "",
            english=glossary_request.english or "",
        )
    db.add(entry)
    db.commit()

    return {"success": True, "message": f"Entry saved to {glossary.name}"}


@app.get("/glossary/recent")
async def get_recent_entries(
    request: Request,
    glossary_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get the 4 most recent entries for a glossary."""
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Get specific glossary or default
    if glossary_id:
        glossary = db.query(Glossary).filter(
            Glossary.id == glossary_id,
            Glossary.user_id == user.id
        ).first()
        if not glossary:
            raise HTTPException(status_code=404, detail="Glossary not found")
    else:
        glossary = get_or_create_default_glossary(db, user.id)

    # Get 4 most recent entries
    entries = (
        db.query(GlossaryEntry)
        .filter(GlossaryEntry.glossary_id == glossary.id)
        .order_by(GlossaryEntry.created_at.desc())
        .limit(4)
        .all()
    )

    # Return all 4 language columns - frontend will display based on settings
    return [
        {
            "spanish": e.spanish,
            "german": e.german,
            "polish": e.polish,
            "english": e.english,
            # Include all for dynamic display
            "entries": {
                "spanish": e.spanish,
                "german": e.german,
                "polish": e.polish,
                "english": e.english,
            }
        }
        for e in entries
    ]


@app.get("/glossary/export")
async def export_glossary(
    request: Request,
    glossary_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # Get specific glossary or default
    if glossary_id:
        glossary = db.query(Glossary).filter(
            Glossary.id == glossary_id,
            Glossary.user_id == user.id
        ).first()
        if not glossary:
            raise HTTPException(status_code=404, detail="Glossary not found")
    else:
        glossary = get_or_create_default_glossary(db, user.id)

    # Get entries for the glossary
    entries = (
        db.query(GlossaryEntry)
        .filter(GlossaryEntry.glossary_id == glossary.id)
        .order_by(GlossaryEntry.created_at.desc())
        .all()
    )

    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = glossary.name[:31]  # Excel sheet names max 31 chars

    # Header row
    headers = ["Spanish", "German", "Polish", "English", "Created At"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = cell.font.copy(bold=True)

    # Data rows
    for row, entry in enumerate(entries, 2):
        ws.cell(row=row, column=1, value=entry.spanish)
        ws.cell(row=row, column=2, value=entry.german)
        ws.cell(row=row, column=3, value=entry.polish)
        ws.cell(row=row, column=4, value=entry.english)
        ws.cell(row=row, column=5, value=entry.created_at.strftime("%Y-%m-%d %H:%M"))

    # Adjust column widths
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column].width = adjusted_width

    # Save to BytesIO
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"{glossary.name}_{user.username}.xlsx".replace(" ", "_")

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
