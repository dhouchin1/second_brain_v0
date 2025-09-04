# ──────────────────────────────────────────────────────────────────────────────
# File: scripts/init_users.py
# ──────────────────────────────────────────────────────────────────────────────
"""Create the users table and (optionally) a dev user.

Usage:
  python scripts/init_users.py                 # just ensure table exists
  python scripts/init_users.py --create-dev    # also create dev:changeme123
  python scripts/init_users.py --user alice --password secret --email a@b.c

Env:
  SQLITE_DB (default: notes.db)
"""
from __future__ import annotations
import argparse, os, sqlite3, bcrypt

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  email TEXT,
  hashed_password TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_conn():
    db = os.getenv("SQLITE_DB", "notes.db")
    con = sqlite3.connect(db)
    return con


def ensure_table() -> None:
    con = get_conn()
    con.execute(CREATE_SQL)
    con.commit()
    con.close()


def create_user(username: str, password: str, email: str | None = None) -> None:
    con = get_conn()
    hpw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    con.execute(
        "INSERT INTO users (username,email,hashed_password) VALUES (?,?,?)",
        (username, email, hpw),
    )
    con.commit()
    con.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--create-dev", action="store_true")
    p.add_argument("--user", type=str)
    p.add_argument("--password", type=str)
    p.add_argument("--email", type=str)
    args = p.parse_args()

    ensure_table()

    if args.create_dev:
        try:
            create_user("dev", "changeme123", "dev@example.com")
            print("Created dev user: dev / changeme123")
        except sqlite3.IntegrityError:
            print("Dev user already exists")
    elif args.user and args.password:
        try:
            create_user(args.user, args.password, args.email)
            print(f"Created user: {args.user}")
        except sqlite3.IntegrityError:
            print("Username already exists")

if __name__ == "__main__":
    main()


# ──────────────────────────────────────────────────────────────────────────────
# File: app_with_auth.py
# ──────────────────────────────────────────────────────────────────────────────
"""Full FastAPI app that includes:
- Public capture endpoints (/capture, /capture/audio)
- Search endpoints (/search)
- Auth: register/login (JSON + web forms) and logout (cookie)

Run:
  uvicorn app_with_auth:app --reload --host 0.0.0.0 --port 8082
"""
from __future__ import annotations
import os, sqlite3, jwt, bcrypt, datetime as dt
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

# Reuse routers from this scaffold
from api.routes_capture import router as capture_router
from api.routes_search import router as search_router
from services.jobs import JobRunner

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_MIN = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))

app = FastAPI(title="Second Brain — with auth")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

app.include_router(capture_router)
app.include_router(search_router)

runner = JobRunner(db_path=os.getenv('SQLITE_DB','notes.db'))
@app.on_event('startup')
def _start_worker():
    runner.start(app)
    _ensure_users_table()

# ─── DB helpers ─────────────────────────────────────────────────────────────

def get_conn():
    con = sqlite3.connect(os.getenv("SQLITE_DB","notes.db"))
    con.row_factory = sqlite3.Row
    return con

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  email TEXT,
  hashed_password TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

def _ensure_users_table():
    con = get_conn(); con.execute(CREATE_USERS); con.commit(); con.close()

# ─── Auth helpers ───────────────────────────────────────────────────────────

def get_user(username: str) -> Optional[sqlite3.Row]:
    con = get_conn()
    u = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    con.close()
    return u

def create_user(username: str, email: str | None, password: str) -> None:
    hpw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    con = get_conn()
    con.execute("INSERT INTO users (username,email,hashed_password) VALUES (?,?,?)",
                (username, email, hpw))
    con.commit(); con.close()

def verify_user(username: str, password: str) -> bool:
    u = get_user(username)
    if not u: return False
    return bcrypt.checkpw(password.encode("utf-8"), u["hashed_password"].encode("utf-8"))

def create_access_token(sub: str) -> str:
    now = dt.datetime.utcnow()
    payload = {"sub": sub, "iat": now, "exp": now + dt.timedelta(minutes=ACCESS_MIN)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def current_user_from_request(request: Request) -> Optional[sqlite3.Row]:
    # Prefer Authorization header; else fall back to cookie
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    token = None
    if auth.lower().startswith("bearer "):
        token = auth.split(" ",1)[1]
    elif request.cookies.get("access_token"):
        token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        return get_user(username) if username else None
    except Exception:
        return None

# ─── JSON Auth API ─────────────────────────────────────────────────────────
auth_api = APIRouter(prefix="/auth", tags=["auth"])

from pydantic import BaseModel
class RegisterIn(BaseModel):
    username: str
    password: str
    email: str | None = None

@auth_api.post("/register")
def register_json(body: RegisterIn):
    if get_user(body.username):
        raise HTTPException(status_code=400, detail="Username already exists")
    create_user(body.username, body.email, body.password)
    return {"ok": True}

@auth_api.post("/token")
def token_json(username: str = Form(...), password: str = Form(...)):
    if not verify_user(username, password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(sub=username)
    return {"access_token": token, "token_type": "bearer"}

app.include_router(auth_api)

# ─── Web UI: Register/Login/Logout ─────────────────────────────────────────-
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    u = current_user_from_request(request)
    if not u:
        return HTMLResponse(
            """
            <html><body>
              <h2>Second Brain</h2>
              <p>You are not logged in.</p>
              <p><a href="/auth">Register / Login</a></p>
            </body></html>
            """
        )
    return HTMLResponse(
        f"""
        <html><body>
          <h2>Second Brain</h2>
          <p>Welcome, <b>{u['username']}</b>!</p>
          <form action="/logout" method="get"><button type="submit">Logout</button></form>
        </body></html>
        """
    )

@app.get("/auth", response_class=HTMLResponse)
async def auth_page():
    return HTMLResponse(
        """
        <html><body>
          <h2>Register</h2>
          <form action="/auth/register_form" method="post">
            <input name="username" placeholder="username" required />
            <input name="email" placeholder="email" />
            <input type="password" name="password" placeholder="password" required />
            <button type="submit">Create account</button>
          </form>
          <hr/>
          <h2>Login</h2>
          <form action="/auth/login_form" method="post">
            <input name="username" placeholder="username" required />
            <input type="password" name="password" placeholder="password" required />
            <button type="submit">Login</button>
          </form>
        </body></html>
        """
    )

@app.post("/auth/register_form")
async def register_form(username: str = Form(...), password: str = Form(...), email: str | None = Form(None)):
    if get_user(username):
        return HTMLResponse("<p>Username already exists. <a href='/auth'>Back</a></p>", status_code=400)
    create_user(username, email, password)
    return RedirectResponse(url="/auth", status_code=302)

@app.post("/auth/login_form")
async def login_form(username: str = Form(...), password: str = Form(...)):
    if not verify_user(username, password):
        return HTMLResponse("<p>Invalid credentials. <a href='/auth'>Back</a></p>", status_code=401)
    token = create_access_token(sub=username)
    resp = RedirectResponse(url="/", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, samesite="lax")
    return resp

@app.get("/logout")
async def logout():
    resp = RedirectResponse(url="/")
    resp.delete_cookie("access_token")
    return resp


# ──────────────────────────────────────────────────────────────────────────────
# File: requirements.txt
# ──────────────────────────────────────────────────────────────────────────────
fastapi
uvicorn[standard]
python-multipart
bcrypt
PyJWT
watchfiles
pydantic
pydantic-settings
