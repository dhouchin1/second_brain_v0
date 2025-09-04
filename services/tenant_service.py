"""
Tenant Service

Handles multi-tenant operations, tenant management, and data isolation
for Second Brain. Provides the foundation for SaaS deployment with
proper tenant isolation and resource management.
"""

from __future__ import annotations
import json
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum

from fastapi import HTTPException, Depends
from pydantic import BaseModel
import re

from config import settings


class TenantPlan(str, Enum):
    """Available tenant plans"""
    FREE = "free"
    STARTER = "starter" 
    PRO = "pro"
    ENTERPRISE = "enterprise"
    UNLIMITED = "unlimited"


class TenantStatus(str, Enum):
    """Tenant status"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELED = "canceled"
    PENDING = "pending"


class MembershipRole(str, Enum):
    """Tenant membership roles"""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


@dataclass
class Tenant:
    """Tenant data model"""
    id: str
    name: str
    slug: str
    plan: TenantPlan
    status: TenantStatus
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Limits
    max_users: int = 5
    max_notes: int = 1000
    max_storage_mb: int = 500
    
    # Features
    features: Optional[Dict[str, bool]] = None
    settings: Optional[Dict[str, Any]] = None


@dataclass
class TenantMembership:
    """Tenant membership model"""
    id: int
    tenant_id: str
    user_id: int
    role: MembershipRole
    status: str = "active"
    joined_at: Optional[datetime] = None


@dataclass 
class TenantUsage:
    """Tenant usage tracking"""
    tenant_id: str
    metric: str
    value: int
    recorded_at: datetime


class TenantLimits:
    """Tenant plan limits and features"""
    
    PLAN_LIMITS = {
        TenantPlan.FREE: {
            "max_users": 1,
            "max_notes": 100,
            "max_storage_mb": 50,
            "features": {
                "automation": False,
                "api_access": False,
                "custom_workflows": False,
                "discord_bot": False,
                "obsidian_sync": True
            }
        },
        TenantPlan.STARTER: {
            "max_users": 5,
            "max_notes": 1000,
            "max_storage_mb": 500,
            "features": {
                "automation": True,
                "api_access": True,
                "custom_workflows": False,
                "discord_bot": True,
                "obsidian_sync": True
            }
        },
        TenantPlan.PRO: {
            "max_users": 25,
            "max_notes": 10000,
            "max_storage_mb": 5000,
            "features": {
                "automation": True,
                "api_access": True,
                "custom_workflows": True,
                "discord_bot": True,
                "obsidian_sync": True,
                "advanced_search": True
            }
        },
        TenantPlan.ENTERPRISE: {
            "max_users": 1000,
            "max_notes": 100000,
            "max_storage_mb": 50000,
            "features": {
                "automation": True,
                "api_access": True,
                "custom_workflows": True,
                "discord_bot": True,
                "obsidian_sync": True,
                "advanced_search": True,
                "sso": True,
                "audit_logs": True
            }
        },
        TenantPlan.UNLIMITED: {
            "max_users": 999999,
            "max_notes": 999999,
            "max_storage_mb": 999999,
            "features": {
                "automation": True,
                "api_access": True,
                "custom_workflows": True,
                "discord_bot": True,
                "obsidian_sync": True,
                "advanced_search": True,
                "sso": True,
                "audit_logs": True
            }
        }
    }
    
    @classmethod
    def get_limits(cls, plan: TenantPlan) -> Dict[str, Any]:
        """Get limits for a tenant plan"""
        return cls.PLAN_LIMITS.get(plan, cls.PLAN_LIMITS[TenantPlan.FREE])


class TenantService:
    """Multi-tenant management service"""
    
    def __init__(self, get_conn_func: Callable[[], sqlite3.Connection]):
        self.get_conn = get_conn_func
        self._ensure_migrations()
    
    def _ensure_migrations(self):
        """Ensure tenant migrations are applied"""
        try:
            conn = self.get_conn()
            # Check if tenants table exists
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tenants'")
            if not c.fetchone():
                # Run tenant migration
                self._run_tenant_migration()
            conn.close()
        except Exception as e:
            print(f"[tenant] Migration check error: {e}")
    
    def _run_tenant_migration(self):
        """Run the tenant migration"""
        try:
            from pathlib import Path
            migration_path = Path(__file__).parent.parent / "migrations" / "002_add_tenants.sql"
            if migration_path.exists():
                conn = self.get_conn()
                c = conn.cursor()
                sql = migration_path.read_text()
                c.executescript(sql)
                conn.commit()
                conn.close()
                print("[tenant] Multi-tenant migration applied successfully")
            else:
                print("[tenant] Migration file not found")
        except Exception as e:
            print(f"[tenant] Migration error: {e}")
    
    # ─── Tenant Management ───
    
    def create_tenant(self, name: str, plan: TenantPlan = TenantPlan.FREE, 
                     owner_user_id: Optional[int] = None) -> Tenant:
        """Create a new tenant"""
        # Generate slug from name
        slug = self._generate_slug(name)
        tenant_id = f"tenant_{secrets.token_hex(8)}"
        
        # Get plan limits
        limits = TenantLimits.get_limits(plan)
        
        tenant = Tenant(
            id=tenant_id,
            name=name,
            slug=slug,
            plan=plan,
            status=TenantStatus.ACTIVE,
            metadata={},
            created_at=datetime.now(),
            max_users=limits["max_users"],
            max_notes=limits["max_notes"],
            max_storage_mb=limits["max_storage_mb"],
            features=limits["features"],
            settings={}
        )
        
        # Save to database
        conn = self.get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                INSERT INTO tenants (
                    id, name, slug, plan, status, metadata, created_at,
                    max_users, max_notes, max_storage_mb, features, settings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tenant.id, tenant.name, tenant.slug, tenant.plan.value, 
                tenant.status.value, json.dumps(tenant.metadata),
                tenant.created_at.isoformat(), tenant.max_users, tenant.max_notes,
                tenant.max_storage_mb, json.dumps(tenant.features),
                json.dumps(tenant.settings)
            ))
            
            # Add owner membership if specified
            if owner_user_id:
                self.add_tenant_member(tenant_id, owner_user_id, MembershipRole.OWNER)
                
                # Update user's tenant_id
                c.execute("UPDATE users SET tenant_id = ? WHERE id = ?", (tenant_id, owner_user_id))
            
            conn.commit()
        finally:
            conn.close()
        
        return tenant
    
    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            row = c.execute("""
                SELECT id, name, slug, plan, status, metadata, created_at, updated_at,
                       max_users, max_notes, max_storage_mb, features, settings
                FROM tenants WHERE id = ?
            """, (tenant_id,)).fetchone()
            
            if not row:
                return None
            
            return Tenant(
                id=row[0],
                name=row[1],
                slug=row[2],
                plan=TenantPlan(row[3]),
                status=TenantStatus(row[4]),
                metadata=json.loads(row[5]) if row[5] else {},
                created_at=datetime.fromisoformat(row[6]) if row[6] else None,
                updated_at=datetime.fromisoformat(row[7]) if row[7] else None,
                max_users=row[8],
                max_notes=row[9],
                max_storage_mb=row[10],
                features=json.loads(row[11]) if row[11] else {},
                settings=json.loads(row[12]) if row[12] else {}
            )
        finally:
            conn.close()
    
    def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        """Get tenant by slug"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            row = c.execute("""
                SELECT id, name, slug, plan, status, metadata, created_at, updated_at,
                       max_users, max_notes, max_storage_mb, features, settings
                FROM tenants WHERE slug = ?
            """, (slug,)).fetchone()
            
            if not row:
                return None
            
            return Tenant(
                id=row[0],
                name=row[1],
                slug=row[2],
                plan=TenantPlan(row[3]),
                status=TenantStatus(row[4]),
                metadata=json.loads(row[5]) if row[5] else {},
                created_at=datetime.fromisoformat(row[6]) if row[6] else None,
                updated_at=datetime.fromisoformat(row[7]) if row[7] else None,
                max_users=row[8],
                max_notes=row[9],
                max_storage_mb=row[10],
                features=json.loads(row[11]) if row[11] else {},
                settings=json.loads(row[12]) if row[12] else {}
            )
        finally:
            conn.close()
    
    def list_tenants(self, status: Optional[TenantStatus] = None) -> List[Tenant]:
        """List tenants with optional status filter"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            query = """
                SELECT id, name, slug, plan, status, metadata, created_at, updated_at,
                       max_users, max_notes, max_storage_mb, features, settings
                FROM tenants
            """
            params = []
            
            if status:
                query += " WHERE status = ?"
                params.append(status.value)
            
            query += " ORDER BY created_at DESC"
            
            rows = c.execute(query, params).fetchall()
            
            return [
                Tenant(
                    id=row[0],
                    name=row[1],
                    slug=row[2],
                    plan=TenantPlan(row[3]),
                    status=TenantStatus(row[4]),
                    metadata=json.loads(row[5]) if row[5] else {},
                    created_at=datetime.fromisoformat(row[6]) if row[6] else None,
                    updated_at=datetime.fromisoformat(row[7]) if row[7] else None,
                    max_users=row[8],
                    max_notes=row[9],
                    max_storage_mb=row[10],
                    features=json.loads(row[11]) if row[11] else {},
                    settings=json.loads(row[12]) if row[12] else {}
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def update_tenant(self, tenant_id: str, **updates) -> bool:
        """Update tenant properties"""
        if not updates:
            return False
            
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            # Build dynamic update query
            set_clauses = []
            params = []
            
            for key, value in updates.items():
                if key in ['name', 'slug', 'plan', 'status', 'max_users', 'max_notes', 'max_storage_mb']:
                    set_clauses.append(f"{key} = ?")
                    params.append(value.value if hasattr(value, 'value') else value)
                elif key in ['metadata', 'features', 'settings']:
                    set_clauses.append(f"{key} = ?")
                    params.append(json.dumps(value))
            
            if not set_clauses:
                return False
            
            set_clauses.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(tenant_id)
            
            query = f"UPDATE tenants SET {', '.join(set_clauses)} WHERE id = ?"
            c.execute(query, params)
            conn.commit()
            
            return c.rowcount > 0
        finally:
            conn.close()
    
    def delete_tenant(self, tenant_id: str) -> bool:
        """Delete a tenant and all associated data"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            # Delete in order due to foreign key constraints
            c.execute("DELETE FROM tenant_memberships WHERE tenant_id = ?", (tenant_id,))
            c.execute("DELETE FROM tenant_usage WHERE tenant_id = ?", (tenant_id,))
            c.execute("DELETE FROM tenant_settings WHERE tenant_id = ?", (tenant_id,))
            c.execute("DELETE FROM tenant_workflows WHERE tenant_id = ?", (tenant_id,))
            c.execute("DELETE FROM tenant_routing_rules WHERE tenant_id = ?", (tenant_id,))
            c.execute("DELETE FROM notes WHERE tenant_id = ?", (tenant_id,))
            c.execute("UPDATE users SET tenant_id = NULL WHERE tenant_id = ?", (tenant_id,))
            c.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
            
            conn.commit()
            return c.rowcount > 0
        finally:
            conn.close()
    
    # ─── Tenant Membership Management ───
    
    def add_tenant_member(self, tenant_id: str, user_id: int, role: MembershipRole = MembershipRole.MEMBER) -> bool:
        """Add user to tenant"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO tenant_memberships (tenant_id, user_id, role, joined_at)
                VALUES (?, ?, ?, ?)
            """, (tenant_id, user_id, role.value, datetime.now().isoformat()))
            conn.commit()
            return True
        except Exception as e:
            print(f"[tenant] Add member error: {e}")
            return False
        finally:
            conn.close()
    
    def remove_tenant_member(self, tenant_id: str, user_id: int) -> bool:
        """Remove user from tenant"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM tenant_memberships WHERE tenant_id = ? AND user_id = ?", 
                     (tenant_id, user_id))
            conn.commit()
            return c.rowcount > 0
        finally:
            conn.close()
    
    def get_tenant_members(self, tenant_id: str) -> List[TenantMembership]:
        """Get all members of a tenant"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            rows = c.execute("""
                SELECT id, tenant_id, user_id, role, status, joined_at
                FROM tenant_memberships WHERE tenant_id = ?
                ORDER BY joined_at
            """, (tenant_id,)).fetchall()
            
            return [
                TenantMembership(
                    id=row[0],
                    tenant_id=row[1],
                    user_id=row[2],
                    role=MembershipRole(row[3]),
                    status=row[4],
                    joined_at=datetime.fromisoformat(row[5]) if row[5] else None
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def get_user_tenant_membership(self, user_id: int, tenant_id: str) -> Optional[TenantMembership]:
        """Get user's membership in a specific tenant"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            row = c.execute("""
                SELECT id, tenant_id, user_id, role, status, joined_at
                FROM tenant_memberships WHERE user_id = ? AND tenant_id = ?
            """, (user_id, tenant_id)).fetchone()
            
            if not row:
                return None
            
            return TenantMembership(
                id=row[0],
                tenant_id=row[1],
                user_id=row[2],
                role=MembershipRole(row[3]),
                status=row[4],
                joined_at=datetime.fromisoformat(row[5]) if row[5] else None
            )
        finally:
            conn.close()
    
    # ─── Usage Tracking ───
    
    def record_usage(self, tenant_id: str, metric: str, value: int):
        """Record usage metric for tenant"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            c.execute("""
                INSERT INTO tenant_usage (tenant_id, metric, value, recorded_at)
                VALUES (?, ?, ?, ?)
            """, (tenant_id, metric, value, datetime.now().isoformat()))
            conn.commit()
        finally:
            conn.close()
    
    def get_tenant_usage(self, tenant_id: str, metric: Optional[str] = None, 
                        days: int = 30) -> List[TenantUsage]:
        """Get usage data for tenant"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            query = """
                SELECT tenant_id, metric, value, recorded_at
                FROM tenant_usage 
                WHERE tenant_id = ? AND recorded_at >= ?
            """
            params = [tenant_id, (datetime.now() - timedelta(days=days)).isoformat()]
            
            if metric:
                query += " AND metric = ?"
                params.append(metric)
            
            query += " ORDER BY recorded_at DESC"
            
            rows = c.execute(query, params).fetchall()
            
            return [
                TenantUsage(
                    tenant_id=row[0],
                    metric=row[1],
                    value=row[2],
                    recorded_at=datetime.fromisoformat(row[3])
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def get_current_usage_stats(self, tenant_id: str) -> Dict[str, int]:
        """Get current usage statistics for tenant"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            # Count current usage
            stats = {}
            
            # User count
            user_count = c.execute("""
                SELECT COUNT(*) FROM tenant_memberships 
                WHERE tenant_id = ? AND status = 'active'
            """, (tenant_id,)).fetchone()[0]
            stats['users'] = user_count
            
            # Note count
            note_count = c.execute("""
                SELECT COUNT(*) FROM notes WHERE tenant_id = ?
            """, (tenant_id,)).fetchone()[0]
            stats['notes'] = note_count
            
            # Storage usage
            storage_result = c.execute("""
                SELECT COALESCE(SUM(file_size), 0) FROM notes 
                WHERE tenant_id = ? AND file_size IS NOT NULL
            """, (tenant_id,)).fetchone()[0]
            stats['storage_bytes'] = storage_result or 0
            
            return stats
        finally:
            conn.close()
    
    def check_limits(self, tenant_id: str) -> Dict[str, Any]:
        """Check if tenant is within limits"""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"error": "Tenant not found"}
        
        current_usage = self.get_current_usage_stats(tenant_id)
        
        return {
            "within_limits": {
                "users": current_usage['users'] <= tenant.max_users,
                "notes": current_usage['notes'] <= tenant.max_notes,
                "storage": current_usage['storage_bytes'] <= (tenant.max_storage_mb * 1024 * 1024)
            },
            "current": current_usage,
            "limits": {
                "users": tenant.max_users,
                "notes": tenant.max_notes,
                "storage_bytes": tenant.max_storage_mb * 1024 * 1024
            },
            "usage_percentage": {
                "users": (current_usage['users'] / tenant.max_users) * 100 if tenant.max_users > 0 else 0,
                "notes": (current_usage['notes'] / tenant.max_notes) * 100 if tenant.max_notes > 0 else 0,
                "storage": (current_usage['storage_bytes'] / (tenant.max_storage_mb * 1024 * 1024)) * 100 if tenant.max_storage_mb > 0 else 0
            }
        }
    
    # ─── Utility Methods ───
    
    def _generate_slug(self, name: str) -> str:
        """Generate URL-safe slug from tenant name"""
        # Convert to lowercase and replace spaces/special chars with hyphens
        slug = re.sub(r'[^a-zA-Z0-9\-]', '-', name.lower())
        slug = re.sub(r'-+', '-', slug)  # Multiple hyphens to single
        slug = slug.strip('-')  # Remove leading/trailing hyphens
        
        # Ensure uniqueness
        base_slug = slug
        counter = 1
        conn = self.get_conn()
        
        try:
            c = conn.cursor()
            while True:
                existing = c.execute("SELECT id FROM tenants WHERE slug = ?", (slug,)).fetchone()
                if not existing:
                    break
                slug = f"{base_slug}-{counter}"
                counter += 1
        finally:
            conn.close()
        
        return slug
    
    def get_tenant_stats(self) -> Dict[str, Any]:
        """Get system-wide tenant statistics"""
        conn = self.get_conn()
        try:
            c = conn.cursor()
            
            # Count tenants by status
            status_counts = {}
            for status in TenantStatus:
                count = c.execute("SELECT COUNT(*) FROM tenants WHERE status = ?", (status.value,)).fetchone()[0]
                status_counts[status.value] = count
            
            # Count by plan
            plan_counts = {}
            for plan in TenantPlan:
                count = c.execute("SELECT COUNT(*) FROM tenants WHERE plan = ?", (plan.value,)).fetchone()[0]
                plan_counts[plan.value] = count
            
            # Total users across all tenants
            total_users = c.execute("SELECT COUNT(*) FROM users WHERE tenant_id IS NOT NULL").fetchone()[0]
            
            # Total notes across all tenants
            total_notes = c.execute("SELECT COUNT(*) FROM notes WHERE tenant_id IS NOT NULL").fetchone()[0]
            
            return {
                "total_tenants": sum(status_counts.values()),
                "by_status": status_counts,
                "by_plan": plan_counts,
                "total_users": total_users,
                "total_notes": total_notes,
                "timestamp": datetime.now().isoformat()
            }
        finally:
            conn.close()


# ─── Tenant Context Middleware ───

class TenantContext:
    """Thread-local tenant context"""
    
    def __init__(self):
        self.tenant_id: Optional[str] = None
        self.tenant: Optional[Tenant] = None
        self.membership: Optional[TenantMembership] = None


# Global tenant context
current_tenant = TenantContext()


def get_tenant_context() -> TenantContext:
    """Get current tenant context"""
    return current_tenant


def set_tenant_context(tenant_id: str, tenant: Tenant, membership: Optional[TenantMembership] = None):
    """Set tenant context for current request"""
    current_tenant.tenant_id = tenant_id
    current_tenant.tenant = tenant
    current_tenant.membership = membership


def clear_tenant_context():
    """Clear tenant context"""
    current_tenant.tenant_id = None
    current_tenant.tenant = None  
    current_tenant.membership = None


# ─── API Models ───

class TenantCreate(BaseModel):
    name: str
    plan: TenantPlan = TenantPlan.FREE


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    status: str
    created_at: str
    max_users: int
    max_notes: int
    max_storage_mb: int
    features: Dict[str, bool]


class TenantStatsResponse(BaseModel):
    total_tenants: int
    by_status: Dict[str, int]
    by_plan: Dict[str, int]
    total_users: int
    total_notes: int
    timestamp: str


class TenantUsageResponse(BaseModel):
    within_limits: Dict[str, bool]
    current: Dict[str, int]
    limits: Dict[str, int]
    usage_percentage: Dict[str, float]