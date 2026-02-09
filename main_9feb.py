# This code implements a FastAPI application that provides an OCR service using the Mistral API.
# It allows users to upload PDF files, processes them with OCR, and returns the extracted text in HTML format. 
# The application includes two main endpoints: one for uploading PDFs and another for retrieving the OCR results. 
# Then the OCR results are converted from Markdown to HTML .

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
import requests
import base64
import os
import re
import html as html_lib
from dotenv import load_dotenv
import uuid

load_dotenv()


app = FastAPI(title="Mistral OCR API")

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
OCR_URL = "https://api.mistral.ai/v1/ocr"

if not MISTRAL_API_KEY:
    raise RuntimeError("MISTRAL_API_KEY is missing from .env")

JOB_DIR = "jobs"
os.makedirs(JOB_DIR, exist_ok=True)

# ---------------- Markdown → HTML ---------------- #


def markdown_to_html(md: str) -> str:
    lines = md.splitlines()
    html_blocks = []

    para_lines = []

    def flush_para():
        if para_lines:
            content = "<br>\n".join(html_lib.unescape(l) for l in para_lines)
            html_blocks.append(f"<p>{content}</p>")
            para_lines.clear()

    for raw_line in lines:
        line = raw_line.rstrip()

        # Empty line → new paragraph
        if not line.strip():
            flush_para()
            continue

        # Bold: **text**
        line = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", line)

        # Italic: *text*
        line = re.sub(
            r"\*(.+?)\*(?=[\s.,;:!?]|$|[¹²³⁴⁵⁶⁷⁸⁹⁰])",
            r"<i>\1</i>",
            line
        )

        # Headings
        if line.startswith("#"):
            flush_para()
            heading = line.lstrip("#").strip()
            html_blocks.append(f"<p><b>{html_lib.escape(heading)}</b></p>")
            continue

        # Page numbers alone
        if re.fullmatch(r"\d+", line.strip()):
            flush_para()
            continue

        # Normal line → same paragraph
        para_lines.append(line)

    flush_para()
    return "\n".join(html_blocks)

# ---------------- Upload Endpoint ---------------- #

@app.post("/ocr/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF allowed")

    jobId = str(uuid.uuid4())
    pdf_path = os.path.join(JOB_DIR, f"{jobId}.pdf")

    with open(pdf_path, "wb") as f:
        f.write(await file.read())

    return {
        "jobId": jobId,
        "result_endpoint": f"/ocr/result/{jobId}"
    }

# ---------------- Result Endpoint ---------------- #
@app.get("/ocr/result/{jobId}", response_class=HTMLResponse)
def get_ocr_result(jobId: str):
    pdf_path = os.path.join(JOB_DIR, f"{jobId}.pdf")

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Invalid jobId")

    try:
        with open(pdf_path, "rb") as f:
            pdf_base64 = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "model": "mistral-ocr-latest",
            "document": {
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{pdf_base64}"
            },
            "include_image_base64": False
        }

        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(OCR_URL, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()

        markdown_pages = [
            p["markdown"] for p in data.get("pages", []) if p.get("markdown")
        ]

        html_body = markdown_to_html("\n\n".join(markdown_pages))

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>OCR Output</title>
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """

    finally:
        # 🔥 DELETE PDF AFTER RESPONSE IS READY
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
