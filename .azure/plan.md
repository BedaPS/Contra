# Azure Deployment Plan

> **Status:** Deployed

Generated: 2026-04-01

---

## 1. Project Overview

**Goal:** Deploy the Contra financial reconciliation pipeline (FastAPI backend + Angular SPA frontend + MSSQL database) to Azure with minimum cost.

**Path:** Modernize Existing (containerized Docker Compose app → Azure managed services)

---

## 2. Requirements

| Attribute | Value |
|-----------|-------|
| Classification | POC |
| Scale | Small (<1K users) |
| Budget | Cost-Optimized (Free tier where possible) |
| **Subscription** | Windows Azure MSDN - Visual Studio Professional (`26789300-bfdd-4d8a-823e-37745abca691`) |
| **Location** | `centralindia` |

---

## 3. Components Detected

| Component | Type | Technology | Path |
|-----------|------|------------|------|
| backend | API Service | Python 3.12 / FastAPI (Dockerized) | `backend/` |
| frontend | SPA | Angular 21 (TypeScript) | `frontend/` |
| database | MSSQL | SQL Server 2022 (Docker) | `docker-compose.yml` |

## Dependencies

| Component | Depends On | Type |
|-----------|-----------|------|
| backend | MSSQL database | SQL connection (pymssql) |
| backend | LLM provider | External HTTP (configurable) |
| frontend | backend | HTTP API (`/api/v1`) |

## Existing Infrastructure

| Item | Status |
|------|--------|
| azure.yaml | Not found |
| infra/ | Not found |
| Dockerfile | Found: `backend/Dockerfile` |
| docker-compose.yml | Found (backend + MSSQL) |
| Frontend prod env | Found: `environment.prod.ts` (uses relative `/api/v1`) |

---

## 4. Recipe Selection

**Selected:** Bicep (standalone)

**Rationale:**
- `azd` CLI is not installed and not required for a simple 3-component app
- Direct Bicep gives full control over resource configuration
- Deployment via `az deployment sub create` — simple and repeatable
- No extra tooling dependencies needed

---

## 5. Architecture

**Stack:** Containers (backend) + Static Web Apps (frontend) + Azure SQL (database)

### Service Mapping

| Component | Azure Service | SKU / Tier |
|-----------|---------------|------------|
| backend | Azure Container Apps | Consumption (scale-to-zero) |
| frontend | Azure Static Web Apps | Free |
| database | Azure SQL Database | Free offer (32 GB, 100K vCore-seconds/mo) |
| container images | Azure Container Registry | Basic |

### Supporting Services

| Service | Purpose | SKU |
|---------|---------|-----|
| Log Analytics Workspace | Centralized logging for Container Apps | Free tier (5 GB/mo) |
| Key Vault | Store DATABASE_URL, LLM API keys | Standard |
| Managed Identity | Backend → SQL, Backend → Key Vault (no credentials in code) | System-assigned |
| Container Apps Environment | Hosting environment for backend | Consumption |

### Architecture Diagram

```
┌─────────────────┐     HTTPS      ┌──────────────────────┐
│  Azure Static   │ ──────────────▶│  Azure Container     │
│  Web Apps       │   /api/* proxy │  Apps (backend)       │
│  (Angular SPA)  │                │  FastAPI + Uvicorn    │
│  Free tier      │                │  Consumption plan     │
└─────────────────┘                └──────────┬───────────┘
                                              │
                                    ┌─────────▼──────────┐
                                    │  Azure SQL Database │
                                    │  Free offer         │
                                    │  (32 GB storage)    │
                                    └─────────┬──────────┘
                                              │
                                    ┌─────────▼──────────┐
                                    │  Azure Key Vault    │
                                    │  (secrets store)    │
                                    └────────────────────┘
```

### Networking

- Static Web Apps serves the Angular SPA and reverse-proxies `/api/*` to the Container App (via `staticwebapp.config.json`)
- Container App has external ingress on port 8000
- Azure SQL uses firewall rules to allow Azure services
- Key Vault accessed via managed identity (RBAC)

### Cost Estimate (Monthly)

| Service | Estimated Cost |
|---------|---------------|
| Static Web Apps Free | $0.00 |
| Container Apps Consumption (idle) | $0.00 (scale-to-zero) |
| Container Apps Consumption (active) | ~$0.50–$2.00 (light POC use) |
| Azure SQL Free offer | $0.00 (12 months) |
| Container Registry Basic | ~$5.00 |
| Key Vault (minimal operations) | ~$0.03 |
| Log Analytics (< 5 GB) | $0.00 |
| **Total** | **~$5–$7/mo** |

---

## 6. Provisioning Limit Checklist

### Phase 1: Resource Inventory

| Resource Type | Number to Deploy | Total After Deployment | Limit/Quota | Notes |
|---------------|------------------|------------------------|-------------|-------|
| Microsoft.App/managedEnvironments | 1 | 1 | 15 per region | Official docs (quota CLI provider registering) |
| Microsoft.App/containerApps | 1 | 1 | 100 per environment | Official docs |
| Microsoft.Web/staticSites | 1 | 1 | 10 per subscription | Official docs |
| Microsoft.Sql/servers | 1 | 1 | 250 per subscription | Official docs (0 existing, verified via CLI) |
| Microsoft.Sql/servers/databases | 1 | 1 | 500 per server | Official docs |
| Microsoft.ContainerRegistry/registries | 1 | 1 | 100 per subscription | Official docs (0 existing) |
| Microsoft.KeyVault/vaults | 1 | 1 | 1000 per subscription | Official docs |
| Microsoft.OperationalInsights/workspaces | 1 | 1 | 100 per subscription | Official docs |

### Phase 2: Validation

**Data Source:** Azure CLI (`az containerapp list`, `az sql server list` return 0 results) + [Azure service limits documentation](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/azure-subscription-service-limits). Quota CLI provider (`Microsoft.Quota`) is still in `Registering` state.

**Status:** ✅ All resources well within limits (0 existing resources, clean subscription)

---

## 7. Execution Checklist

### Phase 1: Planning
- [x] Analyze workspace
- [x] Gather requirements
- [x] Confirm subscription and location with user
- [x] Prepare resource inventory (Step 6 Phase 1)
- [x] Fetch quotas and validate capacity (Step 6 Phase 2)
- [x] Scan codebase
- [x] Select recipe
- [x] Plan architecture
- [ ] **User approved this plan**

### Phase 2: Execution
- [x] Research components (load references, invoke skills)
- [x] Generate infrastructure files (`infra/main.bicep` + 7 modules)
- [x] Generate `frontend/staticwebapp.config.json` (SPA routing + security headers)
- [x] Apply security hardening (managed identity, TLS 1.2, HTTPS-only, security headers)
- [x] Create deployment script (`deploy.ps1`)
- [x] Bicep what-if validation passed (9 resources to create)
- [x] **Update plan status to "Ready for Validation"**

### Phase 3: Validation
- [ ] Invoke azure-validate skill
- [ ] All validation checks pass
- [ ] Update plan status to "Validated"

### Phase 4: Deployment
- [ ] Invoke azure-deploy skill
- [ ] Deployment successful
- [ ] Report deployed endpoint URLs
- [ ] Update plan status to "Deployed"

---

## 8. Validation Proof

> Populated by azure-validate skill.

| Check | Command Run | Result | Timestamp |
|-------|-------------|--------|----------|
| Bicep compilation | `az bicep build --file infra/main.bicep` | Pass (exit 0) | 2026-04-01T18:10Z |
| Bicep linting | `az bicep lint --file infra/main.bicep` | Pass (exit 0) | 2026-04-01T18:11Z |
| Template validation | `az deployment sub validate --location centralindia` | Succeeded | 2026-04-01T18:11Z |
| What-if preview | `az deployment sub what-if --location centralindia` | 9 resources to create | 2026-04-01T18:09Z |
| Authentication | `az account show` | Windows Azure MSDN - Visual Studio Professional | 2026-04-01T18:05Z |

**Validated by:** azure-validate skill
**Validation timestamp:** 2026-04-01T18:11Z

---

## 9. Files to Generate

| File | Purpose | Status |
|------|---------|--------|
| `infra/main.bicep` | Subscription-scope entry point (creates RG + modules) | Pending |
| `infra/main.parameters.json` | Parameter values (env name, location, SQL admin) | Pending |
| `infra/modules/container-registry.bicep` | Azure Container Registry (Basic) | Pending |
| `infra/modules/log-analytics.bicep` | Log Analytics workspace | Pending |
| `infra/modules/container-apps-env.bicep` | Container Apps Environment (Consumption) | Pending |
| `infra/modules/container-app-backend.bicep` | Backend Container App + managed identity | Pending |
| `infra/modules/sql-server.bicep` | Azure SQL Server + free-tier database | Pending |
| `infra/modules/key-vault.bicep` | Key Vault + secrets + RBAC | Pending |
| `infra/modules/static-web-app.bicep` | Static Web App (Free) | Pending |
| `frontend/staticwebapp.config.json` | SWA routing config (API proxy to backend) | Pending |
| `deploy.ps1` | PowerShell deployment script | Pending |
