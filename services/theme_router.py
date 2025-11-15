"""
Theme Management Router for Second Brain
Handles theme selection, customization, and persistence
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import json
import sqlite3
from pathlib import Path

router = APIRouter(prefix="/api/themes", tags=["themes"])


# ============================================
# Theme Models
# ============================================

class Theme(BaseModel):
    """Theme definition model"""
    id: str = Field(..., description="Unique theme identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Theme description")
    author: str = Field(default="Second Brain", description="Theme author")
    version: str = Field(default="1.0.0", description="Theme version")
    is_dark: bool = Field(default=False, description="Is this a dark theme?")
    is_custom: bool = Field(default=False, description="Is this a custom theme?")
    colors: Optional[Dict[str, str]] = Field(default=None, description="Custom color overrides")
    preview_url: Optional[str] = Field(default=None, description="Preview image URL")


class ThemeColors(BaseModel):
    """Custom theme colors"""
    primary: Optional[str] = None
    secondary: Optional[str] = None
    accent: Optional[str] = None
    background_primary: Optional[str] = None
    background_secondary: Optional[str] = None
    text_primary: Optional[str] = None
    text_secondary: Optional[str] = None
    border_light: Optional[str] = None


class UserThemePreference(BaseModel):
    """User theme preference"""
    user_id: int
    theme_id: str
    custom_colors: Optional[Dict[str, str]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SetThemeRequest(BaseModel):
    """Request to set user theme"""
    theme_id: str
    custom_colors: Optional[Dict[str, str]] = None


# ============================================
# Built-in Themes Catalog
# ============================================

BUILTIN_THEMES = {
    "default": Theme(
        id="default",
        name="Light",
        description="Clean and bright default theme",
        is_dark=False,
        colors={
            "primary": "#3b82f6",
            "secondary": "#8b5cf6",
            "accent": "#10b981",
            "bg_primary": "#ffffff",
            "text_primary": "#111827"
        }
    ),
    "dark": Theme(
        id="dark",
        name="Dark",
        description="Easy on the eyes dark theme",
        is_dark=True,
        colors={
            "primary": "#60a5fa",
            "secondary": "#a78bfa",
            "accent": "#34d399",
            "bg_primary": "#111827",
            "text_primary": "#f9fafb"
        }
    ),
    "midnight": Theme(
        id="midnight",
        name="Midnight Blue",
        description="Deep blue theme for night owls",
        is_dark=True,
        colors={
            "primary": "#3b82f6",
            "secondary": "#ec4899",
            "accent": "#14b8a6",
            "bg_primary": "#0f172a",
            "text_primary": "#f1f5f9"
        }
    ),
    "forest": Theme(
        id="forest",
        name="Forest",
        description="Nature-inspired green theme",
        is_dark=True,
        colors={
            "primary": "#10b981",
            "secondary": "#8b5cf6",
            "accent": "#f59e0b",
            "bg_primary": "#064e3b",
            "text_primary": "#ecfdf5"
        }
    ),
    "sunset": Theme(
        id="sunset",
        name="Sunset",
        description="Warm orange and pink theme",
        is_dark=True,
        colors={
            "primary": "#f59e0b",
            "secondary": "#ec4899",
            "accent": "#8b5cf6",
            "bg_primary": "#7c2d12",
            "text_primary": "#fef3c7"
        }
    ),
    "ocean": Theme(
        id="ocean",
        name="Ocean",
        description="Cool cyan and blue theme",
        is_dark=True,
        colors={
            "primary": "#06b6d4",
            "secondary": "#3b82f6",
            "accent": "#8b5cf6",
            "bg_primary": "#164e63",
            "text_primary": "#ecfeff"
        }
    ),
    "high-contrast": Theme(
        id="high-contrast",
        name="High Contrast",
        description="Maximum contrast for accessibility",
        is_dark=True,
        colors={
            "primary": "#000000",
            "secondary": "#ffffff",
            "accent": "#ffff00",
            "bg_primary": "#000000",
            "text_primary": "#ffffff"
        }
    ),
}


# ============================================
# Database Helper Functions
# ============================================

def get_db_connection():
    """Get database connection"""
    db_path = Path(__file__).parent.parent / "second_brain.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_theme_table():
    """Initialize theme preferences table"""
    conn = get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_theme_preferences (
                user_id INTEGER PRIMARY KEY,
                theme_id TEXT NOT NULL DEFAULT 'default',
                custom_colors TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
    finally:
        conn.close()


# Initialize table on module import
try:
    init_theme_table()
except Exception as e:
    print(f"Warning: Could not initialize theme table: {e}")


# ============================================
# API Endpoints
# ============================================

@router.get("/", response_model=List[Theme])
async def get_available_themes():
    """
    Get all available themes (built-in and custom)
    """
    return list(BUILTIN_THEMES.values())


@router.get("/{theme_id}", response_model=Theme)
async def get_theme_by_id(theme_id: str):
    """
    Get a specific theme by ID
    """
    if theme_id not in BUILTIN_THEMES:
        raise HTTPException(status_code=404, detail="Theme not found")

    return BUILTIN_THEMES[theme_id]


@router.get("/user/current")
async def get_user_theme(user_id: int = 1):
    """
    Get current user's theme preference

    Note: user_id defaults to 1 for now. Should be from auth session.
    """
    conn = get_db_connection()
    try:
        result = conn.execute(
            "SELECT theme_id, custom_colors FROM user_theme_preferences WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if result:
            custom_colors = json.loads(result["custom_colors"]) if result["custom_colors"] else None
            return {
                "theme_id": result["theme_id"],
                "custom_colors": custom_colors,
                "theme": BUILTIN_THEMES.get(result["theme_id"])
            }
        else:
            # Return default theme
            return {
                "theme_id": "default",
                "custom_colors": None,
                "theme": BUILTIN_THEMES["default"]
            }
    finally:
        conn.close()


@router.post("/user/set")
async def set_user_theme(request: SetThemeRequest, user_id: int = 1):
    """
    Set user's theme preference

    Note: user_id defaults to 1 for now. Should be from auth session.
    """
    # Validate theme exists
    if request.theme_id not in BUILTIN_THEMES:
        raise HTTPException(status_code=400, detail="Invalid theme_id")

    conn = get_db_connection()
    try:
        # Check if preference exists
        existing = conn.execute(
            "SELECT user_id FROM user_theme_preferences WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        custom_colors_json = json.dumps(request.custom_colors) if request.custom_colors else None

        if existing:
            # Update existing preference
            conn.execute(
                """UPDATE user_theme_preferences
                   SET theme_id = ?, custom_colors = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE user_id = ?""",
                (request.theme_id, custom_colors_json, user_id)
            )
        else:
            # Insert new preference
            conn.execute(
                """INSERT INTO user_theme_preferences (user_id, theme_id, custom_colors)
                   VALUES (?, ?, ?)""",
                (user_id, request.theme_id, custom_colors_json)
            )

        conn.commit()

        return {
            "success": True,
            "message": f"Theme set to '{request.theme_id}'",
            "theme_id": request.theme_id,
            "custom_colors": request.custom_colors
        }
    finally:
        conn.close()


@router.post("/user/customize")
async def customize_theme_colors(colors: ThemeColors, user_id: int = 1):
    """
    Customize current theme colors

    Note: user_id defaults to 1 for now. Should be from auth session.
    """
    conn = get_db_connection()
    try:
        # Get current theme
        result = conn.execute(
            "SELECT theme_id, custom_colors FROM user_theme_preferences WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        current_theme_id = result["theme_id"] if result else "default"
        current_colors = json.loads(result["custom_colors"]) if result and result["custom_colors"] else {}

        # Merge with new colors
        updated_colors = {**current_colors, **colors.dict(exclude_none=True)}
        custom_colors_json = json.dumps(updated_colors)

        if result:
            conn.execute(
                """UPDATE user_theme_preferences
                   SET custom_colors = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE user_id = ?""",
                (custom_colors_json, user_id)
            )
        else:
            conn.execute(
                """INSERT INTO user_theme_preferences (user_id, theme_id, custom_colors)
                   VALUES (?, ?, ?)""",
                (user_id, current_theme_id, custom_colors_json)
            )

        conn.commit()

        return {
            "success": True,
            "message": "Theme colors customized",
            "colors": updated_colors
        }
    finally:
        conn.close()


@router.delete("/user/reset")
async def reset_user_theme(user_id: int = 1):
    """
    Reset user theme to default

    Note: user_id defaults to 1 for now. Should be from auth session.
    """
    conn = get_db_connection()
    try:
        conn.execute(
            "DELETE FROM user_theme_preferences WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()

        return {
            "success": True,
            "message": "Theme reset to default",
            "theme_id": "default"
        }
    finally:
        conn.close()


@router.get("/export/{theme_id}")
async def export_theme(theme_id: str, user_id: int = 1):
    """
    Export theme configuration as JSON
    """
    if theme_id not in BUILTIN_THEMES:
        raise HTTPException(status_code=404, detail="Theme not found")

    theme = BUILTIN_THEMES[theme_id]

    # Get any user customizations
    conn = get_db_connection()
    try:
        result = conn.execute(
            "SELECT custom_colors FROM user_theme_preferences WHERE user_id = ? AND theme_id = ?",
            (user_id, theme_id)
        ).fetchone()

        custom_colors = json.loads(result["custom_colors"]) if result and result["custom_colors"] else None

        export_data = {
            **theme.dict(),
            "custom_colors": custom_colors
        }

        return export_data
    finally:
        conn.close()


@router.get("/css/variables")
async def get_css_variables(theme_id: str = "default"):
    """
    Get CSS custom properties for a theme
    Useful for dynamically generating CSS
    """
    if theme_id not in BUILTIN_THEMES:
        raise HTTPException(status_code=404, detail="Theme not found")

    theme = BUILTIN_THEMES[theme_id]
    colors = theme.colors or {}

    # Generate CSS custom properties
    css_vars = {
        f"--sb-{key.replace('_', '-')}": value
        for key, value in colors.items()
    }

    return {
        "theme_id": theme_id,
        "css_variables": css_vars
    }


# ============================================
# Health Check
# ============================================

@router.get("/health")
async def health_check():
    """Theme service health check"""
    return {
        "status": "healthy",
        "service": "theme",
        "available_themes": len(BUILTIN_THEMES),
        "themes": list(BUILTIN_THEMES.keys())
    }
