## Testing the Agent Locally

Before deploying, verify the agent works locally.

> **Prerequisites**: 
> - **Python 3.10, 3.11, or 3.12** (Python 3.13+ is not yet supported)
> - Azure Developer CLI (`azd`)
> - Azure authentication (`azd auth login`)

### Start the agent with azd (Recommended)

The simplest way to test locally is using the Azure Developer CLI:

```bash
# From the repository root
azd ai agent run
```

This command automatically:
- Sets up the environment variables
- Installs dependencies  
- Starts the agent

### Invoke the agent

In a separate terminal, send a test message to the local agent:

```bash
azd ai agent invoke --local "What is 25 multiplied by 4?"
```

You should see a response from the agent performing the calculation.

### Common issues

If the agent fails to start, check these common issues:

| Issue | Solution |
|-------|----------|
| AuthenticationError or DefaultAzureCredential failure | Run `azd auth login` again to refresh your session. |
| ResourceNotFound | Verify your endpoint URLs match the values in the Foundry portal. |
| DeploymentNotFound | Check the deployment name in Build > Deployments. |
| Connection refused | Ensure no other process is using port 8088. |
| Package compatibility errors (e.g., Starlette) | Use `azd ai agent run` instead of running Python directly. |

## Advanced: Running Python Directly

> **Warning**: Running `python main.py` directly may encounter package compatibility issues (such as Starlette version conflicts). Using `azd ai agent run` (recommended above) avoids these issues.

If you need to run the Python script directly for debugging purposes, be aware that you'll need to manually set up the environment and may encounter dependency version conflicts. In most cases, **`azd ai agent run` is the better choice**.

## Troubleshooting

### Images built on Apple Silicon or other ARM64 machines do not work on our service

We **recommend using `azd` cloud build**, which always builds images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds**

Use this command to build the image locally:

```shell
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.
