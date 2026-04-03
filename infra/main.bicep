targetScope = 'subscription'

@minLength(1)
@maxLength(20)
@description('Name of the environment (used for resource naming)')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Location for Static Web App (must be a supported SWA region)')
param swaLocation string = 'eastasia'

@description('SQL Server administrator login')
param sqlAdminLogin string = 'contraadmin'

@secure()
@description('SQL Server administrator password')
param sqlAdminPassword string

var tags = {
  environment: environmentName
  project: 'contra'
}

var resourceToken = uniqueString(subscription().id, environmentName, location)

// ── Resource Group ──────────────────────────────────────────────────────────
resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// ── Log Analytics ───────────────────────────────────────────────────────────
module logAnalytics './modules/log-analytics.bicep' = {
  name: 'log-analytics'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
  }
}

// ── Container Registry ──────────────────────────────────────────────────────
module acr './modules/container-registry.bicep' = {
  name: 'container-registry'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
  }
}

// ── Azure SQL Server + Database ─────────────────────────────────────────────
module sqlServer './modules/sql-server.bicep' = {
  name: 'sql-server'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
    sqlAdminLogin: sqlAdminLogin
    sqlAdminPassword: sqlAdminPassword
  }
}

// ── Container Apps Environment ──────────────────────────────────────────────
module containerAppsEnv './modules/container-apps-env.bicep' = {
  name: 'container-apps-env'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
  }
}

// ── Backend Container App ───────────────────────────────────────────────────
module backendApp './modules/container-app-backend.bicep' = {
  name: 'container-app-backend'
  scope: rg
  params: {
    location: location
    tags: tags
    environmentId: containerAppsEnv.outputs.environmentId
    databaseUrl: 'mssql+pymssql://${sqlAdminLogin}:${sqlAdminPassword}@${sqlServer.outputs.sqlServerFqdn}:1433/contra'
  }
}

// ── Static Web App (Frontend) ───────────────────────────────────────────────
module swa './modules/static-web-app.bicep' = {
  name: 'static-web-app'
  scope: rg
  params: {
    location: swaLocation
    environmentName: environmentName
    tags: tags
  }
}

// ── Outputs ─────────────────────────────────────────────────────────────────
output resourceGroupName string = rg.name
output acrLoginServer string = acr.outputs.loginServer
output acrName string = acr.outputs.name
output backendFqdn string = backendApp.outputs.fqdn
output backendUrl string = 'https://${backendApp.outputs.fqdn}'
output sqlServerFqdn string = sqlServer.outputs.sqlServerFqdn
output staticWebAppName string = swa.outputs.name
output staticWebAppUrl string = swa.outputs.defaultHostname
