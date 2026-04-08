metadata description = 'Creates a Log Analytics query pack for storing and sharing queries.'
param name string
param location string = resourceGroup().location
param tags object = {}

resource queryPack 'Microsoft.OperationalInsights/queryPacks@2019-09-01' = {
  name: name
  location: location
  tags: tags
  properties: {}
}

// Sample queries for AI project monitoring
resource queryAgentTraces 'Microsoft.OperationalInsights/queryPacks/queries@2019-09-01' = {
  parent: queryPack
  name: guid(queryPack.id, 'ai-agent-traces')
  properties: {
    displayName: 'AI Agent Traces'
    description: 'View all AI agent traces and telemetry'
    body: '''traces
| where cloud_RoleName contains "agent" or customDimensions contains "agent"
| project timestamp, message, severityLevel, customDimensions
| order by timestamp desc'''
    related: {
      categories: ['applications']
    }
  }
}

resource queryAgentErrors 'Microsoft.OperationalInsights/queryPacks/queries@2019-09-01' = {
  parent: queryPack
  name: guid(queryPack.id, 'ai-agent-errors')
  properties: {
    displayName: 'AI Agent Errors'
    description: 'View errors from AI agents'
    body: '''exceptions
| where cloud_RoleName contains "agent" or customDimensions contains "agent"
| project timestamp, problemId, outerMessage, innermostMessage, severityLevel
| order by timestamp desc'''
    related: {
      categories: ['applications']
    }
  }
}

resource queryAgentPerformance 'Microsoft.OperationalInsights/queryPacks/queries@2019-09-01' = {
  parent: queryPack
  name: guid(queryPack.id, 'ai-agent-performance')
  properties: {
    displayName: 'AI Agent Performance'
    description: 'Monitor AI agent response times and performance metrics'
    body: '''requests
| where cloud_RoleName contains "agent"
| summarize 
    RequestCount = count(),
    AvgDuration = avg(duration),
    P50Duration = percentile(duration, 50),
    P95Duration = percentile(duration, 95),
    P99Duration = percentile(duration, 99)
    by bin(timestamp, 5m), name
| order by timestamp desc'''
    related: {
      categories: ['applications']
    }
  }
}

resource queryAgentDependencies 'Microsoft.OperationalInsights/queryPacks/queries@2019-09-01' = {
  parent: queryPack
  name: guid(queryPack.id, 'ai-agent-dependencies')
  properties: {
    displayName: 'AI Agent Dependencies'
    description: 'Track external dependencies called by AI agents'
    body: '''dependencies
| where cloud_RoleName contains "agent"
| summarize 
    CallCount = count(),
    AvgDuration = avg(duration),
    SuccessRate = 100.0 * countif(success == true) / count()
    by target, type, name
| order by CallCount desc'''
    related: {
      categories: ['applications']
    }
  }
}

resource queryTokenUsage 'Microsoft.OperationalInsights/queryPacks/queries@2019-09-01' = {
  parent: queryPack
  name: guid(queryPack.id, 'ai-token-usage')
  properties: {
    displayName: 'AI Token Usage'
    description: 'Track AI model token consumption'
    body: '''traces
| where customDimensions has "completion_tokens" or customDimensions has "prompt_tokens"
| extend 
    PromptTokens = toint(customDimensions.prompt_tokens),
    CompletionTokens = toint(customDimensions.completion_tokens),
    TotalTokens = toint(customDimensions.total_tokens)
| where isnotnull(TotalTokens)
| summarize 
    TotalPromptTokens = sum(PromptTokens),
    TotalCompletionTokens = sum(CompletionTokens),
    TotalTokens = sum(TotalTokens)
    by bin(timestamp, 1h)
| order by timestamp desc'''
    related: {
      categories: ['applications']
    }
  }
}

output id string = queryPack.id
output name string = queryPack.name
output queryPackId string = queryPack.id
