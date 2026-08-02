# Agentic Employee-Data Import Agent

An autonomous AI agent that takes **one plain-English instruction** — like
*"Create an employee CSV and import it into Excel and Google Sheets"* — and
figures out on its own which tools to run, in what order, to get it done.
No fixed script. The LLM decides.

This README is written so someone setting this up for the **first time**
can follow it top to bottom without getting stuck.

---

## Table of contents

1. [What this project actually does](#what-this-project-actually-does)
2. [How it works (architecture)](#how-it-works-architecture)
3. [Prerequisites](#prerequisites)
4. [Step-by-step setup](#step-by-step-setup)
5. [Running the agent from the terminal](#running-the-agent-from-the-terminal)
6. [Running it as a web API](#running-it-as-a-web-api)
7. [Testing it (browser / docs UI / GET method)](#testing-it-browser--docs-ui--get-method)
8. [Expected outcome](#expected-outcome)
9. [Running the automated tests](#running-the-automated-tests)
10. [Project structure](#project-structure)
11. [Troubleshooting](#troubleshooting)
12. [Docker (optional)](#docker-optional)
13. [Why this counts as an "agent" and not just a script](#why-this-counts-as-an-agent-and-not-just-a-script)

---

## What this project actually does

You give it one sentence, for example:

> "Create an employee CSV and import it into Excel and Google Sheets."

And the agent, on its own:

1. Generates a realistic sample employee CSV (20+ rows — ID, Name, Department, Email, Salary)
2. Opens Microsoft Excel and imports the CSV into it
3. Saves the Excel workbook
4. Creates a new Google Sheet via the Google Sheets API and imports the same data
5. Double-checks both files actually contain the right data
6. Reports success/failure for every step, in plain English

You don't tell it to do each of those steps — you give it the one sentence
above, and it plans and executes the rest by itself using tool-calling.

---

## How it works (architecture)

```
                ┌─────────────────────────┐
   instruction  │                         │
 ───────────────▶     agent node (LLM)    │◀────────────┐
                │  Claude/GPT + tool-call  │              │
                └────────────┬────────────┘              │
                             │ tool_calls?                │ tool results
                             ▼                            │
                     ┌───────────────┐            ┌───────┴────────┐
                     │ tools_condition│───tools───▶│   tool node    │
                     └───────┬───────┘            └────────────────┘
                             │ no more calls
                             ▼
                        final report
```

The LLM is given four tools and a description of the goal. It decides
itself which tools to call and in what order (built with **LangGraph**).

| Tool | What it does |
|---|---|
| `generate_employee_csv` | Generates ≥20 rows of realistic sample employee data |
| `import_csv_to_excel` | Opens Excel (or falls back to `openpyxl` if Excel isn't installed), imports the CSV, saves `.xlsx` |
| `import_csv_to_google_sheets` | Authenticates with the Google Sheets API, creates a sheet, uploads the data |
| `verify_imports` | Re-reads the saved `.xlsx` and the live Google Sheet to confirm the data is really there |

Every tool automatically retries on failure, logs what it's doing, and
returns a clear success/failure result instead of silently assuming
everything worked.

---

## Prerequisites

You need these installed **before** you start. If you're not sure whether
you have them, the check commands will tell you.

| Requirement | Check if you have it | Get it if you don't |
|---|---|---|
| Python 3.10+ | `python --version` (or `python3 --version`) | [python.org/downloads](https://www.python.org/downloads/) |
| pip (comes with Python) | `pip --version` | comes bundled with Python |
| Git (optional, only if cloning) | `git --version` | [git-scm.com](https://git-scm.com/downloads) |
| A Groq API key | — | [console.groq.com](https://console.groq.com/) → API Keys |
| A Google account (for Sheets) | — | any Gmail account works |
| Microsoft Excel (optional) | — | Only needed on **Windows** if you want the agent to literally open the Excel app. If you don't have it, the agent still works — it just saves an equivalent `.xlsx` file directly instead of driving the Excel app. |

You do **not** need Excel, and you do **not** need Windows, for this
project to run correctly — that's covered in the [Troubleshooting](#troubleshooting)
section.

---

## Step-by-step setup

### Step 1 — Get the project onto your machine

If you downloaded the ZIP, just unzip it. If you're cloning from a repo:

```bash
git clone <this-repo>
cd agentic-excel-sheets-agent
```

### Step 2 — Create a virtual environment

This keeps this project's Python packages separate from everything else
on your machine. Run this **inside** the project folder:

```bash
python -m venv venv
```

Now activate it:

- **Windows (Command Prompt):**
```bash
  venv\Scripts\activate
```
- **Windows (PowerShell):**
```bash
  venv\Scripts\Activate.ps1
```
- **Mac / Linux:**
```bash
  source venv/bin/activate
```

You'll know it worked because your terminal prompt will now start with
`(venv)`.

> You need to activate this every time you open a new terminal to work on
> this project.

### Step 3 — Install the required packages

```bash
pip install -r requirements.txt
```

This installs LangGraph, LangChain, GROQ, FastAPI, Faker,
openpyxl, gspread, and everything else the project needs. It may take a
minute or two.

### Step 4 — Set up your Anthropic API key

1. Copy the example environment file:
```bash
   # Mac/Linux
   cp .env.example .env
   # Windows
   copy .env.example .env
```
2. Go to [console.groq.com](https://console.groq.com/) → **API Keys** → create a new API key.
3. Open the new `.env` file in any text editor and paste your key in:
```
   GROQ_API_KEY=sk-ant-your-actual-key-here
```
4. Save the file.

That's it for the LLM side.

### Step 5 — Set up Google Sheets API access

This is the part beginners usually find unfamiliar, so it's spelled out
in full:

1. Go to [console.cloud.google.com](https://console.cloud.google.com/) and sign in with your Google account.
2. At the top, click the project dropdown → **New Project** → give it any name (e.g. "employee-agent") → **Create**.
3. Make sure your new project is selected (check the dropdown at the top again).
4. In the search bar at the top, type **"Google Sheets API"** → click it → click **Enable**.
5. Go back to the search bar, type **"Google Drive API"** → click it → click **Enable**.
   (Both are needed — Sheets to write data, Drive to create the file.)
6. In the left sidebar, go to **APIs & Services → Credentials**.
7. Click **Create Credentials → Service Account**.
8. Give it any name (e.g. "employee-agent-bot") → **Create and Continue** → you can skip the optional role/permission steps → **Done**.
9. You'll now see your new service account in the list. Click on it.
10. Go to the **Keys** tab → **Add Key → Create new key → JSON** → **Create**.
    This downloads a `.json` file to your computer — this is your credential file.
11. Rename that downloaded file to `service_account.json` and move it into
    the root of this project folder (same folder as `agent.py`).
12. **Important:** open that JSON file and copy the email address next to
    `"client_email"` (it looks like `something@your-project.iam.gserviceaccount.com`).
    This is a robot account, not your own Google account — sheets it
    creates won't show up in *your* Google Drive unless you share them
    with yourself, which is what the next step does.
13. Open `.env` again and add your own Gmail so every sheet the agent
    creates gets automatically shared with you:
```
    GOOGLE_SHARE_WITH_EMAIL=your.email@gmail.com
```

You're done with setup. Every Google Sheet the agent creates from now on
will show up in your own Google Drive (usually under "Shared with me").

---

## Running the agent from the terminal

The simplest way to try it:

```bash
python agent.py "Create an employee CSV and import it into Excel and Google Sheets."
```

You'll see live output as the agent decides what to do:

```
Instruction: Create an employee CSV and import it into Excel and Google Sheets.

 Agent decided to call: generate_employee_csv({"num_rows": 25})
  → Generating 25 rows of sample employee data...
  → CSV written to data/employees.csv (25 rows)
 Tool result [generate_employee_csv]: {'success': True, ...}

Agent decided to call: import_csv_to_excel({"csv_path": "data/employees.csv"})
  → Saved workbook to data/employees.xlsx
 Tool result [import_csv_to_excel]: {'success': True, ...}

 Agent decided to call: import_csv_to_google_sheets({"csv_path": "data/employees.csv"})
  → Google Sheet ready: https://docs.google.com/spreadsheets/d/...
 Tool result [import_csv_to_google_sheets]: {'success': True, ...}

 Agent decided to call: verify_imports({...})
  → Verification complete — overall success: True

FINAL REPORT
------------------------------------------------------------
 Generated 25 sample employee rows (data/employees.csv)
 Excel: saved to data/employees.xlsx
 Google Sheets: https://docs.google.com/spreadsheets/d/...
 Verification: both targets confirmed 25/25 rows matched.
```

If you run it with no arguments at all, it defaults to the exact prompt
above:

```bash
python agent.py
```

You can also give it different instructions — the agent adapts:

```bash
python agent.py "Just generate 30 employees and push them to Google Sheets, skip Excel."
```

---

## Running it as a web API

Instead of the terminal, you can run the agent as a small web server and
send it requests. This is useful if you want to trigger it from a browser,
Postman, or another program.

Start the server:

```bash
uvicorn api:app --reload --port 8000
```

You'll see something like:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Leave this terminal window running — open a **new** terminal (or your
browser) to actually send it requests, covered next.

---

## Testing it (browser / docs UI / GET method)

Once the server above is running, there are three ways to test it,
ordered from easiest to most advanced.

### Option A — Just use your browser (GET method)

This is the simplest possible way to test the whole agent — no tools, no
extra software, just your normal web browser.

1. Open your browser.
2. Paste this into the address bar and press Enter:
```
   http://localhost:8000/run?instruction=Create an employee CSV and import it into Excel and Google Sheets.
```
3. Wait a few seconds (it's actually running the whole workflow — generating
   the CSV, saving the Excel file, calling the real Google Sheets API).
4. Your browser will display the raw JSON response with every step and
   the final report.

To try a different instruction, just edit the text after `instruction=`
in the URL and hit Enter again. That's the entire test loop — edit URL,
press Enter, read the result.

### Option B — Use the FastAPI docs page (recommended for demos)

FastAPI automatically builds an interactive test page for you.

1. With the server running, open:
```
   http://localhost:8000/docs
```
2. You'll see a list of endpoints: `GET /run`, `POST /run`, `POST /run/stream`, `GET /health`.
3. Click on **`GET /run`** to expand it.
4. Click the **"Try it out"** button.
5. In the `instruction` box, type or edit your instruction.
6. Click the blue **"Execute"** button.
7. Scroll down — you'll see the live response, the exact `curl` command
   that was run, and the response status code, all on one page.

This is the best option to screen-record for your demo video, since it
visibly shows the request being built and the response coming back.

### Option C — curl from the terminal

If you're comfortable with the terminal:

```bash
# GET (simplest — everything is in the URL)
curl "http://localhost:8000/run?instruction=Create%20an%20employee%20CSV%20and%20import%20it%20into%20Excel%20and%20Google%20Sheets."

# POST (JSON body instead of a URL)
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"instruction": "Create an employee CSV and import it into Excel and Google Sheets."}'

# Streaming (watch each step arrive live instead of waiting for the whole thing)
curl -N -X POST http://localhost:8000/run/stream \
  -H "Content-Type: application/json" \
  -d '{"instruction": "Create an employee CSV and import it into Excel and Google Sheets."}'
```

> Note on the GET URL: spaces need to become `%20` in a raw URL. Your
> browser does this automatically when you paste a normal sentence in
> the address bar, but `curl` needs it typed out, as shown above.

---

## Expected outcome

When given the prompt:

> **"Create an employee CSV and import it into Excel and Google Sheets."**

The agent will:

- Generate the CSV.
- Open Excel.
- Import the data.
- Save the workbook.
- Upload the data to Google Sheets.
- Report completion of each step — without you doing anything else after
  issuing that one instruction.

You can verify each part happened for real, not just that the agent
*said* it did:

- **CSV** — open `data/employees.csv` in any text editor or Excel; you'll see 20+ realistic rows.
- **Excel** — open `data/employees.xlsx`; the same data will be there, formatted with a bold header row.
- **Google Sheets** — the final report (and the JSON response, under `spreadsheet_url`) contains a real, clickable link to a Google Sheet in your own Drive with the same data.
- **Verification** — the agent's own `verify_imports` step re-opens both files and re-counts the rows, rather than just trusting that the earlier steps worked — that result is included in the final report too.

---

## Running the automated tests

The project includes unit tests that don't need any API keys or Excel
installed, so they run the same way on any machine:

```bash
pytest tests/ -v
```

Expected output:

```
tests/test_tools.py::test_generate_employee_csv_creates_at_least_20_rows PASSED
tests/test_tools.py::test_generate_employee_csv_enforces_minimum_20_rows PASSED
tests/test_tools.py::test_import_csv_to_excel_uses_openpyxl_fallback_when_com_unavailable PASSED
tests/test_tools.py::test_import_csv_to_excel_missing_source_fails_gracefully PASSED
tests/test_tools.py::test_verify_imports_matches_row_counts PASSED
```

---

## Project structure

```
agentic-excel-sheets-agent/
├── agent.py              # The LangGraph agent (the "brain") + CLI entrypoint
├── api.py                # FastAPI web server wrapping the same agent
├── config.py              # All settings (API keys, file paths, retry counts) — from .env
├── tools/
│   ├── common.py          # Shared retry decorator + logging
│   ├── csv_tool.py        # generate_employee_csv
│   ├── excel_tool.py      # import_csv_to_excel
│   ├── gsheets_tool.py    # import_csv_to_google_sheets
│   └── verify_tool.py     # verify_imports
├── tests/
│   └── test_tools.py      # Unit tests (no credentials needed)
├── data/                   # Generated CSV/XLSX files land here
├── logs/                   # agent.log — full structured run history
├── requirements.txt
├── .env.example            # Copy to .env and fill in your keys
├── Dockerfile
└── README.md                # This file
```

---

## Troubleshooting

**"ModuleNotFoundError" when running `python agent.py`**
Your virtual environment probably isn't activated, or `pip install -r requirements.txt` hasn't finished. Re-run Step 2 and Step 3 above.

**"Google auth failed" / can't find `service_account.json`**
Double-check the file is named exactly `service_account.json` and sits in
the same folder as `agent.py` (the project root), not inside `tools/`.

**I don't have Excel / I'm on Mac or Linux**
That's fine — the agent detects this automatically and saves an
equivalent `.xlsx` file using `openpyxl` instead of driving the Excel
app. You'll see `"method": "openpyxl_fallback"` in the tool result, and
the file will still open perfectly in Excel later if you copy it to a
Windows machine.

**The Google Sheet was created but I can't find it in my Drive**
Make sure `GOOGLE_SHARE_WITH_EMAIL` in your `.env` is set to your real
Gmail address — the sheet is created by a robot account and only becomes
visible to you once it's shared. Check "Shared with me" in Google Drive.

**Nothing happens / the terminal just hangs**
The agent is waiting on the Anthropic API or the Google Sheets API — this
usually takes 5–15 seconds total, it's not actually stuck. If it takes
much longer, check your internet connection and that `ANTHROPIC_API_KEY`
in `.env` is a real, valid key.

**`curl` command doesn't work on Windows Command Prompt**
Use PowerShell instead, or just use the browser method (Option A above) —
it's the easiest either way.

---

## Docker (optional)

```bash
docker build -t employee-agent .
docker run --rm -v $(pwd)/data:/app/data -v $(pwd)/service_account.json:/app/service_account.json --env-file .env employee-agent "Create an employee CSV and import it into Excel and Google Sheets."
```

To run the web API instead of the one-shot CLI:

```bash
docker run --rm -p 8000:8000 -v $(pwd)/data:/app/data --env-file .env \
  --entrypoint uvicorn employee-agent api:app --host 0.0.0.0 --port 8000
```

Note: inside the Linux container, Excel COM automation is unavailable by
definition (Excel doesn't run on Linux), so the Excel step always uses
the `openpyxl` fallback — Google Sheets import still runs for real via
the API.

---

## Why this counts as an "agent" and not just a script

- **Dynamic tool selection**: the LLM is given all four tools and decides
  itself which to call and in what order, based on the instruction —
  nothing is hardcoded as a fixed sequence of function calls.
- **Multi-step planning**: the system prompt sets the dependency chain
  (CSV → Excel/Sheets → verify), but the model still reasons about
  threading arguments (`csv_path`, `xlsx_path`, `spreadsheet_id`) between
  steps itself.
- **Robust integrations**: real Excel COM automation on Windows, a real
  Google Sheets API integration — with an environment-aware fallback
  instead of a crash when Excel isn't installed.
- **Error handling & retries**: every tool returns a clear
  success/failure result and automatically retries transient failures.
- **Structured logging & progress updates**: every run is logged to
  `logs/agent.log`, plus live progress printed as it works.
- **Configurable**: models, retry counts, row counts, and file paths are
  all driven by `.env`/`config.py`, not hardcoded in the tools.
- **Multiple interfaces**: CLI, a synchronous HTTP API, a GET-based
  browser-testable endpoint, and a live-streaming endpoint — all sharing
  one underlying implementation.

## Example prompts to use in your demo video

1. `"Create an employee CSV and import it into Excel and Google Sheets."`
2. `"Generate 30 employees and just push them to Google Sheets, skip Excel."`
3. `"Do the full employee data workflow and make sure to verify both imports worked."`