import os
import logging

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import (
    END,
    START,
    MessagesState,
    StateGraph,
)
from typing_extensions import Literal
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from azure.ai.agentserver.langgraph import from_langgraph

# OpenTelemetry tracing configuration
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)

# Configure Azure Monitor OpenTelemetry
connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if connection_string:
    configure_azure_monitor(
        connection_string=connection_string,
        logger_name=__name__,
    )
    logger.info("Azure Monitor OpenTelemetry configured successfully")
else:
    logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING not set, tracing disabled")

# Get tracer for instrumenting custom operations
tracer = trace.get_tracer(__name__)


# Define tools with tracing
@tool
def multiply(a: int, b: int) -> int:
    """Multiply a and b.

    Args:
        a: first int
        b: second int
    """
    with tracer.start_as_current_span("tool.multiply") as span:
        span.set_attribute("gen_ai.tool.name", "multiply")
        span.set_attribute("tool.a", a)
        span.set_attribute("tool.b", b)
        result = a * b
        span.set_attribute("tool.result", result)
        span.set_status(Status(StatusCode.OK))
        return result


@tool
def add(a: int, b: int) -> int:
    """Adds a and b.

    Args:
        a: first int
        b: second int
    """
    with tracer.start_as_current_span("tool.add") as span:
        span.set_attribute("gen_ai.tool.name", "add")
        span.set_attribute("tool.a", a)
        span.set_attribute("tool.b", b)
        result = a + b
        span.set_attribute("tool.result", result)
        span.set_status(Status(StatusCode.OK))
        return result


@tool
def divide(a: int, b: int) -> float:
    """Divide a and b.

    Args:
        a: first int
        b: second int
    """
    with tracer.start_as_current_span("tool.divide") as span:
        span.set_attribute("gen_ai.tool.name", "divide")
        span.set_attribute("tool.a", a)
        span.set_attribute("tool.b", b)
        try:
            result = a / b
            span.set_attribute("tool.result", result)
            span.set_status(Status(StatusCode.OK))
            return result
        except ZeroDivisionError as e:
            span.set_status(Status(StatusCode.ERROR, "Division by zero"))
            span.record_exception(e)
            raise


# Augment the LLM with tools
tools = [add, multiply, divide]
tools_by_name = {tool.name: tool for tool in tools}
_llm_with_tools = None

def llm():
    try:
        deployment_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_version = os.getenv("OPENAI_API_VERSION", "2024-06-01")
        
        print(f"[DEBUG] Initializing LLM:")
        print(f"[DEBUG]   Deployment: {deployment_name}")
        print(f"[DEBUG]   Endpoint: {azure_endpoint}")
        print(f"[DEBUG]   API Version: {api_version}")
        
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        
        llm = AzureChatOpenAI(
            azure_deployment=deployment_name,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
            azure_ad_token_provider=token_provider,
        )
        print("[DEBUG] LLM initialized successfully")
        return llm
    except Exception as e:
        print(f"[DEBUG] Error initializing LLM: {e}")
        logger.exception("Failed to initialize client of large language model")
        raise

def llm_with_tools():
    global _llm_with_tools
    if _llm_with_tools is None:
        _llm_with_tools = llm().bind_tools(tools)
    return _llm_with_tools

# Nodes
def llm_call(state: MessagesState):
    """LLM decides whether to call a tool or not"""
    with tracer.start_as_current_span("agent.llm_call") as span:
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("agent.node", "llm_call")
        
        try:
            response = llm_with_tools().invoke(
                [
                    SystemMessage(
                        content="You are a helpful assistant tasked with performing arithmetic on a set of inputs."
                    )
                ]
                + state["messages"]
            )
            
            # Track token usage if available
            if hasattr(response, "response_metadata"):
                metadata = response.response_metadata
                if "token_usage" in metadata:
                    token_usage = metadata["token_usage"]
                    span.set_attribute("gen_ai.usage.input_tokens", token_usage.get("prompt_tokens", 0))
                    span.set_attribute("gen_ai.usage.output_tokens", token_usage.get("completion_tokens", 0))
            
            span.set_status(Status(StatusCode.OK))
            return {"messages": [response]}
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


def tool_node(state: dict):
    """Performs the tool call"""
    with tracer.start_as_current_span("agent.tool_execution") as span:
        span.set_attribute("agent.node", "environment")
        
        result = []
        tool_calls = state["messages"][-1].tool_calls
        span.set_attribute("tool.call_count", len(tool_calls))
        
        for i, tool_call in enumerate(tool_calls):
            tool_name = tool_call["name"]
            span.set_attribute(f"tool.{i}.name", tool_name)
            
            tool = tools_by_name[tool_name]
            observation = tool.invoke(tool_call["args"])
            result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
        
        span.set_status(Status(StatusCode.OK))
        return {"messages": result}


# Conditional edge function to route to the tool node or end based upon whether the LLM made a tool call
def should_continue(state: MessagesState) -> Literal["environment", END]:
    """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

    messages = state["messages"]
    last_message = messages[-1]
    # If the LLM makes a tool call, then perform an action
    if last_message.tool_calls:
        return "Action"
    # Otherwise, we stop (reply to the user)
    return END


# Build workflow
def build_agent() -> "StateGraph":
    agent_builder = StateGraph(MessagesState)

    # Add nodes
    agent_builder.add_node("llm_call", llm_call)
    agent_builder.add_node("environment", tool_node)

    # Add edges to connect nodes
    agent_builder.add_edge(START, "llm_call")
    agent_builder.add_conditional_edges(
        "llm_call",
        should_continue,
        {
            "Action": "environment",
            END: END,
        },
    )
    agent_builder.add_edge("environment", "llm_call")

    # Compile the agent
    return agent_builder.compile()

# Build workflow and run agent
if __name__ == "__main__":
    try:
        agent = build_agent()
        adapter = from_langgraph(agent)
        adapter.run()
    except Exception:
        logger.exception("Calculator Agent encountered an error while running")
        raise
