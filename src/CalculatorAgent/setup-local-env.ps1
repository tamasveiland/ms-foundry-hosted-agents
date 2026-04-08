# Script to create .env file from azd environment for local debugging
# Run this from the CalculatorAgent directory

$ErrorActionPreference = "Stop"

Write-Host "Creating .env file from azd environment..." -ForegroundColor Cyan

# Get azd environment values
Push-Location ../..
$azdEnvOutput = azd env get-values
Pop-Location

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to get azd environment values. Make sure you're in an initialized azd environment." -ForegroundColor Red
    exit 1
}

# Parse and create .env file
$envContent = @"
# Auto-generated from azd environment on $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
# To regenerate: Run setup-local-env.ps1

# Local Development Settings
AGENT_ENVIRONMENT=local

"@

# Extract specific variables we need
foreach ($line in $azdEnvOutput -split "`n") {
    if ($line -match '^(AZURE_AI_PROJECT_ENDPOINT|AZURE_OPENAI_ENDPOINT|OPENAI_API_VERSION|AZURE_AI_MODEL_DEPLOYMENT_NAME|APPLICATIONINSIGHTS_CONNECTION_STRING)=(.*)$') {
        $key = $matches[1]
        $value = $matches[2] -replace '^"|"$', ''  # Remove quotes
        
        # Skip App Insights for local dev (we use OTLP instead)
        if ($key -eq "APPLICATIONINSIGHTS_CONNECTION_STRING") {
            $envContent += "# $key is disabled for local tracing`n"
            continue
        }
        
        $envContent += "$key=$value`n"
    }
}

# Write .env file
$envContent | Set-Content -Path ".env" -Encoding UTF8

Write-Host "✓ Created .env file successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "You can now:" -ForegroundColor Yellow
Write-Host "  1. Run the agent directly: python main.py"
Write-Host "  2. Debug in VS Code (F5)"
Write-Host "  3. Use azd ai agent run (which uses azd env automatically)"
Write-Host ""
Write-Host "Environment variables loaded:" -ForegroundColor Cyan
Get-Content .env | Where-Object { $_ -notmatch '^#' -and $_ -match '=' }
