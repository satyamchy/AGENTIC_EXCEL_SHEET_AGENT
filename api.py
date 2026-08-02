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
