metadata description = 'Creates an Azure Monitor Workbook for AI Agent monitoring with conversation traces, performance metrics, and token usage.'

param name string
param location string = resourceGroup().location
param tags object = {}
param applicationInsightsId string
param displayName string = 'AI Agent Monitoring Dashboard'

var workbookId = guid(resourceGroup().id, name)

resource workbook 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: workbookId
  location: location
  tags: tags
  kind: 'shared'
  properties: {
    displayName: displayName
    serializedData: string({
      version: 'Notebook/1.0'
      items: [
        // Header
        {
          type: 1
          content: {
            json: '# 🤖 AI Agent Monitoring Dashboard\n\nComprehensive monitoring for Microsoft Foundry Hosted Agents including conversation traces, performance metrics, and token usage analytics.'
          }
          name: 'header'
        }
        
        // Parameters
        {
          type: 9
          content: {
            version: 'KqlParameterItem/1.0'
            parameters: [
              {
                id: 'c4b69c01-2490-4e7b-a58c-c40a16b7a6e0'
                version: 'KqlParameterItem/1.0'
                name: 'TimeRange'
                type: 4
                isRequired: true
                value: {
                  durationMs: 86400000
                }
                typeSettings: {
                  selectableValues: [
                    {
                      durationMs: 3600000
                      createdTime: '2024-01-01T00:00:00.000Z'
                      isInitialTime: false
                      grain: 1
                      useDashboardTimeRange: false
                    }
                    {
                      durationMs: 14400000
                      createdTime: '2024-01-01T00:00:00.000Z'
                      isInitialTime: false
                      grain: 1
                      useDashboardTimeRange: false
                    }
                    {
                      durationMs: 86400000
                      createdTime: '2024-01-01T00:00:00.000Z'
                      isInitialTime: false
                      grain: 1
                      useDashboardTimeRange: false
                    }
                    {
                      durationMs: 604800000
                      createdTime: '2024-01-01T00:00:00.000Z'
                      isInitialTime: false
                      grain: 1
                      useDashboardTimeRange: false
                    }
                  ]
                }
                label: 'Time Range'
              }
              {
                id: 'agent-name-param'
                version: 'KqlParameterItem/1.0'
                name: 'AgentName'
                type: 1
                value: 'CalculatorAgentLG'
                label: 'Agent Name'
              }
            ]
            style: 'pills'
            queryType: 0
            resourceType: 'microsoft.insights/components'
          }
          name: 'parameters'
        }

        // Section: Overview Metrics
        {
          type: 1
          content: {
            json: '## 📊 Overview'
          }
          name: 'overview-header'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: '''requests
| where timestamp {TimeRange}
| extend
    foundryAgentName = coalesce(
        tostring(customDimensions['gen_ai.agent.name']),
        tostring(customDimensions['azure.ai.agentserver.agent_name'])
    )
| where foundryAgentName == "{AgentName}"
| summarize 
    TotalConversations = dcount(operation_Id),
    SuccessfulConversations = dcountif(operation_Id, success == true),
    FailedConversations = dcountif(operation_Id, success == false),
    AvgDuration = avg(duration),
    P95Duration = percentile(duration, 95)
| extend SuccessRate = round(100.0 * SuccessfulConversations / TotalConversations, 2)
| project 
    TotalConversations,
    SuccessfulConversations,
    FailedConversations,
    SuccessRate,
    AvgDuration = round(AvgDuration, 0),
    P95Duration = round(P95Duration, 0)'''
            size: 4
            title: 'Agent Performance Summary'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            visualization: 'tiles'
            tileSettings: {
              showBorder: false
              titleContent: {
                columnMatch: 'TotalConversations'
                formatter: 1
              }
              leftContent: {
                columnMatch: 'TotalConversations'
                formatter: 12
                formatOptions: {
                  palette: 'blue'
                }
              }
            }
          }
          customWidth: '100'
          name: 'overview-metrics'
        }

        // Section: Recent Conversations
        {
          type: 1
          content: {
            json: '## 💬 Recent Conversations'
          }
          name: 'conversations-header'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: '''requests
| where timestamp {TimeRange}
| extend
    foundryAgentName = coalesce(
        tostring(customDimensions['gen_ai.agent.name']),
        tostring(customDimensions['azure.ai.agentserver.agent_name'])
    ),
    agentId = tostring(customDimensions['gen_ai.agent.id']),
    agentVersion = iff(customDimensions['gen_ai.agent.id'] contains ":", tostring(split(customDimensions['gen_ai.agent.id'], ":")[1]), ""),
    conversationId = coalesce(
        tostring(customDimensions['gen_ai.conversation.id']),
        tostring(customDimensions['azure.ai.agentserver.conversation_id']),
        operation_Id
    )
| where foundryAgentName == "{AgentName}"
| project 
    Timestamp = timestamp,
    ["Conversation ID"] = conversationId,
    ["Agent Version"] = agentVersion,
    ["Duration (ms)"] = duration,
    Status = iff(success == true, "✅ Success", "❌ Failed"),
    ["Operation ID"] = operation_Id
| order by Timestamp desc
| take 20'''
            size: 0
            title: 'Recent Conversations'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            visualization: 'table'
            gridSettings: {
              formatters: [
                {
                  columnMatch: 'Timestamp'
                  formatter: 6
                }
                {
                  columnMatch: 'Duration (ms)'
                  formatter: 8
                  formatOptions: {
                    palette: 'greenRed'
                  }
                }
                {
                  columnMatch: 'Status'
                  formatter: 18
                  formatOptions: {
                    thresholdsOptions: 'icons'
                    thresholdsGrid: [
                      {
                        operator: 'contains'
                        thresholdValue: 'Success'
                        representation: 'success'
                        text: '{0}{1}'
                      }
                      {
                        operator: 'Default'
                        thresholdValue: null
                        representation: 'failed'
                        text: '{0}{1}'
                      }
                    ]
                  }
                }
              ]
            }
          }
          name: 'recent-conversations'
        }

        // Section: Token Usage
        {
          type: 1
          content: {
            json: '## 🎯 Token Usage Analytics'
          }
          name: 'tokens-header'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: '''dependencies
| where timestamp {TimeRange}
| where isnotempty(customDimensions['gen_ai.usage.input_tokens'])
| extend
    foundryAgentName = coalesce(
        tostring(customDimensions['gen_ai.agent.name']),
        tostring(customDimensions['azure.ai.agentserver.agent_name'])
    ),
    inputTokens = toint(customDimensions['gen_ai.usage.input_tokens']),
    outputTokens = toint(customDimensions['gen_ai.usage.output_tokens']),
    model = tostring(customDimensions['gen_ai.request.model'])
| summarize 
    TotalInputTokens = sum(inputTokens),
    TotalOutputTokens = sum(outputTokens),
    ConversationCount = dcount(operation_Id),
    AvgInputTokens = round(avg(inputTokens), 0),
    AvgOutputTokens = round(avg(outputTokens), 0)
    by bin(timestamp, 1h), model
| extend TotalTokens = TotalInputTokens + TotalOutputTokens
| order by timestamp desc'''
            size: 0
            title: 'Token Usage Over Time'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            visualization: 'linechart'
          }
          customWidth: '50'
          name: 'token-usage-chart'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: '''dependencies
| where timestamp {TimeRange}
| where isnotempty(customDimensions['gen_ai.usage.input_tokens'])
| extend
    inputTokens = toint(customDimensions['gen_ai.usage.input_tokens']),
    outputTokens = toint(customDimensions['gen_ai.usage.output_tokens']),
    model = tostring(customDimensions['gen_ai.request.model'])
| summarize 
    TotalInputTokens = sum(inputTokens),
    TotalOutputTokens = sum(outputTokens),
    CallCount = count()
    by Model = model
| extend TotalTokens = TotalInputTokens + TotalOutputTokens
| project Model, CallCount, TotalInputTokens, TotalOutputTokens, TotalTokens
| order by TotalTokens desc'''
            size: 0
            title: 'Token Usage by Model'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            visualization: 'table'
          }
          customWidth: '50'
          name: 'token-usage-table'
        }

        // Section: Tool Execution
        {
          type: 1
          content: {
            json: '## 🔧 Tool Execution Analytics'
          }
          name: 'tools-header'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: '''dependencies
| where timestamp {TimeRange}
| where customDimensions['gen_ai.operation.name'] == "execute_tool"
| extend
    toolName = tostring(customDimensions['gen_ai.tool.name']),
    toolA = tostring(customDimensions['tool.a']),
    toolB = tostring(customDimensions['tool.b']),
    toolResult = tostring(customDimensions['tool.result'])
| summarize 
    ExecutionCount = count(),
    AvgDuration = round(avg(duration), 2),
    SuccessRate = round(100.0 * countif(success == true) / count(), 2)
    by Tool = toolName
| order by ExecutionCount desc'''
            size: 0
            title: 'Tool Execution Summary'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            visualization: 'table'
            gridSettings: {
              formatters: [
                {
                  columnMatch: 'AvgDuration'
                  formatter: 8
                  formatOptions: {
                    palette: 'greenRed'
                  }
                  numberFormat: {
                    unit: 0
                    options: {
                      style: 'decimal'
                    }
                  }
                }
                {
                  columnMatch: 'SuccessRate'
                  formatter: 8
                  formatOptions: {
                    min: 0
                    max: 100
                    palette: 'redGreen'
                  }
                  numberFormat: {
                    unit: 1
                    options: {
                      style: 'decimal'
                    }
                  }
                }
              ]
            }
          }
          customWidth: '50'
          name: 'tool-summary'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: '''dependencies
| where timestamp {TimeRange}
| where customDimensions['gen_ai.operation.name'] == "execute_tool"
| extend
    toolName = tostring(customDimensions['gen_ai.tool.name'])
| summarize ExecutionCount = count() by Tool = toolName, bin(timestamp, 1h)
| order by timestamp desc'''
            size: 0
            title: 'Tool Executions Over Time'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            visualization: 'barchart'
          }
          customWidth: '50'
          name: 'tool-executions-chart'
        }

        // Section: Performance Breakdown
        {
          type: 1
          content: {
            json: '## ⚡ Performance Breakdown'
          }
          name: 'performance-header'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: '''dependencies
| where timestamp {TimeRange}
| where isnotempty(customDimensions['gen_ai.operation.name'])
| extend
    operation = tostring(customDimensions['gen_ai.operation.name'])
| summarize 
    Count = count(),
    AvgDuration = round(avg(duration), 0),
    P50Duration = round(percentile(duration, 50), 0),
    P95Duration = round(percentile(duration, 95), 0),
    P99Duration = round(percentile(duration, 99), 0)
    by Operation = operation
| order by AvgDuration desc'''
            size: 0
            title: 'Operation Performance Metrics'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            visualization: 'table'
          }
          name: 'performance-breakdown'
        }

        // Section: Conversation Trace Explorer
        {
          type: 1
          content: {
            json: '## 🔍 Conversation Trace Explorer\n\nEnter an Operation ID to view the complete span tree for a conversation.'
          }
          name: 'trace-explorer-header'
        }
        {
          type: 9
          content: {
            version: 'KqlParameterItem/1.0'
            parameters: [
              {
                id: 'operation-id-param'
                version: 'KqlParameterItem/1.0'
                name: 'OperationId'
                type: 1
                value: ''
                label: 'Operation ID'
                timeContext: {
                  durationMs: 0
                }
              }
            ]
            style: 'pills'
            queryType: 0
            resourceType: 'microsoft.insights/components'
          }
          name: 'trace-params'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: '''dependencies
| where operation_Id == "{OperationId}"
| project 
    Timestamp = timestamp,
    Name = name,
    ["Duration (ms)"] = duration,
    Status = iff(success == true, "✅ Success", "❌ Failed"),
    ["Span ID"] = substring(id, 0, 16),
    ["Parent Span ID"] = substring(operation_ParentId, 0, 16),
    Operation = tostring(customDimensions['gen_ai.operation.name']),
    Model = tostring(customDimensions['gen_ai.request.model']),
    ["Input Tokens"] = toint(customDimensions['gen_ai.usage.input_tokens']),
    ["Output Tokens"] = toint(customDimensions['gen_ai.usage.output_tokens']),
    ["Finish Reason"] = tostring(customDimensions['gen_ai.response.finish_reasons']),
    Tool = tostring(customDimensions['gen_ai.tool.name'])
| order by Timestamp asc'''
            size: 0
            title: 'Complete Span Tree'
            noDataMessage: 'Enter an Operation ID to view the trace'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            visualization: 'table'
          }
          conditionalVisibility: {
            parameterName: 'OperationId'
            comparison: 'isNotEqualTo'
          }
          name: 'trace-details'
        }

        // Section: Errors and Failures
        {
          type: 1
          content: {
            json: '## ⚠️ Errors and Failures'
          }
          name: 'errors-header'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: '''requests
| where timestamp {TimeRange}
| extend
    foundryAgentName = coalesce(
        tostring(customDimensions['gen_ai.agent.name']),
        tostring(customDimensions['azure.ai.agentserver.agent_name'])
    )
| where foundryAgentName == "{AgentName}"
| where success == false
| project 
    Timestamp = timestamp,
    ["Operation ID"] = operation_Id,
    ["Result Code"] = resultCode,
    Duration = duration,
    Name = name
| order by Timestamp desc
| take 20'''
            size: 0
            title: 'Failed Conversations'
            noDataMessage: 'No failures found in the selected time range ✅'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            visualization: 'table'
          }
          customWidth: '50'
          name: 'failed-requests'
        }
        {
          type: 3
          content: {
            version: 'KqlItem/1.0'
            query: '''exceptions
| where timestamp {TimeRange}
| where cloud_RoleName contains "agent" or customDimensions contains "agent"
| project 
    Timestamp = timestamp,
    Type = type,
    Message = outerMessage,
    ["Innermost Message"] = innermostMessage,
    ["Problem ID"] = problemId
| order by Timestamp desc
| take 20'''
            size: 0
            title: 'Exceptions'
            noDataMessage: 'No exceptions found in the selected time range ✅'
            queryType: 0
            resourceType: 'microsoft.insights/components'
            visualization: 'table'
          }
          customWidth: '50'
          name: 'exceptions'
        }
      ]
      fallbackResourceIds: [
        applicationInsightsId
      ]
      fromTemplateId: 'community-Workbooks/Azure Monitor - Agents/AI Agent Monitoring'
      '$schema': 'https://github.com/Microsoft/Application-Insights-Workbooks/blob/master/schema/workbook.json'
    })
    version: '1.0'
    sourceId: applicationInsightsId
    category: 'AI + Machine Learning'
  }
}

output workbookId string = workbook.id
output workbookName string = workbook.name
