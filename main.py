from fastapi import FastAPI, Request, Form, Depends, status, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware
from datetime import datetime
import os, shutil, re

import models
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key='supersecretkey123')

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

templates = Jinja2Templates(directory="templates")
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def is_valid_email(email: str) -> bool:
    return re.match(r"^[\w\.-]+@[\w\.-]+\.com$", email) is not None

def is_strong_password(password: str) -> bool:
    return re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[A-Za-z\d]{8,}$', password) is not None

def get_lang(request: Request):
    return request.session.get('lang', 'ru')


active_connections = []

@app.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            for conn in active_connections:
                if conn != websocket:
                    await conn.send_text(f"🔔 {data}")
    except WebSocketDisconnect:
        active_connections.remove(websocket)


@app.get("/set_language/{lang_code}")
def set_language(lang_code: str, request: Request):
    if lang_code not in ("uk", "en"):
        lang_code = "uk"
    request.session['lang'] = lang_code
    referer = request.headers.get("referer") or "/"
    return RedirectResponse(referer, status_code=302)



@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    lang = get_lang(request)
    return templates.TemplateResponse("login.html", {"request": request, "lang": lang})

@app.get("/register", response_class=HTMLResponse)
def register_get(request: Request):
    lang = get_lang(request)
    return templates.TemplateResponse("register.html", {"request": request, "lang": lang})

@app.post("/register")
def register_post(request: Request, first_name: str = Form(...), last_name: str = Form(...),
                  email: str = Form(...), password: str = Form(...), role: str = Form(...),
                  db: Session = Depends(get_db)):
    lang = get_lang(request)
    if not is_valid_email(email):
        return templates.TemplateResponse("register.html", {"request": request, "msg": "Введите email с доменом .com", "lang": lang})
    if not is_strong_password(password):
        return templates.TemplateResponse("register.html", {
            "request": request,
            "msg": "Пароль должен быть не менее 8 символов, содержать заглавную букву, строчную и цифру",
            "lang": lang
        })
    if db.query(models.User).filter(models.User.email == email).first():
        return templates.TemplateResponse("register.html", {"request": request, "msg": "Email уже существует", "lang": lang})

    hashed = get_password_hash(password)
    user = models.User(first_name=first_name, last_name=last_name, email=email,
                       hashed_password=hashed, role=role)
    db.add(user)
    db.commit()
    return RedirectResponse("/", status_code=302)

@app.post("/login")
def login_post(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    lang = get_lang(request)
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "msg": "Неверные данные", "lang": lang})
    request.session['user_id'] = user.id
    request.session['role'] = user.role
    return RedirectResponse("/dashboard", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)



@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/", status_code=302)
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(status_code=403, detail="Unauthorized")
    lang = get_lang(request)
    return templates.TemplateResponse(f"dashboard_{user.role}.html", {"request": request, "user": user, "lang": lang})



@app.get("/calendar", response_class=HTMLResponse)
def calendar_view(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/", status_code=302)
    user = db.query(models.User).get(user_id)
    schedule = db.query(models.Lesson).filter(
        (models.Lesson.teacher_id == user_id) | (models.Lesson.student_email == user.email)
    ).all()
    lang = get_lang(request)
    return templates.TemplateResponse("calendar.html", {"request": request, "schedule": schedule, "user": user, "lang": lang})

@app.get("/add_schedule", response_class=HTMLResponse)
def add_schedule_get(request: Request):
    lang = get_lang(request)
    return templates.TemplateResponse("add_schedule.html", {"request": request, "lang": lang})

@app.post("/add_schedule")
def add_schedule_post(request: Request, dt_str: str = Form(...), subject: str = Form(...),
                 student_email: str = Form(...), db: Session = Depends(get_db)):
    teacher_id = request.session.get("user_id")
    if not teacher_id:
        return RedirectResponse("/", status_code=302)
    dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M")
    db.add(models.Lesson(subject=subject, datetime=dt, teacher_id=teacher_id, student_email=student_email))
    db.commit()
    return RedirectResponse("/calendar", status_code=302)


@app.get("/grades", response_class=HTMLResponse)
def grades(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/", status_code=302)
    user = db.query(models.User).get(user_id)
    lang = get_lang(request)
    if user.role == "teacher":
        return templates.TemplateResponse("grades.html", {"request": request, "user": user, "lang": lang})
    grades = db.query(models.Grade).filter(models.Grade.student_id == user_id).all()
    return templates.TemplateResponse("grades.html", {"request": request, "user": user, "grades": grades, "lang": lang})

@app.post("/add_grade")
def add_grade(request: Request, student_email: str = Form(...), subject: str = Form(...), grade: str = Form(...),
              db: Session = Depends(get_db)):
    teacher_id = request.session.get("user_id")
    if not teacher_id:
        return RedirectResponse("/", status_code=302)
    student = db.query(models.User).filter(models.User.email == student_email).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    db.add(models.Grade(subject=subject, grade=grade, teacher_id=teacher_id, student_id=student.id))
    db.commit()
    return RedirectResponse("/grades", status_code=302)


@app.get("/homework", response_class=HTMLResponse)
def homework_view(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/", status_code=302)
    user = db.query(models.User).get(user_id)
    lang = get_lang(request)
    if user.role == 'teacher':
        return templates.TemplateResponse("homework.html", {"request": request, "user": user, "lang": lang})
    homeworks = db.query(models.Homework).filter(models.Homework.student_id == user_id).all()
    return templates.TemplateResponse("homework.html", {"request": request, "user": user, "homeworks": homeworks, "lang": lang})

@app.post("/add_homework")
def add_homework(request: Request, title: str = Form(...), description: str = Form(...),
                 due_date: str = Form(...), student_email: str = Form(...), db: Session = Depends(get_db)):
    teacher_id = request.session.get("user_id")
    if not teacher_id:
        return RedirectResponse("/", status_code=302)
    student = db.query(models.User).filter(models.User.email == student_email).first()
    due = datetime.strptime(due_date, "%Y-%m-%d")
    db.add(models.Homework(title=title, description=description, due_date=due,
                           teacher_id=teacher_id, student_id=student.id))
    db.commit()
    return RedirectResponse("/homework", status_code=302)

@app.post("/submit_homework")
def submit_hw(request: Request, homework_id: int = Form(...), file: UploadFile = File(...),
              db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/", status_code=302)
    hw = db.query(models.Homework).get(homework_id)
    filename = f"{user_id}_{homework_id}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    hw.submission_file = filename
    db.commit()
    return RedirectResponse("/homework", status_code=302)


@app.get("/settings", response_class=HTMLResponse)
def get_settings(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/", status_code=302)
    user = db.query(models.User).get(user_id)
    lang = get_lang(request)
    return templates.TemplateResponse("settings.html", {"request": request, "user": user, "lang": lang})

@app.post("/settings")
def update_settings(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/", status_code=302)
    user = db.query(models.User).get(user_id)
    user.first_name = name
    user.email = email
    if password:
        user.hashed_password = get_password_hash(password)
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)
#uvicorn main:app --reload
