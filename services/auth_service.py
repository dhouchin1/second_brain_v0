"""
Authentication Service

Handles JWT tokens, password hashing, user authentication, and magic link functionality.
Extracted from app.py to provide clean separation of authentication concerns.
"""

import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Request, Header, HTTPException, status, Form, Query, Depends, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from config import settings


# --- Models ---

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class User(BaseModel):
    id: int
    username: str


class UserInDB(User):
    hashed_password: str


# --- Authentication Configuration ---

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
auth_scheme = HTTPBearer(auto_error=False)

SECRET_KEY = settings.secret_key
WEBHOOK_TOKEN = settings.webhook_token
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


class AuthService:
    """Service for handling authentication operations."""
    
    def __init__(self, get_conn_func):
        """Initialize auth service with database connection function."""
        self.get_conn = get_conn_func
    
    # --- Password Management ---
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Generate password hash."""
        return pwd_context.hash(password)
    
    # --- User Management ---
    
    def get_user(self, username: str) -> Optional[UserInDB]:
        """Get user by username."""
        conn = self.get_conn()
        c = conn.cursor()
        row = c.execute(
            "SELECT id, username, hashed_password FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        conn.close()
        if row:
            return UserInDB(id=row[0], username=row[1], hashed_password=row[2])
        return None
    
    def get_user_by_email(self, email: str) -> Optional[UserInDB]:
        """Get user by email address."""
        conn = self.get_conn()
        c = conn.cursor()
        
        # First check if email column exists, if not return None
        try:
            row = c.execute("""
                SELECT id, username, hashed_password, email 
                FROM users WHERE email = ?
            """, (email,)).fetchone()
        except Exception:
            # Email column doesn't exist yet
            conn.close()
            return None
        
        conn.close()
        if row:
            return UserInDB(id=row[0], username=row[1], hashed_password=row[2])
        return None
    
    def authenticate_user(self, username: str, password: str) -> Optional[UserInDB]:
        """Authenticate user with username and password."""
        user = self.get_user(username)
        if not user or not self.verify_password(password, user.hashed_password):
            return None
        return user
    
    # --- Token Management ---
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token."""
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def create_extended_access_token(self, data: dict, minutes: int = 60) -> str:
        """Create JWT access token with extended duration for recording sessions."""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=minutes)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def get_token_from_request(self, request: Request) -> Optional[str]:
        """Extract JWT token from request (cookie or authorization header)."""
        # First try to get from authorization cookie
        token = request.cookies.get("access_token")
        if token:
            return token
        
        # Then try authorization header
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header.split(" ")[1]
        
        return None
    
    def validate_and_decode_token(self, token: str) -> Optional[dict]:
        """Validate and decode JWT token, return payload if valid."""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError:
            return None
    
    def create_file_token(self, user_id: int, filename: str, ttl_seconds: int = 600) -> str:
        """Create a short-lived JWT token for accessing a specific file.
        
        Encodes: user id, filename, and expiry. Used for img/pdf links where
        cookies may not be reliably attached (e.g., cross-origin contexts).
        """
        expire = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        payload = {"uid": user_id, "fn": filename, "exp": expire}
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    # --- Magic Link Authentication ---
    
    def create_magic_link_token(self) -> str:
        """Generate a cryptographically secure random token for magic links."""
        return secrets.token_urlsafe(32)
    
    def store_magic_link_token(self, email: str, token: str, expires_minutes: int = 15) -> bool:
        """Store magic link token in database with expiration."""
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            # Create magic_links table if it doesn't exist
            c.execute("""
                CREATE TABLE IF NOT EXISTS magic_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    token TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    user_agent TEXT,
                    ip_address TEXT
                )
            """)
            
            now = datetime.utcnow()
            expires_at = now + timedelta(minutes=expires_minutes)
            
            c.execute("""
                INSERT INTO magic_links (email, token, created_at, expires_at)
                VALUES (?, ?, ?, ?)
            """, (email, token, now.isoformat(), expires_at.isoformat()))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error storing magic link token: {e}")
            return False
    
    def validate_magic_link_token(self, token: str) -> Optional[str]:
        """Validate magic link token and return email if valid, mark as used."""
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            # Find unused, non-expired token
            now = datetime.utcnow().isoformat()
            row = c.execute("""
                SELECT email FROM magic_links 
                WHERE token = ? AND used = FALSE AND expires_at > ?
            """, (token, now)).fetchone()
            
            if not row:
                conn.close()
                return None
                
            email = row[0]
            
            # Mark token as used
            c.execute("""
                UPDATE magic_links SET used = TRUE WHERE token = ?
            """, (token,))
            
            conn.commit()
            conn.close()
            return email
        except Exception as e:
            print(f"Error validating magic link token: {e}")
            return None
    
    def send_magic_link_email(self, email: str, token: str, request_url: str) -> bool:
        """Send magic link email using configured email service."""
        # Import here to avoid circular imports
        try:
            from email_service import email_service
        except ImportError as e:
            print(f"❌ Email service import failed: {e}")
            return False
        
        # Extract base URL from request
        base_url = request_url.replace('/api/auth/magic-link', '')
        magic_link = f"{base_url}/auth/magic-link?token={token}"
        
        # Use the email service
        return email_service.send_magic_link_email(email, magic_link)
    
    def cleanup_expired_magic_links(self):
        """Clean up expired magic link tokens."""
        try:
            conn = self.get_conn()
            c = conn.cursor()
            
            now = datetime.utcnow().isoformat()
            c.execute("DELETE FROM magic_links WHERE expires_at < ?", (now,))
            
            deleted = c.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                print(f"Cleaned up {deleted} expired magic link tokens")
                
        except Exception as e:
            print(f"Error cleaning up magic links: {e}")
    
    # --- Session Extension for Recording ---
    
    def extend_session_for_recording(self, request: Request, duration_minutes: int = 60) -> Optional[str]:
        """Extend user session for active recording - returns new token or None."""
        token = self.get_token_from_request(request)
        if not token:
            return None
        
        payload = self.validate_and_decode_token(token)
        if not payload or "sub" not in payload:
            return None
        
        # Create new token with extended duration
        new_token = self.create_extended_access_token(
            {"sub": payload["sub"]}, 
            minutes=duration_minutes
        )
        return new_token
    
    # --- CSRF Protection ---
    
    def validate_csrf(self, request: Request, csrf_token: Optional[str]) -> bool:
        """Validate CSRF token against cookie."""
        return csrf_token and csrf_token == request.cookies.get("csrf_token")
    
    # --- User Authentication Dependencies ---
    
    def get_current_user_from_discord(self, authorization: str = Header(None)) -> User:
        """Authenticate Discord webhook requests using a shared bearer token.
        
        The Discord bot sends `Authorization: Bearer <WEBHOOK_TOKEN>`. We validate
        the token and return a placeholder user, since the endpoint determines the
        actual `user_id` by mapping the provided `discord_user_id` in the payload.
        """
        expected = os.getenv("WEBHOOK_TOKEN", "your-secret-token")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization header")
        token = authorization.split(" ", 1)[1].strip()
        if token != expected:
            raise HTTPException(status_code=401, detail="Invalid webhook token")
        return User(id=0, username="discord-webhook")
    
    async def get_current_user(self, request: Request, token: Optional[str] = None):
        """Get current authenticated user from request."""
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        # Support Authorization header or cookie-based token for browser navigation
        if not token:
            auth = request.headers.get("Authorization")
            if auth and auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1].strip()
            else:
                token = request.cookies.get("access_token")
        if not token:
            raise credentials_exception
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise credentials_exception
            token_data = TokenData(username=username)
        except JWTError:
            raise credentials_exception
        user = self.get_user(token_data.username)
        if user is None:
            raise credentials_exception
        return user
    
    def get_current_user_silent(self, request: Request) -> Optional[User]:
        """Best-effort user extraction for browser pages. Returns None if invalid."""
        token = None
        auth = request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
        else:
            token = request.cookies.get("access_token")
        if not token:
            return None
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if not username:
                return None
            user = self.get_user(username)
            return user
        except Exception:
            return None


# --- Standalone Functions for Webhook Authentication ---

def verify_webhook_token(credentials):
    """Verify webhook token for Discord integrations."""
    if not credentials or credentials.token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid webhook token")
    return credentials.token


# --- Authentication Router ---

# Initialize router
router = APIRouter(tags=["authentication"])

# Global dependencies that will be set from app.py
get_conn = None
render_page = None
set_flash = None
auth_service = None

def init_auth_router(get_conn_func, render_page_func, set_flash_func, auth_service_instance):
    """Initialize auth router with functions from app.py"""
    global get_conn, render_page, set_flash, auth_service
    get_conn = get_conn_func
    render_page = render_page_func
    set_flash = set_flash_func
    auth_service = auth_service_instance


# --- Authentication Endpoints ---

@router.post("/register", response_model=User)
def register(username: str = Form(...), password: str = Form(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    """Register a new user."""
    conn = get_conn()
    c = conn.cursor()
    hashed = auth_service.get_password_hash(password)
    try:
        c.execute(
            "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
            (username, hashed),
        )
        conn.commit()
        user_id = c.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already registered")
    conn.close()
    
    # Schedule auto-seeding for new user in background
    if user_id:
        background_tasks.add_task(_perform_user_auto_seeding, user_id)
    
    return User(id=user_id, username=username)


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 token endpoint for programmatic access."""
    user = auth_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect username or password",
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_service.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# --- Magic Link Authentication Endpoints ---

@router.post("/api/auth/magic-link")
async def request_magic_link(request: Request, email: str = Form(...), csrf_token: str = Form(...)):
    """Request a magic link to be sent to the provided email"""
    # Validate CSRF token
    if not auth_service.validate_csrf(request, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid form token")
    
    # Basic email validation
    if "@" not in email or len(email) < 5:
        raise HTTPException(status_code=400, detail="Invalid email address")
    
    # Check if user exists with this email
    user = auth_service.get_user_by_email(email)
    if not user:
        # Don't reveal if email exists or not for security
        # Always return success to prevent email enumeration
        return {"message": "If an account exists with that email, a magic link has been sent"}
    
    # Generate and store magic link token
    token = auth_service.create_magic_link_token()
    
    if not auth_service.store_magic_link_token(email, token):
        raise HTTPException(status_code=500, detail="Failed to generate magic link")
    
    # Send email with magic link
    request_url = str(request.url)
    if not auth_service.send_magic_link_email(email, token, request_url):
        raise HTTPException(status_code=500, detail="Failed to send magic link email")
    
    return {"message": "If an account exists with that email, a magic link has been sent"}


@router.get("/auth/magic-link")
async def verify_magic_link(request: Request, token: str = Query(...)):
    """Verify magic link token and log user in"""
    # Clean up expired tokens first
    auth_service.cleanup_expired_magic_links()
    
    # Validate the token
    email = auth_service.validate_magic_link_token(token)
    if not email:
        return render_page(request, "login.html", {
            "error": "Invalid or expired magic link. Please try again."
        })
    
    # Get the user
    user = auth_service.get_user_by_email(email)
    if not user:
        return render_page(request, "login.html", {
            "error": "Account not found. Please contact support."
        })
    
    # Create access token and set cookie (same as normal login)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_service.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    # Set cookie and redirect to dashboard
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,  # Use in production with HTTPS
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    return response


@router.post("/api/auth/magic-link/cleanup")
async def cleanup_magic_links_endpoint(request: Request):
    """Admin endpoint to manually cleanup expired magic links"""
    # Require authentication for this admin endpoint
    current_user = await auth_service.get_current_user(request)
    auth_service.cleanup_expired_magic_links()
    return {"message": "Expired magic links cleaned up"}


@router.get("/api/auth/email/test")
async def test_email_service(request: Request):
    """Test email service configuration"""
    # Require authentication for this admin endpoint
    current_user = await auth_service.get_current_user(request)
    try:
        from email_service import email_service
        
        if email_service.test_connection():
            return {
                "status": "success", 
                "service": email_service.service,
                "enabled": email_service.enabled,
                "message": "Email service is working correctly"
            }
        else:
            return {
                "status": "error",
                "service": email_service.service, 
                "enabled": email_service.enabled,
                "message": "Email service connection failed"
            }
    except Exception as e:
        return {"status": "error", "message": f"Email service error: {str(e)}"}


# --- Browser Login/Logout using cookie for token storage ---

@router.get("/login")
def login_page(request: Request):
    """Display login page."""
    return render_page(request, "login.html", {})


@router.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...), csrf_token: str = Form(...)):
    """Handle login form submission."""
    if not auth_service.validate_csrf(request, csrf_token):
        return render_page(request, "login.html", {"error": "Invalid form. Please refresh."})
    user = auth_service.authenticate_user(username, password)
    if not user:
        resp = render_page(request, "login.html", {"error": "Invalid username or password"})
        resp.status_code = 400
        return resp
    token = auth_service.create_access_token({"sub": user.username}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    resp = RedirectResponse(url="/", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES*60)
    set_flash(resp, "Welcome back!", "success")
    return resp


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    """Handle logout."""
    if not auth_service.validate_csrf(request, csrf_token):
        return RedirectResponse(url="/login", status_code=302)
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie("access_token")
    set_flash(resp, "Logged out.")
    return resp


# --- Web Registration (UI) ---

@router.get("/signup")
def signup_page(request: Request):
    """Display signup page."""
    return render_page(request, "register.html", {})


@router.post("/signup")
def signup_submit(request: Request, username: str = Form(...), password: str = Form(...), csrf_token: str = Form(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    """Handle signup form submission."""
    if not auth_service.validate_csrf(request, csrf_token):
        return render_page(request, "register.html", {"error": "Invalid form. Please refresh."})
    # Reuse registration logic, then log in
    conn = get_conn()
    c = conn.cursor()
    hashed = auth_service.get_password_hash(password)
    try:
        c.execute(
            "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
            (username, hashed),
        )
        conn.commit()
        user_id = c.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        resp = render_page(request, "register.html", {"error": "Username already registered"})
        resp.status_code = 400
        return resp
    conn.close()
    
    # Schedule auto-seeding for new user in background
    if user_id:
        background_tasks.add_task(_perform_user_auto_seeding, user_id)
    
    token = auth_service.create_access_token({"sub": username}, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    resp = RedirectResponse(url="/", status_code=302)
    resp.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=ACCESS_TOKEN_EXPIRE_MINUTES*60)
    set_flash(resp, "Account created!", "success")
    return resp


@router.post("/api/auth/extend-session")
async def extend_session_for_recording(request: Request, duration_minutes: int = 60):
    """Extend user session for active recording sessions"""
    try:
        # Get current user first to validate they're logged in
        current_user = await auth_service.get_current_user(request)
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Create new extended token
        new_token = auth_service.create_extended_access_token(
            {"sub": current_user.username}, 
            minutes=duration_minutes
        )
        
        response = JSONResponse(content={
            "success": True,
            "message": f"Session extended for {duration_minutes} minutes",
            "expires_in_minutes": duration_minutes
        })
        
        # Set the new token as a cookie
        response.set_cookie(
            key="access_token",
            value=new_token,
            httponly=True,
            max_age=duration_minutes * 60,  # Convert to seconds
            samesite="lax"
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extend session: {str(e)}")


@router.post("/api/auth/recording-session")
async def start_recording_session(request: Request):
    """Start a recording session with extended authentication (60 min + 15 min buffer)"""
    try:
        # Get current user to validate they're logged in
        current_user = await auth_service.get_current_user(request)
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Create extended token for recording (75 minutes = 60 min recording + 15 min processing buffer)
        extended_token = auth_service.create_extended_access_token(
            {"sub": current_user.username}, 
            minutes=75
        )
        
        response = JSONResponse(content={
            "success": True,
            "message": "Recording session started - session extended to 75 minutes",
            "session_duration_minutes": 75,
            "recording_time_limit_minutes": 60,
            "processing_buffer_minutes": 15
        })
        
        # Set the extended token as a cookie
        response.set_cookie(
            key="access_token",
            value=extended_token,
            httponly=True,
            max_age=75 * 60,  # 75 minutes in seconds
            samesite="lax"
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start recording session: {str(e)}")


# --- Auto-seeding Helper Functions ---

def _perform_user_auto_seeding(user_id: int, retry_count: int = 0):
    """Background task to perform auto-seeding for new users with retry logic."""
    try:
        import asyncio
        from services.initialization_service import get_initialization_service
        
        init_service = get_initialization_service(get_conn)
        result = init_service.perform_user_onboarding(user_id, retry_count)
        
        if result["success"]:
            auto_seeding_result = result.get("auto_seeding_result", {})
            if auto_seeding_result and auto_seeding_result.get("success"):
                print(f"🌱 Auto-seeding completed for user {user_id}: {auto_seeding_result.get('message', 'Content seeded')}")
            elif auto_seeding_result:
                print(f"ℹ️  Auto-seeding skipped for user {user_id}: {auto_seeding_result.get('reason', 'Unknown reason')}")
            
            # Check if we need to schedule a retry
            if result.get("retry_scheduled", False):
                retry_count = result.get("retry_count", 0)
                print(f"🔄 Scheduling retry for user {user_id} auto-seeding (attempt {retry_count + 2})")
                
                # Schedule retry with delay (exponential backoff: 30s, 60s, 120s)
                delay = min(30 * (2 ** retry_count), 300)  # Max 5 minutes
                
                # Create delayed retry task
                async def delayed_retry():
                    await asyncio.sleep(delay)
                    _perform_user_auto_seeding(user_id, retry_count + 1)
                
                asyncio.create_task(delayed_retry())
        else:
            print(f"❌ User onboarding failed permanently for user {user_id}: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Auto-seeding background task failed for user {user_id}: {e}")
        
        # For unexpected errors, try to schedule one retry if this is the first attempt
        if retry_count == 0:
            try:
                import asyncio
                print(f"🔄 Scheduling single retry for user {user_id} after unexpected error")
                
                async def delayed_retry():
                    await asyncio.sleep(60)  # Wait 1 minute before retry
                    _perform_user_auto_seeding(user_id, 1)
                
                asyncio.create_task(delayed_retry())
            except Exception as retry_error:
                print(f"❌ Failed to schedule retry for user {user_id}: {retry_error}")


print("[Auth Service] Loaded successfully")