"""
Interactive Seeding Service for Second Brain

Guides users through interactive content collection to build high-quality
search training data beyond automatic seeding.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from config import settings

log = logging.getLogger(__name__)

@dataclass
class SeedingPrompt:
    """Configuration for a seeding prompt."""
    id: str
    type: str  # 'pdf', 'audio', 'text', 'web'
    title: str
    description: str
    target_count: int
    points: int
    required: bool = False
    examples: List[str] = None

@dataclass
class UserSeedingProgress:
    """User's progress through interactive seeding."""
    user_id: int
    level: int = 1
    total_points: int = 0
    completed_prompts: List[str] = None
    achievements: List[str] = None
    last_activity: datetime = None

# Seeding prompts configuration
SEEDING_PROMPTS = [
    # PDF Documents
    SeedingPrompt(
        id="pdf_personal_docs",
        type="pdf", 
        title="📄 Add 3-5 Personal Documents",
        description="Upload PDFs like resumes, reports, or articles you reference often",
        target_count=5,
        points=100,
        required=True,
        examples=["Resume/CV", "Research papers", "Technical documentation", "Meeting notes", "Project reports"]
    ),
    
    # Audio Content
    SeedingPrompt(
        id="audio_voice_memos",
        type="audio",
        title="🎤 Record 10 Minutes of Voice Memos", 
        description="Create voice recordings about your thoughts, ideas, or daily reflections",
        target_count=10,  # minutes
        points=150,
        required=True,
        examples=["Daily reflections", "Project ideas", "Meeting summaries", "Learning notes", "Creative thoughts"]
    ),
    
    # Text Questions
    SeedingPrompt(
        id="text_personal_info",
        type="text",
        title="✍️ Answer 8 Personal Questions",
        description="Help us understand your interests and knowledge areas",
        target_count=8,
        points=80,
        required=True,
        examples=[]
    ),
    
    # Web Content
    SeedingPrompt(
        id="web_bookmarks",
        type="web",
        title="🔖 Capture 10 Important Web Resources",
        description="Add web pages, articles, or tools you reference frequently",
        target_count=10,
        points=120,
        required=False,
        examples=["Technical documentation", "News articles", "Tools and resources", "Blog posts", "Reference materials"]
    ),
    
    # Advanced Content
    SeedingPrompt(
        id="email_samples",
        type="text",
        title="📧 Add 5 Email Templates or Important Messages",
        description="Share templates or important emails (remove sensitive info)",
        target_count=5,
        points=60,
        required=False,
        examples=["Email templates", "Important messages", "Communication examples", "Business correspondence"]
    ),
    
    SeedingPrompt(
        id="code_snippets",
        type="text", 
        title="💻 Share 5 Code Snippets or Technical Notes",
        description="Add useful code examples or technical documentation",
        target_count=5,
        points=80,
        required=False,
        examples=["Code snippets", "Technical solutions", "Configuration examples", "Scripts", "Documentation"]
    )
]

# Personal questions for text seeding
PERSONAL_QUESTIONS = [
    {
        "id": "q1_expertise",
        "question": "What are your main areas of expertise or professional knowledge?",
        "placeholder": "e.g., software development, marketing, healthcare, education...",
        "category": "expertise"
    },
    {
        "id": "q2_hobbies",
        "question": "What are your primary hobbies and personal interests?", 
        "placeholder": "e.g., photography, cooking, hiking, reading...",
        "category": "personal"
    },
    {
        "id": "q3_learning",
        "question": "What topics are you currently learning about or want to explore?",
        "placeholder": "e.g., machine learning, Spanish language, investing...",
        "category": "learning"
    },
    {
        "id": "q4_goals",
        "question": "What are your main personal or professional goals for the next year?",
        "placeholder": "e.g., launch a project, improve skills, travel...",
        "category": "goals"
    },
    {
        "id": "q5_challenges",
        "question": "What challenges or problems do you frequently encounter in your work or life?",
        "placeholder": "e.g., time management, technical issues, communication...",
        "category": "challenges"
    },
    {
        "id": "q6_tools",
        "question": "What tools, software, or resources do you use daily?",
        "placeholder": "e.g., specific software, apps, websites, books...",
        "category": "tools"
    },
    {
        "id": "q7_projects",
        "question": "Describe a recent project or accomplishment you're proud of.",
        "placeholder": "Share details about something you've worked on recently...",
        "category": "projects"
    },
    {
        "id": "q8_vision",
        "question": "How do you envision using your Second Brain to enhance your productivity?",
        "placeholder": "e.g., research organization, project tracking, idea development...",
        "category": "vision"
    }
]

# Achievement definitions
ACHIEVEMENTS = {
    "first_steps": {"name": "First Steps", "description": "Completed your first seeding prompt", "points": 10},
    "content_contributor": {"name": "Content Contributor", "description": "Added 10+ items to your vault", "points": 50},
    "knowledge_curator": {"name": "Knowledge Curator", "description": "Completed all required prompts", "points": 200},
    "search_optimizer": {"name": "Search Optimizer", "description": "Your content improved search quality by 25%", "points": 300},
    "power_user": {"name": "Power User", "description": "Reached 1000+ points", "points": 100},
    "completionist": {"name": "Completionist", "description": "Finished all seeding prompts", "points": 500}
}

class InteractiveSeedingService:
    """Service for interactive user-guided content seeding."""
    
    def __init__(self, get_conn_func):
        """Initialize with database connection function."""
        self.get_conn = get_conn_func
        self._ensure_schema()
    
    def _ensure_schema(self) -> None:
        """Ensure interactive seeding tables exist."""
        conn = self.get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interactive_seeding_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    level INTEGER DEFAULT 1,
                    total_points INTEGER DEFAULT 0,
                    completed_prompts TEXT DEFAULT '[]',
                    achievements TEXT DEFAULT '[]',
                    last_activity TEXT DEFAULT (datetime('now')),
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interactive_seeding_submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    prompt_id TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    content_data TEXT,
                    file_path TEXT,
                    points_awarded INTEGER DEFAULT 0,
                    quality_score REAL,
                    submitted_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            conn.commit()
            
        except Exception as e:
            log.error("Failed to ensure interactive seeding schema: %s", e)
        finally:
            conn.close()
    
    def get_user_progress(self, user_id: int) -> UserSeedingProgress:
        """Get user's current seeding progress."""
        conn = self.get_conn()
        try:
            cursor = conn.execute("""
                SELECT level, total_points, completed_prompts, achievements, last_activity
                FROM interactive_seeding_progress
                WHERE user_id = ?
            """, (user_id,))
            
            result = cursor.fetchone()
            if result:
                import json
                return UserSeedingProgress(
                    user_id=user_id,
                    level=result[0],
                    total_points=result[1],
                    completed_prompts=json.loads(result[2] or '[]'),
                    achievements=json.loads(result[3] or '[]'),
                    last_activity=datetime.fromisoformat(result[4]) if result[4] else datetime.now()
                )
            else:
                # Create new progress record
                conn.execute("""
                    INSERT OR IGNORE INTO interactive_seeding_progress (user_id)
                    VALUES (?)
                """, (user_id,))
                conn.commit()
                
                return UserSeedingProgress(
                    user_id=user_id,
                    completed_prompts=[],
                    achievements=[],
                    last_activity=datetime.now()
                )
                
        except Exception as e:
            log.error("Error getting user progress: %s", e)
            return UserSeedingProgress(
                user_id=user_id,
                completed_prompts=[],
                achievements=[],
                last_activity=datetime.now()
            )
        finally:
            conn.close()
    
    def get_available_prompts(self, user_id: int) -> List[Dict[str, Any]]:
        """Get available seeding prompts for user."""
        progress = self.get_user_progress(user_id)
        completed = set(progress.completed_prompts or [])
        
        prompts = []
        for prompt in SEEDING_PROMPTS:
            # Get submission count for this prompt
            conn = self.get_conn()
            cursor = conn.execute("""
                SELECT COUNT(*) FROM interactive_seeding_submissions
                WHERE user_id = ? AND prompt_id = ?
            """, (user_id, prompt.id))
            
            current_count = cursor.fetchone()[0]
            conn.close()
            
            prompts.append({
                "id": prompt.id,
                "type": prompt.type,
                "title": prompt.title,
                "description": prompt.description,
                "target_count": prompt.target_count,
                "current_count": current_count,
                "points": prompt.points,
                "required": prompt.required,
                "completed": prompt.id in completed,
                "progress_percentage": min(100, (current_count / prompt.target_count) * 100),
                "examples": prompt.examples or []
            })
        
        return prompts
    
    def get_personal_questions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get personal questions for text seeding."""
        # Check which questions already answered
        conn = self.get_conn()
        cursor = conn.execute("""
            SELECT content_data FROM interactive_seeding_submissions
            WHERE user_id = ? AND prompt_id = 'text_personal_info'
        """, (user_id,))
        
        answered_questions = set()
        for row in cursor.fetchall():
            import json
            try:
                data = json.loads(row[0])
                answered_questions.add(data.get('question_id'))
            except:
                pass
        
        conn.close()
        
        return [
            {
                **q,
                "answered": q["id"] in answered_questions
            }
            for q in PERSONAL_QUESTIONS
        ]
    
    def submit_content(self, user_id: int, prompt_id: str, content_data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit content for a seeding prompt."""
        try:
            # Find the prompt
            prompt = next((p for p in SEEDING_PROMPTS if p.id == prompt_id), None)
            if not prompt:
                return {"success": False, "error": "Invalid prompt ID"}
            
            # Calculate points and quality score
            points_awarded = min(prompt.points, content_data.get('quality_bonus', 0) + prompt.points // prompt.target_count)
            quality_score = self._calculate_quality_score(prompt.type, content_data)
            
            # Store submission
            conn = self.get_conn()
            cursor = conn.execute("""
                INSERT INTO interactive_seeding_submissions 
                (user_id, prompt_id, content_type, content_data, points_awarded, quality_score)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id, 
                prompt_id, 
                prompt.type, 
                json.dumps(content_data),
                points_awarded,
                quality_score
            ))
            
            submission_id = cursor.lastrowid
            
            # Update user progress
            self._update_user_progress(user_id, prompt_id, points_awarded, conn)
            
            conn.commit()
            conn.close()
            
            # Check for new achievements
            new_achievements = self._check_achievements(user_id)
            
            return {
                "success": True,
                "submission_id": submission_id,
                "points_awarded": points_awarded,
                "quality_score": quality_score,
                "new_achievements": new_achievements,
                "message": f"Great work! You earned {points_awarded} points."
            }
            
        except Exception as e:
            log.error("Error submitting content: %s", e)
            return {"success": False, "error": str(e)}
    
    def _calculate_quality_score(self, content_type: str, content_data: Dict[str, Any]) -> float:
        """Calculate quality score for submitted content."""
        base_score = 0.7
        
        if content_type == 'text':
            # Score based on text length and completeness
            text = content_data.get('text', '')
            word_count = len(text.split())
            if word_count > 50:
                base_score += 0.2
            if word_count > 100:
                base_score += 0.1
                
        elif content_type == 'pdf':
            # Score based on file size and type
            file_size = content_data.get('file_size', 0)
            if file_size > 10000:  # > 10KB
                base_score += 0.2
            if content_data.get('file_type') == 'application/pdf':
                base_score += 0.1
                
        elif content_type == 'audio':
            # Score based on duration
            duration = content_data.get('duration_minutes', 0)
            if duration >= 1:
                base_score += 0.2
            if duration >= 5:
                base_score += 0.1
                
        elif content_type == 'web':
            # Score based on URL validity and content
            url = content_data.get('url', '')
            if url.startswith(('http://', 'https://')):
                base_score += 0.2
            if len(content_data.get('description', '')) > 20:
                base_score += 0.1
        
        return min(1.0, base_score)
    
    def _update_user_progress(self, user_id: int, prompt_id: str, points: int, conn: sqlite3.Connection) -> None:
        """Update user's seeding progress."""
        import json
        
        # Get current progress
        cursor = conn.execute("""
            SELECT completed_prompts, total_points FROM interactive_seeding_progress
            WHERE user_id = ?
        """, (user_id,))
        
        result = cursor.fetchone()
        if result:
            completed_prompts = json.loads(result[0] or '[]')
            total_points = result[1] or 0
        else:
            completed_prompts = []
            total_points = 0
        
        # Add prompt if not already completed
        if prompt_id not in completed_prompts:
            # Check if prompt is actually complete
            prompt = next((p for p in SEEDING_PROMPTS if p.id == prompt_id), None)
            if prompt:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM interactive_seeding_submissions
                    WHERE user_id = ? AND prompt_id = ?
                """, (user_id, prompt_id))
                
                submission_count = cursor.fetchone()[0]
                if submission_count >= prompt.target_count:
                    completed_prompts.append(prompt_id)
        
        # Update points and level
        total_points += points
        level = max(1, total_points // 100)  # Level up every 100 points
        
        # Update database
        conn.execute("""
            UPDATE interactive_seeding_progress 
            SET completed_prompts = ?, total_points = ?, level = ?, last_activity = datetime('now')
            WHERE user_id = ?
        """, (json.dumps(completed_prompts), total_points, level, user_id))
    
    def _check_achievements(self, user_id: int) -> List[Dict[str, Any]]:
        """Check for new achievements."""
        progress = self.get_user_progress(user_id)
        current_achievements = set(progress.achievements or [])
        new_achievements = []
        
        # Check each achievement
        if len(progress.completed_prompts or []) >= 1 and "first_steps" not in current_achievements:
            new_achievements.append("first_steps")
        
        # Get total submissions
        conn = self.get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM interactive_seeding_submissions WHERE user_id = ?", (user_id,))
        total_submissions = cursor.fetchone()[0]
        
        if total_submissions >= 10 and "content_contributor" not in current_achievements:
            new_achievements.append("content_contributor")
        
        # Check required prompts completion
        required_prompts = [p.id for p in SEEDING_PROMPTS if p.required]
        if all(p in (progress.completed_prompts or []) for p in required_prompts) and "knowledge_curator" not in current_achievements:
            new_achievements.append("knowledge_curator")
        
        if progress.total_points >= 1000 and "power_user" not in current_achievements:
            new_achievements.append("power_user")
        
        if len(progress.completed_prompts or []) == len(SEEDING_PROMPTS) and "completionist" not in current_achievements:
            new_achievements.append("completionist")
        
        conn.close()
        
        # Update achievements in database
        if new_achievements:
            all_achievements = list(current_achievements) + new_achievements
            conn = self.get_conn()
            conn.execute("""
                UPDATE interactive_seeding_progress 
                SET achievements = ?
                WHERE user_id = ?
            """, (json.dumps(all_achievements), user_id))
            conn.commit()
            conn.close()
        
        # Return achievement details
        return [
            {
                "id": ach_id,
                "name": ACHIEVEMENTS[ach_id]["name"],
                "description": ACHIEVEMENTS[ach_id]["description"],
                "points": ACHIEVEMENTS[ach_id]["points"]
            }
            for ach_id in new_achievements
        ]
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top users by seeding progress (anonymized)."""
        conn = self.get_conn()
        try:
            cursor = conn.execute("""
                SELECT p.level, p.total_points, p.achievements, u.username
                FROM interactive_seeding_progress p
                JOIN users u ON p.user_id = u.id
                ORDER BY p.total_points DESC, p.level DESC
                LIMIT ?
            """, (limit,))
            
            leaderboard = []
            for i, (level, points, achievements_json, username) in enumerate(cursor.fetchall()):
                import json
                achievements = json.loads(achievements_json or '[]')
                
                leaderboard.append({
                    "rank": i + 1,
                    "username": username[:3] + "***",  # Anonymize
                    "level": level,
                    "points": points,
                    "achievement_count": len(achievements)
                })
            
            return leaderboard
            
        except Exception as e:
            log.error("Error getting leaderboard: %s", e)
            return []
        finally:
            conn.close()

# Global instance
_interactive_seeding_service = None

def get_interactive_seeding_service(get_conn_func):
    """Get global interactive seeding service instance."""
    global _interactive_seeding_service
    if _interactive_seeding_service is None:
        _interactive_seeding_service = InteractiveSeedingService(get_conn_func)
    return _interactive_seeding_service

# Export the service class and functions
__all__ = ["InteractiveSeedingService", "SeedingPrompt", "UserSeedingProgress", "get_interactive_seeding_service"]