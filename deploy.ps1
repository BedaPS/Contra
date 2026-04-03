<#
.SYNOPSIS
  Deploy Contra to Azure (Container Apps + Static Web Apps + Azure SQL)

.DESCRIPTION
  This script deploys all Azure infrastructure using Bicep, builds and pushes
  the backend Docker image, and deploys the Angular frontend to Static Web Apps.

.PARAMETER EnvironmentName
  Name for the Azure environment (used in resource group and resource names).
  Default: "contra"

.PARAMETER Location
  Azure region for resources. Default: "centralindia"

.PARAMETER SqlAdminLogin
  SQL Server admin username. Default: "contraadmin"

.EXAMPLE
  .\deploy.ps1
  .\deploy.ps1 -EnvironmentName "contra-dev" -Location "centralindia"
#>

param(
    [string]$EnvironmentName = "contra",
    [string]$Location = "centralindia",
    [string]$SwaLocation = "eastasia",
    [string]$SqlAdminLogin = "contraadmin"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ROOT_DIR = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$ROOT_DIR\infra\main.bicep")) {
    $ROOT_DIR = $PSScriptRoot
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Contra — Azure Deployment" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan
Write-Host "Environment : $EnvironmentName"
Write-Host "Location    : $Location"
Write-Host "SWA Location: $SwaLocation"
Write-Host "SQL Admin   : $SqlAdminLogin"
Write-Host ""

# ── Pre-flight checks ───────────────────────────────────────────────────────
Write-Host "[1/7] Pre-flight checks..." -ForegroundColor Yellow

$azVersion = az version 2>$null | ConvertFrom-Json
if (-not $azVersion) {
    Write-Error "Azure CLI is not installed. Install from https://aka.ms/installazurecli"
    exit 1
}
Write-Host "  Azure CLI: $($azVersion.'azure-cli')" -ForegroundColor Green

$account = az account show 2>$null | ConvertFrom-Json
if (-not $account) {
    Write-Host "  Not logged in. Opening browser for login..." -ForegroundColor Yellow
    az login | Out-Null
    $account = az account show | ConvertFrom-Json
}
Write-Host "  Subscription: $($account.name) ($($account.id))" -ForegroundColor Green

$dockerVersion = docker version --format '{{.Server.Version}}' 2>$null
if (-not $dockerVersion) {
    Write-Error "Docker is not running. Please start Docker Desktop."
    exit 1
}
Write-Host "  Docker: $dockerVersion" -ForegroundColor Green

# ── Prompt for SQL password ──────────────────────────────────────────────────
Write-Host ""
$SqlAdminPassword = Read-Host -Prompt "Enter SQL admin password (min 8 chars, requires uppercase, lowercase, number)" -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SqlAdminPassword)
$SqlPasswordPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
[System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR)

if ($SqlPasswordPlain.Length -lt 8) {
    Write-Error "Password must be at least 8 characters."
    exit 1
}

# ── Register resource providers ──────────────────────────────────────────────
Write-Host "`n[2/7] Registering resource providers..." -ForegroundColor Yellow
$providers = @("Microsoft.App", "Microsoft.Sql", "Microsoft.Web", "Microsoft.ContainerRegistry", "Microsoft.OperationalInsights")
foreach ($provider in $providers) {
    $state = az provider show -n $provider --query "registrationState" -o tsv 2>$null
    if ($state -ne "Registered") {
        Write-Host "  Registering $provider..." -ForegroundColor Gray
        az provider register --namespace $provider | Out-Null
    } else {
        Write-Host "  $provider — already registered" -ForegroundColor Green
    }
}
# Wait for critical providers
foreach ($provider in @("Microsoft.App", "Microsoft.Sql")) {
    $maxWait = 120
    $waited = 0
    while ($waited -lt $maxWait) {
        $state = az provider show -n $provider --query "registrationState" -o tsv 2>$null
        if ($state -eq "Registered") { break }
        Start-Sleep -Seconds 5
        $waited += 5
    }
    if ($state -ne "Registered") {
        Write-Warning "$provider is still in '$state' state. Deployment may fail."
    }
}

# ── Deploy infrastructure ────────────────────────────────────────────────────
Write-Host "`n[3/7] Deploying Azure infrastructure (Bicep)..." -ForegroundColor Yellow
Write-Host "  This may take 3-5 minutes..." -ForegroundColor Gray

$deployResult = az deployment sub create `
    --name "contra-$((Get-Date).ToString('yyyyMMdd-HHmmss'))" `
    --location $Location `
    --template-file "$ROOT_DIR\infra\main.bicep" `
    --parameters "$ROOT_DIR\infra\main.parameters.json" `
    --parameters environmentName=$EnvironmentName `
    --parameters location=$Location `
    --parameters swaLocation=$SwaLocation `
    --parameters sqlAdminLogin=$SqlAdminLogin `
    --parameters sqlAdminPassword=$SqlPasswordPlain `
    2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Error "Infrastructure deployment failed:`n$deployResult"
    exit 1
}

$outputs = $deployResult | ConvertFrom-Json | Select-Object -ExpandProperty properties | Select-Object -ExpandProperty outputs
$rgName = $outputs.resourceGroupName.value
$acrName = $outputs.acrName.value
$acrLoginServer = $outputs.acrLoginServer.value
$backendFqdn = $outputs.backendFqdn.value
$backendUrl = $outputs.backendUrl.value
$swaName = $outputs.staticWebAppName.value
$swaHostname = $outputs.staticWebAppUrl.value

Write-Host "  Resource Group : $rgName" -ForegroundColor Green
Write-Host "  ACR            : $acrLoginServer" -ForegroundColor Green
Write-Host "  Backend FQDN   : $backendFqdn" -ForegroundColor Green
Write-Host "  SWA            : $swaHostname" -ForegroundColor Green

# ── Build and push Docker image ──────────────────────────────────────────────
Write-Host "`n[4/7] Building and pushing backend Docker image..." -ForegroundColor Yellow

az acr login --name $acrName 2>$null
$imageName = "$acrLoginServer/contra-backend:latest"

docker build -t $imageName "$ROOT_DIR\backend"
if ($LASTEXITCODE -ne 0) { Write-Error "Docker build failed."; exit 1 }

docker push $imageName
if ($LASTEXITCODE -ne 0) { Write-Error "Docker push failed."; exit 1 }

Write-Host "  Image pushed: $imageName" -ForegroundColor Green

# ── Update Container App with real image ─────────────────────────────────────
Write-Host "`n[5/7] Updating Container App with backend image..." -ForegroundColor Yellow

$acrPassword = az acr credential show --name $acrName --query "passwords[0].value" -o tsv

az containerapp registry set `
    --name "contra-backend" `
    --resource-group $rgName `
    --server $acrLoginServer `
    --username $acrName `
    --password $acrPassword `
    2>$null

az containerapp update `
    --name "contra-backend" `
    --resource-group $rgName `
    --image $imageName `
    --set-env-vars "CORS_ORIGINS=https://$swaHostname" `
    2>$null

Write-Host "  Container App updated with real image" -ForegroundColor Green

# ── Build Angular frontend ───────────────────────────────────────────────────
Write-Host "`n[6/7] Building Angular frontend..." -ForegroundColor Yellow

$envFile = "$ROOT_DIR\frontend\src\environments\environment.prod.ts"
$originalEnv = Get-Content $envFile -Raw

# Temporarily update API base URL to point to Container App
$updatedEnv = $originalEnv -replace "apiBaseUrl: '/api/v1'", "apiBaseUrl: '$backendUrl/api/v1'"
Set-Content $envFile $updatedEnv -NoNewline

Push-Location "$ROOT_DIR\frontend"
try {
    npm ci --silent 2>$null
    npx ng build --configuration production
    if ($LASTEXITCODE -ne 0) { throw "Angular build failed." }
    Write-Host "  Angular build complete" -ForegroundColor Green
} finally {
    # Restore original environment file
    Set-Content $envFile $originalEnv -NoNewline
    Pop-Location
}

# ── Deploy to Static Web Apps ────────────────────────────────────────────────
Write-Host "`n[7/7] Deploying frontend to Static Web Apps..." -ForegroundColor Yellow

$swaToken = az staticwebapp secrets list --name $swaName --resource-group $rgName --query "properties.apiKey" -o tsv

# Determine the output path (Angular 21 outputs to dist/frontend/browser)
$distPath = "$ROOT_DIR\frontend\dist\frontend\browser"
if (-not (Test-Path $distPath)) {
    $distPath = "$ROOT_DIR\frontend\dist\frontend"
}

# Install SWA CLI if needed and deploy
npx --yes @azure/static-web-apps-cli deploy $distPath `
    --deployment-token $swaToken `
    --env production `
    2>$null

if ($LASTEXITCODE -ne 0) {
    Write-Warning "SWA CLI deploy failed. Trying az CLI fallback..."
    # Copy staticwebapp.config.json to dist
    Copy-Item "$ROOT_DIR\frontend\staticwebapp.config.json" "$distPath\staticwebapp.config.json" -Force
    az staticwebapp deploy `
        --name $swaName `
        --resource-group $rgName `
        --source $distPath `
        --token $swaToken `
        2>$null
}

Write-Host "  Frontend deployed" -ForegroundColor Green

# ── Summary ──────────────────────────────────────────────────────────────────
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Deployment Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Frontend URL : https://$swaHostname" -ForegroundColor Green
Write-Host "  Backend URL  : $backendUrl" -ForegroundColor Green
Write-Host "  API Health   : $backendUrl/api/v1/health" -ForegroundColor Green
Write-Host "  Resource Group: $rgName" -ForegroundColor Green
Write-Host ""
Write-Host "To tear down all resources:" -ForegroundColor Yellow
Write-Host "  az group delete --name $rgName --yes --no-wait" -ForegroundColor Gray
Write-Host ""
