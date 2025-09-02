# Second Brain - Cloud Deployment Strategy

## Overview

This document outlines our phased approach to cloud deployment, starting with local testing on MacBook Pro M3, then scaling to VPS and eventually full cloud automation with Terraform.

**Core Principles:**
- 💰 **Zero Cost Initially** - Test everything locally first
- 🔄 **Incremental Deployment** - Each phase builds on the previous
- 🤖 **Automation First** - Manual processes become automated scripts
- 🏢 **Multi-Tenant Ready** - Every step considers tenant isolation

---

## Phase 1: Local Multi-Tenant Testing (MacBook Pro M3)

### 1.1 Local Container Setup

```bash
# Directory structure for local deployment
second_brain/
├── deployment/
│   ├── local/
│   │   ├── docker-compose.yml       # Local multi-tenant setup
│   │   ├── nginx.conf               # Local reverse proxy
│   │   ├── .env.local               # Local environment
│   │   └── init-local.sh            # Local setup script
│   ├── vps/
│   │   ├── docker-compose.prod.yml  # VPS production setup
│   │   ├── nginx.prod.conf          # Production nginx
│   │   ├── .env.template            # Template for VPS
│   │   └── deploy.sh                # VPS deployment script
│   └── cloud/
│       ├── terraform/               # Infrastructure as Code
│       ├── kubernetes/              # K8s manifests (future)
│       └── scripts/                 # Cloud deployment scripts
```

### 1.2 Local Multi-Tenant Architecture

```yaml
# deployment/local/docker-compose.yml
version: '3.8'

services:
  # Second Brain Application
  second-brain-app:
    build: 
      context: ../../
      dockerfile: deployment/Dockerfile
    ports:
      - "8082:8082"
    environment:
      - ENVIRONMENT=local
      - DATABASE_URL=sqlite:///./data/notes.db
      - MULTI_TENANT_MODE=true
      - TENANT_DOMAIN_MAPPING=true
    volumes:
      - ../../data:/app/data
      - ../../vault:/app/vault
      - ../../audio:/app/audio
    depends_on:
      - nginx-proxy
  
  # Local reverse proxy for tenant routing
  nginx-proxy:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ../../ssl:/etc/ssl/certs
    depends_on:
      - second-brain-app
  
  # Local AI services
  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
  
  # Optional: Local PostgreSQL for production-like testing
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: second_brain
      POSTGRES_USER: sb_user
      POSTGRES_PASSWORD: local_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  ollama_data:
  postgres_data:
```

### 1.3 Local Tenant Domain Mapping

```nginx
# deployment/local/nginx.conf
events {
    worker_connections 1024;
}

http {
    # Tenant routing based on subdomain
    map $host $tenant_id {
        default "default";
        ~^(?<tenant>.+)\.second-brain\.local$ $tenant;
    }
    
    upstream second_brain_app {
        server second-brain-app:8082;
    }
    
    server {
        listen 80;
        server_name *.second-brain.local second-brain.local;
        
        location / {
            proxy_pass http://second_brain_app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Tenant-ID $tenant_id;
        }
    }
}
```

### 1.4 Local Setup Script

```bash
#!/bin/bash
# deployment/local/init-local.sh

set -e

echo "🚀 Setting up Second Brain for local multi-tenant testing"

# Setup local DNS entries
echo "127.0.0.1 second-brain.local" | sudo tee -a /etc/hosts
echo "127.0.0.1 tenant1.second-brain.local" | sudo tee -a /etc/hosts  
echo "127.0.0.1 tenant2.second-brain.local" | sudo tee -a /etc/hosts
echo "127.0.0.1 demo.second-brain.local" | sudo tee -a /etc/hosts

# Create directories
mkdir -p ../../data ../../ssl

# Generate self-signed SSL certificates
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout ../../ssl/second-brain.key \
    -out ../../ssl/second-brain.crt \
    -subj "/C=US/ST=CA/L=SF/O=SecondBrain/CN=*.second-brain.local"

# Build and start services
docker-compose up --build -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 30

# Create demo tenants
curl -X POST http://localhost:8082/api/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "Demo Company", "plan": "starter"}'

curl -X POST http://localhost:8082/api/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Organization", "plan": "pro"}'

echo "✅ Local deployment complete!"
echo "🌐 Access URLs:"
echo "   - Main app: http://second-brain.local"
echo "   - Demo tenant: http://demo.second-brain.local"  
echo "   - Test tenant: http://test.second-brain.local"
echo "   - API docs: http://localhost:8082/docs"
```

---

## Phase 2: VPS Deployment (Manual → Automated)

### 2.1 VPS Requirements

**Recommended Specs:**
- **CPU**: 4+ cores (for AI processing)
- **RAM**: 8GB+ (4GB Ollama, 2GB Whisper, 2GB app)
- **Storage**: 100GB+ SSD
- **Network**: 1Gbps+ (for file uploads)
- **OS**: Ubuntu 22.04 LTS

**Cost Estimate**: $20-40/month (DigitalOcean, Linode, Hetzner)

### 2.2 VPS Manual Setup Process

```bash
# 1. Server Preparation
ssh root@your-vps-ip

# Update system
apt update && apt upgrade -y

# Install Docker & Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
apt install docker-compose-plugin -y

# Create application user
useradd -m -s /bin/bash second-brain
usermod -aG docker second-brain
```

### 2.3 VPS Deployment Script

```bash
#!/bin/bash
# deployment/vps/deploy.sh

set -e

VPS_IP="${1:-}"
if [ -z "$VPS_IP" ]; then
    echo "Usage: ./deploy.sh <VPS_IP>"
    exit 1
fi

echo "🚀 Deploying Second Brain to VPS: $VPS_IP"

# Copy files to VPS
scp -r ../.. second-brain@$VPS_IP:~/second-brain/

# SSH and setup
ssh second-brain@$VPS_IP << 'EOF'
    cd ~/second-brain/deployment/vps
    
    # Setup environment
    cp .env.template .env
    
    # Generate secure secrets
    echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env
    echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" >> .env
    echo "CSRF_SECRET_KEY=$(openssl rand -hex 32)" >> .env
    
    # Setup SSL with Let's Encrypt
    docker run --rm -v /etc/letsencrypt:/etc/letsencrypt \
        -v /var/lib/letsencrypt:/var/lib/letsencrypt \
        -p 80:80 certbot/certbot certonly --standalone \
        -d your-domain.com -d *.your-domain.com \
        --email your-email@domain.com --agree-tos --non-interactive
    
    # Start services
    docker-compose -f docker-compose.prod.yml up --build -d
    
    # Health check
    sleep 30
    curl -f http://localhost:8082/health || exit 1
    
    echo "✅ VPS deployment complete!"
EOF
```

### 2.4 Production Docker Compose

```yaml
# deployment/vps/docker-compose.prod.yml
version: '3.8'

services:
  second-brain:
    build: ../../
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://sb_user:${POSTGRES_PASSWORD}@postgres:5432/second_brain
      - MULTI_TENANT_MODE=true
      - REDIS_URL=redis://redis:6379
    volumes:
      - app_data:/app/data
      - app_vault:/app/vault
      - app_audio:/app/audio
    depends_on:
      - postgres
      - redis
      - ollama

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.prod.conf:/etc/nginx/nginx.conf
      - /etc/letsencrypt:/etc/letsencrypt
    depends_on:
      - second-brain

  postgres:
    image: postgres:15
    restart: unless-stopped
    environment:
      POSTGRES_DB: second_brain
      POSTGRES_USER: sb_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgres-init.sql:/docker-entrypoint-initdb.d/init.sql

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis_data:/data

  ollama:
    image: ollama/ollama
    restart: unless-stopped
    volumes:
      - ollama_data:/root/.ollama

volumes:
  app_data:
  app_vault:
  app_audio:
  postgres_data:
  redis_data:
  ollama_data:
```

---

## Phase 3: Infrastructure as Code (Terraform)

### 3.1 Terraform Structure

```
deployment/cloud/terraform/
├── modules/
│   ├── vpc/                    # Network setup
│   ├── security-groups/        # Firewall rules
│   ├── load-balancer/         # ALB for multi-tenant routing
│   ├── ecs/                   # Container orchestration
│   ├── rds/                   # Managed PostgreSQL
│   └── secrets/               # Parameter store
├── environments/
│   ├── dev/                   # Development environment
│   ├── staging/               # Staging environment
│   └── prod/                  # Production environment
├── main.tf
├── variables.tf
├── outputs.tf
└── terraform.tfvars.template
```

### 3.2 Core Infrastructure Module

```hcl
# deployment/cloud/terraform/main.tf
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# VPC and Networking
module "vpc" {
  source = "./modules/vpc"
  
  project_name = var.project_name
  environment  = var.environment
}

# Security Groups
module "security_groups" {
  source = "./modules/security-groups"
  
  vpc_id = module.vpc.vpc_id
}

# Application Load Balancer for tenant routing
module "load_balancer" {
  source = "./modules/load-balancer"
  
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.public_subnet_ids
  security_group_id = module.security_groups.alb_sg_id
}

# ECS Cluster
module "ecs" {
  source = "./modules/ecs"
  
  project_name = var.project_name
  environment  = var.environment
  vpc_id       = module.vpc.vpc_id
  subnet_ids   = module.vpc.private_subnet_ids
  
  # Multi-tenant configuration
  app_image = var.app_image
  app_count = var.app_count
}

# RDS PostgreSQL
module "rds" {
  source = "./modules/rds"
  
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids
  security_group_id = module.security_groups.rds_sg_id
}
```

### 3.3 Multi-Tenant Load Balancer

```hcl
# deployment/cloud/terraform/modules/load-balancer/main.tf
resource "aws_lb" "main" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.security_group_id]
  subnets           = var.subnet_ids

  tags = {
    Name = "${var.project_name}-alb"
  }
}

# Listener with tenant routing
resource "aws_lb_listener" "main" {
  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

# Tenant-based routing rules
resource "aws_lb_listener_rule" "tenant_routing" {
  listener_arn = aws_lb_listener.main.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }

  condition {
    host_header {
      values = ["*.${var.domain_name}"]
    }
  }
}
```

### 3.4 Deployment Automation Script

```bash
#!/bin/bash
# deployment/cloud/deploy-cloud.sh

set -e

ENVIRONMENT="${1:-dev}"
AWS_REGION="${2:-us-west-2}"

echo "🚀 Deploying Second Brain to AWS ($ENVIRONMENT)"

# Setup Terraform
cd terraform/
terraform init

# Plan deployment
terraform plan \
  -var="environment=$ENVIRONMENT" \
  -var="aws_region=$AWS_REGION" \
  -var-file="environments/$ENVIRONMENT.tfvars"

# Confirm deployment
read -p "Deploy to $ENVIRONMENT? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    terraform apply \
      -var="environment=$ENVIRONMENT" \
      -var="aws_region=$AWS_REGION" \
      -var-file="environments/$ENVIRONMENT.tfvars" \
      -auto-approve
    
    # Output deployment info
    terraform output
    
    echo "✅ Cloud deployment complete!"
fi
```

---

## Phase 4: CI/CD Pipeline

### 4.1 GitHub Actions Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy Second Brain

on:
  push:
    branches: [main, staging]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Run tests
        run: |
          pip install -r requirements.txt
          pytest tests/

  deploy-staging:
    if: github.ref == 'refs/heads/staging'
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to staging
        run: |
          ./deployment/cloud/deploy-cloud.sh staging

  deploy-production:
    if: github.ref == 'refs/heads/main'
    needs: test
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to production
        run: |
          ./deployment/cloud/deploy-cloud.sh prod
```

---

## Multi-Tenant Considerations

### Tenant Isolation Strategies

1. **Database-Level Isolation**
   ```sql
   -- Row-level security in PostgreSQL
   ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
   CREATE POLICY tenant_isolation ON notes 
   FOR ALL TO application_user 
   USING (tenant_id = current_setting('app.current_tenant_id'));
   ```

2. **Application-Level Routing**
   ```python
   # Middleware for tenant context
   @app.middleware("http")
   async def tenant_middleware(request: Request, call_next):
       host = request.headers.get("host", "")
       tenant_id = extract_tenant_from_host(host)
       set_tenant_context(tenant_id)
       response = await call_next(request)
       return response
   ```

3. **File Storage Isolation**
   ```
   storage/
   ├── tenant_123/
   │   ├── audio/
   │   ├── vault/
   │   └── uploads/
   └── tenant_456/
       ├── audio/
       ├── vault/
       └── uploads/
   ```

### Deployment Timeline

| Phase | Duration | Cost | Complexity |
|-------|----------|------|------------|
| **Phase 1**: Local Testing | 1-2 days | $0 | Low |
| **Phase 2**: VPS Manual | 1 day | $25/month | Medium |
| **Phase 3**: VPS Automated | 2-3 days | $25/month | Medium |
| **Phase 4**: Terraform/AWS | 1 week | $100+/month | High |
| **Phase 5**: Full CI/CD | 2-3 days | Marginal | High |

### Next Immediate Steps

1. **Create Dockerfile** for containerization
2. **Implement tenant middleware** in FastAPI
3. **Setup local Docker Compose** for testing
4. **Create tenant routing logic** in nginx
5. **Test multi-tenant functionality** locally

This strategy gives us a clear path from $0 local testing to full cloud automation, with each step building on the previous one. Would you like me to start implementing Phase 1 (local Docker setup)?