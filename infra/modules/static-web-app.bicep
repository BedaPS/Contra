@description('Azure region for Static Web App (must be a supported SWA region)')
param location string

@description('Environment name for resource naming')
param environmentName string

@description('Tags to apply')
param tags object

resource staticWebApp 'Microsoft.Web/staticSites@2023-12-01' = {
  name: 'swa-${environmentName}'
  location: location
  tags: tags
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    stagingEnvironmentPolicy: 'Enabled'
    allowConfigFileUpdates: true
    buildProperties: {
      skipGithubActionWorkflowGeneration: true
    }
  }
}

output name string = staticWebApp.name
output defaultHostname string = staticWebApp.properties.defaultHostname
