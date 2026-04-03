@description('Azure region for the resource')
param location string

@description('Unique token for resource naming')
param resourceToken string

@description('Tags to apply')
param tags object

var acrName = replace('cr${resourceToken}', '-', '')

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

output loginServer string = acr.properties.loginServer
output name string = acr.name
