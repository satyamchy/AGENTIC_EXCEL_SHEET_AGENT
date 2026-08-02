"""
Lightweight FastAPI wrapper around agent.run_agent / agent.stream_agent_events.

Exposes the same autonomous agent over HTTP, three ways:

  GET  /run           - simplest option. Pass the instruction as a query
                        param. Works straight from a browser URL bar or a
                        one-line curl -- easiest to debug since you can just
                        edit the URL and hit enter.

  POST /run           - same result, JSON body instead of a query param.
                        Trigger it from the FastAPI docs UI (/docs) by
                        clicking "Try it out", or from curl/another service.

  POST /run/stream    - Server-Sent Events. Get each tool_call / tool_result
                        / final event pushed live as the agent works, instead
                        of waiting for the whole thing to finish.

All three call the exact same underlying agent code (`_execute` /
`stream_agent_events`) -- nothing is duplicated between them.

Run:
    uvicorn api:app --reload --port 8000

Try it (pick whichever's easiest for you):

    # 1. Browser: just paste this into the address bar
    http://localhost:8000/run?instruction=Create a sample employee CSV and import it into Excel and Google Sheets.

    # 2. GET via curl
    curl "http://localhost:8000/run?instruction=Create%20a%20sample%20employee%20CSV%20and%20import%20it%20into%20Excel%20and%20Google%20Sheets."

    # 3. POST via curl
    curl -X POST http://localhost:8000/run \\
        -H "Content-Type: application/json" \\
        -d '{"instruction": "Create a sample employee CSV and import it into Excel and Google Sheets."}'

    # 4. Streaming
    curl -N -X POST http://localhost:8000/run/stream \\
        -H "Content-Type: application/json" \\
        -d '{"instruction": "Create a sample employee CSV and import it into Excel and Google Sheets."}'

    # 5. Or just open http://localhost:8000/docs and click "Try it out"
"""
import json
import time

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent import stream_agent_events
from tools.common import get_logger

log = get_logger("api")

DEFAULT_INSTRUCTION = "Create a sample employee CSV and import it into Excel and Google Sheets."

app = FastAPI(
    title="Employee Data Agent API",
    description="Autonomous agent: natural-language instruction in, "
    "CSV + Excel + Google Sheets workflow executed out.",
    version="1.0.0",
)


class RunRequest(BaseModel):
    instruction: str = Field(..., example=DEFAULT_INSTRUCTION)


class RunResponse(BaseModel):
    instruction: str
    steps: list[dict]
    final_report: str
    success: bool
    duration_seconds: float


def _execute(instruction: str) -> RunResponse:
    """The one place that actually runs the agent and builds a response.

    Both the POST (JSON body) and GET (query param) endpoints call this,
    so there's exactly one execution path to debug regardless of which
    way you triggered it.
    """
    log.info("Executing instruction=%r", instruction)
    start = time.time()

    steps = []
    final_report = ""
    overall_success = True

    for event in stream_agent_events(instruction):
        if event["type"] in ("tool_call", "tool_result"):
            steps.append(event)
            if event["type"] == "tool_result":
                result = event["result"]
                if isinstance(result, dict) and result.get("success") is False:
                    overall_success = False
        elif event["type"] == "final":
            final_report = event["content"]

    return RunResponse(
        instruction=instruction,
        steps=steps,
        final_report=final_report,
        success=overall_success,
        duration_seconds=round(time.time() - start, 2),
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/run", response_model=RunResponse)
def run_get(
    instruction: str = Query(
        default=DEFAULT_INSTRUCTION,
        description="Natural language instruction for the agent, passed as a query param.",
        examples=[DEFAULT_INSTRUCTION],
    )
):
    """GET version - trigger the agent straight from a browser URL bar or a
    one-line curl, no JSON body needed. Handy for quick manual debugging:

        http://localhost:8000/run?instruction=Create a sample employee CSV...

    Does the exact same work as POST /run - same function underneath.
    """
    return _execute(instruction)


@app.post("/run", response_model=RunResponse)
def run_post(req: RunRequest):
    """POST version - same as GET /run but takes a JSON body. Use this from
    the FastAPI docs UI (/docs) or from another service calling the API
    programmatically."""
    return _execute(req.instruction)


@app.post("/run/stream")
def run_stream(req: RunRequest):
    """Run the agent and stream each step live as Server-Sent Events."""
    log.info("API /run/stream instruction=%r", req.instruction)

    def event_generator():
        yield f"event: start\ndata: {json.dumps({'instruction': req.instruction})}\n\n"
        for event in stream_agent_events(req.instruction):
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
