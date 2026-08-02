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
which tools to call, in what order, and with what arguments - including
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
3. import_csv_to_google_sheets - imports the same data into the configured existing Google Sheet
4. verify_imports - re-reads the Excel file and/or Google Sheet to confirm the data actually landed correctly

When the user asks you to create sample data and get it into Excel and/or
Google Sheets, plan the full sequence yourself before acting:
  1. Generate the CSV first (always the first step - every other tool needs csv_path).
  2. Import into Excel using the csv_path returned by step 1. Save the xlsx_path.
  3. Import into the configured Google Sheet using the same csv_path. Save the spreadsheet_id.
  4. ALWAYS call verify_imports last, passing csv_path, xlsx_path and spreadsheet_id,
     so the final report is based on real re-reads, not just assuming success.

Only run the destinations the user actually asked for (e.g. skip Google Sheets
entirely if they only asked for Excel). If a tool reports success=False, do not
silently continue as if it worked - mention the failure in your final summary,
and skip verifying that specific target.

When you are done, give the user a concise final report: what was generated,
where the Excel file is, the Google Sheet URL (if created), and whether
verification confirmed both. Be explicit about success/failure per step.
"""


def _execution_facts(tool_results: list[dict]) -> str:
    facts = []
    for event in tool_results:
        result = event.get("result")
        if not isinstance(result, dict):
            continue

        name = event.get("name")
        if name == "generate_employee_csv" and result.get("csv_path"):
            facts.append(f"CSV path: {result['csv_path']}")
        elif name == "import_csv_to_excel" and result.get("xlsx_path"):
            facts.append(f"Excel workbook path: {result['xlsx_path']}")
        elif name == "import_csv_to_google_sheets":
            if result.get("spreadsheet_url"):
                facts.append(f"Google Sheet URL: {result['spreadsheet_url']}")
            if result.get("spreadsheet_link_file"):
                facts.append(f"Google Sheet link file: {result['spreadsheet_link_file']}")
            elif result.get("error"):
                facts.append(f"Google Sheets error: {result['error']}")
        elif name == "verify_imports":
            google_report = result.get("google_sheets")
            if isinstance(google_report, dict) and google_report.get("url"):
                facts.append(f"Verified Google Sheet URL: {google_report['url']}")

    if not facts:
        return ""
    return "Execution facts:\n" + "\n".join(f"- {fact}" for fact in facts)


def _get_llm():
    return ChatGroq(model=config.GROQ_MODEL, api_key=config.require_groq_api_key(), temperature=0)


def _requested_targets(instruction: str) -> dict:
    text = instruction.lower()
    wants_google = any(term in text for term in ("google sheet", "google sheets", "sheets", "spreadsheet"))
    wants_excel = any(term in text for term in ("excel", "xlsx", "workbook"))
    wants_csv = "csv" in text or "employee" in text or "sample" in text

    if not wants_excel and not wants_google and any(term in text for term in ("everywhere", "both", "all")):
        wants_excel = True
        wants_google = True

    return {
        "csv": wants_csv or wants_excel or wants_google,
        "excel": wants_excel,
        "google_sheets": wants_google,
    }


def _invoke_tool(name: str, tool_obj, args: dict):
    yield {"type": "tool_call", "name": name, "args": args}
    result = tool_obj.invoke(args)
    yield {"type": "tool_result", "name": name, "result": result}


def _build_final_report(tool_results: list[dict]) -> str:
    lines = []
    success = True

    for event in tool_results:
        name = event["name"]
        result = event["result"]
        if not isinstance(result, dict):
            continue
        if result.get("success") is False:
            success = False

        if name == "generate_employee_csv":
            if result.get("success"):
                lines.append(f"CSV generated: {result.get('csv_path')} ({result.get('rows_generated')} rows)")
            else:
                lines.append(f"CSV generation failed: {result.get('error')}")
        elif name == "import_csv_to_excel":
            if result.get("success"):
                lines.append(
                    f"Excel import completed: {result.get('xlsx_path')} "
                    f"({result.get('rows_imported')} rows, method={result.get('method')})"
                )
            else:
                lines.append(f"Excel import failed: {result.get('error')}")
        elif name == "import_csv_to_google_sheets":
            if result.get("success"):
                lines.append(f"Google Sheets import completed: {result.get('spreadsheet_url')}")
                lines.append(f"Google Sheet link saved to: {result.get('spreadsheet_link_file')}")
            else:
                lines.append(f"Google Sheets import failed: {result.get('error')}")
        elif name == "verify_imports":
            lines.append(f"Verification completed for available targets: {result.get('success')}")
            excel = result.get("excel")
            google = result.get("google_sheets")
            if isinstance(excel, dict):
                if excel.get("verified"):
                    lines.append(f"Excel verified: {excel.get('rows_found')} rows at {excel.get('path')}")
                else:
                    lines.append(f"Excel verification failed: {excel.get('error')}")
            if isinstance(google, dict):
                if google.get("verified"):
                    lines.append(f"Google Sheet verified: {google.get('rows_found')} rows at {google.get('url')}")
                else:
                    lines.append(f"Google Sheet verification failed: {google.get('error')}")

    status = "Workflow completed successfully." if success else "Workflow completed with errors."
    return status + "\n" + "\n".join(lines)


def _stream_sequential_workflow(instruction: str):
    targets = _requested_targets(instruction)
    log.info("Planned targets: %s", targets)

    tool_results = []
    csv_path = ""
    xlsx_path = ""
    spreadsheet_id = ""

    if targets["csv"]:
        args = {}
        for event in _invoke_tool("generate_employee_csv", generate_employee_csv, args):
            if event["type"] == "tool_result":
                tool_results.append(event)
                if isinstance(event["result"], dict) and event["result"].get("success"):
                    csv_path = event["result"]["csv_path"]
            yield event

    if targets["excel"] and csv_path:
        args = {"csv_path": csv_path}
        for event in _invoke_tool("import_csv_to_excel", import_csv_to_excel, args):
            if event["type"] == "tool_result":
                tool_results.append(event)
                if isinstance(event["result"], dict) and event["result"].get("success"):
                    xlsx_path = event["result"]["xlsx_path"]
            yield event

    if targets["google_sheets"] and csv_path:
        args = {"csv_path": csv_path, "sheet_title": "Employee Data"}
        for event in _invoke_tool("import_csv_to_google_sheets", import_csv_to_google_sheets, args):
            if event["type"] == "tool_result":
                tool_results.append(event)
                if isinstance(event["result"], dict) and event["result"].get("success"):
                    spreadsheet_id = event["result"]["spreadsheet_id"]
            yield event

    verify_args = {"csv_path": csv_path}
    if xlsx_path:
        verify_args["xlsx_path"] = xlsx_path
    if spreadsheet_id:
        verify_args["spreadsheet_id"] = spreadsheet_id

    if csv_path and (xlsx_path or spreadsheet_id):
        for event in _invoke_tool("verify_imports", verify_imports, verify_args):
            if event["type"] == "tool_result":
                tool_results.append(event)
            yield event

    final_report = _build_final_report(tool_results)
    facts = _execution_facts(tool_results)
    if facts:
        log.info("%s", facts.replace("\n", " | "))
        final_report = f"{final_report}\n\n{facts}"
    yield {"type": "final", "content": final_report}



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
    yield from _stream_sequential_workflow(instruction)


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
