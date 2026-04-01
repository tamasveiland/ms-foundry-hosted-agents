# Microsoft Foundry Hosted Agents

This project provides a starter template for deploying AI agents to Microsoft AI Foundry using Azure infrastructure. It includes pre-configured Azure resources optimized for hosting intelligent agents.

## Prerequisites

Before setting up this project, ensure you have the following tools installed:

1. **Azure CLI** - For Azure authentication and resource management
   ```bash
   winget install Microsoft.AzureCLI
   ```

2. **Azure Developer CLI (azd)** - For deploying the infrastructure
   ```bash
   winget install Microsoft.Azd
   ```

3. **Azure AI Agents Extension** (required for this template)
   ```bash
   azd extension add azure.ai.agents --prerelease
   ```

4. **Docker Desktop** - Required for containerized agent deployment
   ```bash
   winget install Docker.DockerDesktop
   ```

## Initial Azure Environment Setup

### Step 1: Azure Authentication

1. **Log in to Azure CLI:**
   ```bash
   az login
   ```

2. **Set your default subscription** (if you have multiple):
   ```bash
   az account set --subscription "Your Subscription Name or ID"
   ```

3. **Verify your login:**
   ```bash
   az account show
   ```

### Step 2: Choose Azure Region

This template supports specific regions where AI Foundry services are available. Choose one of the following supported regions:

- **Americas:** `eastus`, `eastus2`, `northcentralus`, `southcentralus`, `westus`, `westus2`, `westus3`, `canadacentral`, `canadaeast`, `brazilsouth`
- **Europe:** `francecentral`, `germanywestcentral`, `norwayeast`, `polandcentral`, `spaincentral`, `swedencentral`, `switzerlandnorth`, `uksouth`, `italynorth`
- **Asia Pacific:** `australiaeast`, `japaneast`, `koreacentral`, `southeastasia`, `southindia`
- **Other:** `southafricanorth`, `uaenorth`

### Step 3: Initialize Azure Developer Environment

1. **Initialize the azd environment:**
   ```bash
   azd init
   ```

2. **Set required environment variables:**
   ```bash
   azd env set AZURE_LOCATION "your-chosen-region"
   azd env set AZURE_AI_DEPLOYMENTS_LOCATION "your-chosen-region"
   ```

3. **Configure your environment name and resource group:**
   ```bash
   azd env set AZURE_ENV_NAME "your-environment-name"
   azd env set AZURE_RESOURCE_GROUP "rg-your-environment-name"
   ```

### Step 4: Deploy Azure Infrastructure

1. **Provision and deploy all Azure resources:**
   ```bash
   azd up
   ```
   
   This command will:
   - Create a new resource group
   - Deploy AI Foundry hub and project
   - Set up Azure Container Registry (ACR)
   - Configure Application Insights for monitoring
   - Create necessary storage accounts
   - Set up proper RBAC permissions

2. **Follow the interactive prompts to:**
   - Confirm your subscription
   - Choose your target region
   - Provide any additional configuration

## What Gets Created

After running `azd up`, the following Azure resources will be created:

- **AI Foundry Hub** - Central hub for AI resources and governance
- **AI Foundry Project** - Project workspace for your agents
- **Azure Container Registry** - For storing container images
- **Application Insights** - For monitoring and telemetry
- **Log Analytics Workspace** - For centralized logging
- **Storage Account** - For data and model storage
- **Managed Identity** - For secure resource access

## Customizing Model Deployments

By default, this template **does not deploy any models automatically**. You need to explicitly configure model deployments before running `azd up` by setting the `AI_PROJECT_DEPLOYMENTS` environment variable.

### Adding Model Deployments

**Option 1: Using azd env set command:**
```bash
azd env set AI_PROJECT_DEPLOYMENTS '[{"name":"gpt-54-mini","model":{"name":"gpt-5.4-mini","format":"OpenAI","version":"2026-03-17"},"sku":{"name":"GlobalStandard","capacity":50}}]'
```

**Option 2: Direct .env file editing:**
Add this line to your `.azure/{env-name}/.env` file:
```
AI_PROJECT_DEPLOYMENTS="[{\\\"name\\\":\\\"gpt-54-mini\\\",\\\"model\\\":{\\\"name\\\":\\\"gpt-5.4-mini\\\",\\\"format\\\":\\\"OpenAI\\\",\\\"version\\\":\\\"2026-03-17\\\"},\\\"sku\\\":{\\\"name\\\":\\\"GlobalStandard\\\",\\\"capacity\\\":50}}]"
```

### Additional Examples

**Deploy multiple models (using azd env set):**
```bash
azd env set AI_PROJECT_DEPLOYMENTS '[
  {
    "name":"gpt-54-mini",
    "model":{"name":"gpt-5.4-mini","format":"OpenAI","version":"2026-03-17"},
    "sku":{"name":"GlobalStandard","capacity":50}
  },
  {
    "name":"gpt-4o",
    "model":{"name":"gpt-4o","format":"OpenAI","version":"2024-05-13"},
    "sku":{"name":"GlobalStandard","capacity":30}
  }
]'
```

**Use different SKU types:**
```bash
azd env set AI_PROJECT_DEPLOYMENTS '[{"name":"gpt-54-mini","model":{"name":"gpt-5.4-mini","format":"OpenAI","version":"2026-03-17"},"sku":{"name":"Standard","capacity":20}}]'
```

### Available SKU Types
- **GlobalStandard** - Recommended for most scenarios, provides global load balancing
- **Standard** - Region-specific deployment for lower latency requirements

> **Note:** Model availability and capacity limits vary by region. Ensure your chosen models are available in your selected Azure region.

## Hosted Agents Configuration

This template is pre-configured to support **hosted agents**, which allows you to deploy containerized AI agents to Azure. By default, hosted agents are **enabled** (`ENABLE_HOSTED_AGENTS=true`), which automatically provisions:

- **Azure Container Registry (ACR)** - For storing your agent container images
- **Proper RBAC permissions** - For pushing/pulling container images
- **AI Foundry connections** - To link ACR with your AI project

### Disabling Hosted Agents

If you only plan to use prompt-based agents (no containers), you can disable hosted agents:

```bash
azd env set ENABLE_HOSTED_AGENTS false
```

This will skip ACR creation and reduce costs, but you won't be able to deploy containerized agents.

### Using Existing Container Registry

If you already have an Azure Container Registry, you can use it instead of creating a new one:

```bash
azd env set AZURE_CONTAINER_REGISTRY_RESOURCE_ID "/subscriptions/your-sub-id/resourceGroups/your-rg/providers/Microsoft.ContainerRegistry/registries/your-acr"
azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT "your-acr.azurecr.io"
```

## Next Steps

Once your Azure environment is set up:

1. **Verify deployment:** Check Azure portal to ensure all resources are created
2. **Configure agent development:** Set up your local development environment for building agents
3. **Deploy your first agent:** Use the Microsoft Agent Framework or LangGraph to create and deploy agents
4. **Monitor and evaluate:** Use the built-in monitoring and evaluation tools

## Troubleshooting

- **Permission Issues:** Ensure your account has Contributor access to the subscription
- **Region Availability:** If deployment fails, try a different supported region
- **Quota Limits:** Check Azure quotas if you encounter capacity issues
- **Extension Issues:** Ensure the Azure AI Agents extension is installed: `azd extension list`
- **JSON Parsing Error:** If you get "invalid character 'n' after object key:value pair" when running `azd provision`, it's likely due to complex JSON in environment variables. Reset the deployments variable:
  ```bash
  azd env set AI_PROJECT_DEPLOYMENTS "[]"
  ```
  Then set your model deployments using simple JSON as shown in the examples above.

## Clean Up Resources

To avoid ongoing charges, clean up resources when done:

```bash
azd down --purge
```

## Additional Resources

- [Microsoft AI Foundry Documentation](https://learn.microsoft.com/azure/ai-foundry/)
- [Azure Developer CLI Documentation](https://learn.microsoft.com/azure/developer/azure-developer-cli/)
- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)