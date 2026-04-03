@description('Azure region for the resource')
param location string

@description('Tags to apply')
param tags object

@description('Container Apps Environment resource ID')
param environmentId string

@secure()
@description('Full DATABASE_URL connection string')
param databaseUrl string

@description('Container image to deploy')
param containerImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('CORS allowed origins (comma-separated)')
param corsOrigins string = '*'

resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'contra-backend'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: [corsOrigins]
          allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
          allowedHeaders: ['*']
          maxAge: 3600
        }
      }
      secrets: [
        {
          name: 'database-url'
          value: databaseUrl
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'contra-backend'
          image: containerImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'LLM_PROVIDER'
              value: 'stub'
            }
            {
              name: 'LLM_API_KEY'
              value: ''
            }
            {
              name: 'LLM_MODEL'
              value: ''
            }
            {
              name: 'CORS_ORIGINS'
              value: corsOrigins
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

output fqdn string = backendApp.properties.configuration.ingress.fqdn
output name string = backendApp.name
output principalId string = backendApp.identity.principalId
