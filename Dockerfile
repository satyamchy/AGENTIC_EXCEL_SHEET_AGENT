# Note: Excel COM automation only works on Windows, so inside this Linux
# container the agent automatically runs the openpyxl fallback path for
# Excel while Google Sheets import runs for real via the API. This is
# expected and is called out in the README.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENTRYPOINT ["python", "agent.py"]
CMD ["Create a sample employee CSV and import it into Excel and Google Sheets."]
