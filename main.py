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
from models import User, GlossaryEntry
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


class SaveGlossaryRequest(BaseModel):
    spanish: str
    german: str
    polish: str
    english: str


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

    translations = translate_to_all_languages(text, translate_request.source_language)
    return translations


# ==================== Glossary Routes ====================


@app.post("/glossary/save")
async def save_to_glossary(
    request: Request,
    glossary_request: SaveGlossaryRequest,
    db: Session = Depends(get_db),
):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    entry = GlossaryEntry(
        user_id=user.id,
        spanish=glossary_request.spanish,
        german=glossary_request.german,
        polish=glossary_request.polish,
        english=glossary_request.english,
    )
    db.add(entry)
    db.commit()

    return {"success": True, "message": "Entry saved to glossary"}


@app.get("/glossary/export")
async def export_glossary(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    # Get all glossary entries for the user
    entries = (
        db.query(GlossaryEntry)
        .filter(GlossaryEntry.user_id == user.id)
        .order_by(GlossaryEntry.created_at.desc())
        .all()
    )

    # Create Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Glossary"

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

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=glossary_{user.username}.xlsx"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
