"""
Autonomous agent entrypoint.

Architecture
------------
This is a ReAct-style LangGraph agent, not a hardcoded script:

    START -> [planner/agent node] <-> [tool node] -> END

The LLM (Claude by default, OpenAI optional) is bound to four tools:
    generate_employee_csv, import_csv_to_excel,
    import_csv_to_google_sheets, verify_imports

Given a single natural-language instruction, the model decides *itself*
which tools to call, in what order, and with what arguments — including
threading the csv_path/xlsx_path/spreadsheet_id returned by one tool call
into the next one. The graph loops between the agent node and the tool
node until the model responds with no further tool calls, at which point
it produces a final natural-language completion report.

Run:
    python agent.py "Create a sample employee CSV and import it into Excel and Google Sheets."
"""
import sys
import json

from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import SystemMessage, HumanMessage

import config
from tools.common import get_logger
from tools.csv_tool import generate_employee_csv
from tools.excel_tool import import_csv_to_excel
from tools.gsheets_tool import import_csv_to_google_sheets
from tools.verify_tool import verify_imports

log = get_logger("agent")

TOOLS = [generate_employee_csv, import_csv_to_excel, import_csv_to_google_sheets, verify_imports]

SYSTEM_PROMPT = """You are an autonomous workflow agent with access to four tools:

1. generate_employee_csv - creates a sample employee CSV (>=20 rows)
2. import_csv_to_excel - opens Excel, imports the CSV, saves as .xlsx
3. import_csv_to_google_sheets - creates a Google Sheet and imports the same data via the Sheets API
4. verify_imports - re-reads the Excel file and/or Google Sheet to confirm the data actually landed correctly

When the user asks you to create sample data and get it into Excel and/or
Google Sheets, plan the full sequence yourself before acting:
  1. Generate the CSV first (always the first step - every other tool needs csv_path).
  2. Import into Excel using the csv_path returned by step 1. Save the xlsx_path.
  3. Import into Google Sheets using the same csv_path. Save the spreadsheet_id.
  4. ALWAYS call verify_imports last, passing csv_path, xlsx_path and spreadsheet_id,
     so the final report is based on real re-reads, not just assuming success.

Only run the destinations the user actually asked for (e.g. skip Google Sheets
entirely if they only asked for Excel). If a tool reports success=False, do not
silently continue as if it worked — mention the failure in your final summary,
and skip verifying that specific target.

When you are done, give the user a concise final report: what was generated,
where the Excel file is, the Google Sheet URL (if created), and whether
verification confirmed both. Be explicit about success/failure per step.
"""


def _get_llm():
    return ChatGroq(model=config.GROQ_MODEL, api_key=config.require_groq_api_key(), temperature=0)



def build_graph():
    llm = _get_llm().bind_tools(TOOLS)

    def agent_node(state: MessagesState):
        messages = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        response = llm.invoke(messages)
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


def stream_agent_events(instruction: str):
    """Core generator shared by the CLI and the FastAPI wrapper.

    Yields structured dicts as the agent works, e.g.:
        {"type": "tool_call", "name": "generate_employee_csv", "args": {...}}
        {"type": "tool_result", "name": "generate_employee_csv", "result": {...}}
        {"type": "final", "content": "..."}
    This is what lets api.py expose the exact same run over HTTP (either as
    one JSON response or as a live SSE stream) without duplicating any
    agent logic.
    """
    log.info("Received instruction: %s", instruction)
    app = build_graph()

    final_state = None
    for event in app.stream(
        {"messages": [HumanMessage(content=instruction)]},
        stream_mode="values",
    ):
        final_state = event
        last = event["messages"][-1]
        if last.type == "ai" and getattr(last, "tool_calls", None):
            for tc in last.tool_calls:
                yield {"type": "tool_call", "name": tc["name"], "args": tc["args"]}
        elif last.type == "tool":
            try:
                payload = json.loads(last.content) if isinstance(last.content, str) else last.content
            except (json.JSONDecodeError, TypeError):
                payload = last.content
            yield {"type": "tool_result", "name": last.name, "result": payload}

    final_message = final_state["messages"][-1]
    yield {"type": "final", "content": final_message.content}


def run_agent(instruction: str) -> str:
    """CLI-friendly wrapper: prints events as they happen, returns final report text."""
    print(f"\nInstruction: {instruction}\n")
    final_report = ""
    for event in stream_agent_events(instruction):
        if event["type"] == "tool_call":
            print(f"\nAgent decided to call: {event['name']}({json.dumps(event['args'])})")
        elif event["type"] == "tool_result":
            print(f"Tool result [{event['name']}]: {event['result']}")
        elif event["type"] == "final":
            final_report = event["content"]
            print("\nFINAL REPORT\n" + "-" * 60)
            print(final_report)
    return final_report


if __name__ == "__main__":
    user_instruction = " ".join(sys.argv[1:]) or (
        "Create a sample employee CSV and import it into Excel and Google Sheets."
    )
    run_agent(user_instruction)
