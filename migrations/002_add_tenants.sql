-- Multi-Tenant Schema Migration
-- Adds tenant support to Second Brain with proper data isolation

-- =====================================================================
-- TENANTS TABLE
-- =====================================================================

CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    plan TEXT DEFAULT 'free',
    status TEXT DEFAULT 'active',
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    -- Billing and limits
    max_users INTEGER DEFAULT 5,
    max_notes INTEGER DEFAULT 1000,
    max_storage_mb INTEGER DEFAULT 500,
    
    -- Feature flags
    features JSON DEFAULT '{}',
    
    -- Settings
    settings JSON DEFAULT '{}'
);

-- =====================================================================
-- TENANT MEMBERSHIPS
-- =====================================================================

CREATE TABLE IF NOT EXISTS tenant_memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT DEFAULT 'member', -- owner, admin, member
    status TEXT DEFAULT 'active',
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(tenant_id, user_id)
);

-- =====================================================================
-- UPDATE EXISTING TABLES FOR MULTI-TENANCY
-- =====================================================================

-- Add tenant_id to users table
ALTER TABLE users ADD COLUMN tenant_id TEXT REFERENCES tenants(id);
ALTER TABLE users ADD COLUMN is_tenant_admin BOOLEAN DEFAULT FALSE;

-- Add tenant_id to notes table (if not exists)
ALTER TABLE notes ADD COLUMN tenant_id TEXT REFERENCES tenants(id);

-- =====================================================================
-- TENANT USAGE TRACKING
-- =====================================================================

CREATE TABLE IF NOT EXISTS tenant_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    metric TEXT NOT NULL, -- 'notes', 'storage', 'api_calls', etc.
    value INTEGER NOT NULL,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

-- =====================================================================
-- TENANT SETTINGS
-- =====================================================================

CREATE TABLE IF NOT EXISTS tenant_settings (
    tenant_id TEXT NOT NULL,
    setting_key TEXT NOT NULL,
    setting_value TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (tenant_id, setting_key),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

-- =====================================================================
-- TENANT WORKFLOWS (for Smart Automation)
-- =====================================================================

CREATE TABLE IF NOT EXISTS tenant_workflows (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    trigger_type TEXT NOT NULL,
    trigger_conditions JSON,
    actions JSON,
    status TEXT DEFAULT 'active',
    created_by INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);

-- =====================================================================
-- TENANT ROUTING RULES (for Intelligent Router)
-- =====================================================================

CREATE TABLE IF NOT EXISTS tenant_routing_rules (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    conditions JSON,
    routing_targets JSON,
    priority TEXT DEFAULT 'normal',
    processing_mode TEXT DEFAULT 'immediate',
    enabled BOOLEAN DEFAULT TRUE,
    created_by INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (created_by) REFERENCES users(id)
);

-- =====================================================================
-- INDEXES FOR PERFORMANCE
-- =====================================================================

CREATE INDEX IF NOT EXISTS idx_tenant_memberships_tenant_id ON tenant_memberships(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_memberships_user_id ON tenant_memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_notes_tenant_id ON notes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_usage_tenant_id ON tenant_usage(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_usage_metric ON tenant_usage(tenant_id, metric);
CREATE INDEX IF NOT EXISTS idx_tenant_workflows_tenant_id ON tenant_workflows(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_routing_rules_tenant_id ON tenant_routing_rules(tenant_id);

-- =====================================================================
-- TRIGGERS FOR AUTOMATIC TIMESTAMPS
-- =====================================================================

CREATE TRIGGER IF NOT EXISTS update_tenant_updated_at
    AFTER UPDATE ON tenants
BEGIN
    UPDATE tenants SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS update_tenant_workflows_updated_at
    AFTER UPDATE ON tenant_workflows
BEGIN
    UPDATE tenant_workflows SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- =====================================================================
-- DEFAULT TENANT FOR EXISTING DATA
-- =====================================================================

-- Create default tenant for existing single-tenant setup
INSERT OR IGNORE INTO tenants (
    id, name, slug, plan, status, max_users, max_notes, max_storage_mb
) VALUES (
    'default', 'Default Organization', 'default', 'unlimited', 'active', 999999, 999999, 999999
);

-- Assign existing users to default tenant
UPDATE users SET tenant_id = 'default' WHERE tenant_id IS NULL;

-- Assign existing notes to default tenant
UPDATE notes SET tenant_id = 'default' WHERE tenant_id IS NULL;

-- Create tenant membership for existing users
INSERT OR IGNORE INTO tenant_memberships (tenant_id, user_id, role)
SELECT 'default', id, 'owner' FROM users WHERE tenant_id = 'default';

-- =====================================================================
-- VIEWS FOR CONVENIENCE
-- =====================================================================

CREATE VIEW IF NOT EXISTS tenant_stats AS
SELECT 
    t.id as tenant_id,
    t.name as tenant_name,
    t.plan,
    t.status,
    COUNT(DISTINCT tm.user_id) as user_count,
    COUNT(DISTINCT n.id) as note_count,
    COALESCE(SUM(n.file_size), 0) as storage_used_bytes,
    t.max_users,
    t.max_notes,
    t.max_storage_mb * 1024 * 1024 as max_storage_bytes
FROM tenants t
LEFT JOIN tenant_memberships tm ON t.id = tm.tenant_id
LEFT JOIN notes n ON t.id = n.tenant_id
GROUP BY t.id, t.name, t.plan, t.status, t.max_users, t.max_notes, t.max_storage_mb;