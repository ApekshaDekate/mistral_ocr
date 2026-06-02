# This code implements a FastAPI application that provides an OCR service using the Mistral API.
# It allows users to upload PDF files, processes them with OCR, and returns the extracted text in HTML format. 
# The application includes two main endpoints: one for uploading PDFs and another for retrieving the OCR results. 
# Then the OCR results are converted from Markdown to HTML .

import json
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


# def markdown_to_html(md: str) -> str:
#     lines = md.splitlines()
#     html_blocks = []

#     para_lines = []

#     def flush_para():
#         if para_lines:
#             content = "<br>\n".join(para_lines)

#             # Preserve raw HTML tables
#             if "<table" in content:
#                 html_blocks.append(content)
#             else:
#                 html_blocks.append(f"<p>{html_lib.unescape(content)}</p>")
#             para_lines.clear()

#     for raw_line in lines:
#         line = raw_line.rstrip()

#         # # 1️⃣ Remove image placeholders
#         # line = re.sub(r"!\[.*?\]\(.*?\)", "", line)

#         # Empty line → new paragraph
#         if not line.strip():
#             flush_para()
#             continue

#         # Bold: **text**
#         line = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", line)

#         # Italic: *text*
#         line = re.sub(
#             r"\*(.+?)\*(?=[\s.,;:!?]|$|[¹²³⁴⁵⁶⁷⁸⁹⁰])",
#             r"<i>\1</i>",
#             line
#         )

#         # Headings
#         if line.startswith("#"):
#             flush_para()
#             heading = line.lstrip("#").strip()
#             html_blocks.append(f"<p><b>{html_lib.escape(heading)}</b></p>")
#             continue

#         # Page numbers alone
#         if re.fullmatch(r"\d+", line.strip()):
#             flush_para()
#             continue

#         # Bold only main point numbers like 1. 2. 10.
#         # Ignore subpoints like 1.1 or quoted subpoints

#         main_point_match = re.match(
#             r'^\s*(\d+)\.\s+(.*)',
#             line
#         )

#         if main_point_match:

#             # Ignore subpoints like 1.1
#             if not re.match(r'^\s*\d+\.\d+', line):

#                 number = main_point_match.group(1)
#                 rest = main_point_match.group(2)

#                 line = f"<b>{number}.</b> {rest}"

#         # Normal line → same paragraph
#         para_lines.append(line)

#     flush_para()
#     return "\n".join(html_blocks)
import re
import html as html_lib

def markdown_to_html(md: str) -> str:
    lines = md.splitlines()

    html_blocks = []
    para_lines = []

    # Tracks multiline quoted block
    inside_quote_block = False

    def flush_para():
        if para_lines:
            content = "<br>\n".join(para_lines)

            # Preserve raw HTML tables
            if "<table" in content:
                html_blocks.append(content)
            else:
                html_blocks.append(f"<p>{html_lib.unescape(content)}</p>")

            para_lines.clear()

    for raw_line in lines:
        line = raw_line.rstrip()

        # Empty line → new paragraph
        if not line.strip():
            flush_para()
            continue

        stripped_line = line.strip()

        # ----------------------------------------
        # CHECK IF QUOTE BLOCK STARTS
        # ----------------------------------------

        if stripped_line.startswith('"'):
            inside_quote_block = True

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
        if re.fullmatch(r"\d+", stripped_line):
            flush_para()
            continue

        # ----------------------------------------
        # MAIN POINT BOLDING
        # ONLY OUTSIDE QUOTE BLOCK
        # ----------------------------------------

        main_point_match = re.match(
            r'^\s*(\d+)\.\s+(.*)',
            line
        )

        if (
            main_point_match
            and not inside_quote_block
        ):

            # Ignore subpoints like 1.1
            if not re.match(r'^\s*\d+\.\d+', line):

                number = main_point_match.group(1)
                rest = main_point_match.group(2)

                line = f"<b>{number}.</b> {rest}"

        # Normal line → same paragraph
        para_lines.append(line)

        # ----------------------------------------
        # CHECK IF QUOTE BLOCK ENDS
        # ----------------------------------------

        if stripped_line.endswith('"'):
            inside_quote_block = False

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
            "table_format": "html",
            "include_image_base64": False,
            "confidence_scores_granularity":"page"
        }

        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(OCR_URL, headers=headers, json=payload)
        response.raise_for_status()
        # print (f"OCR API response: {response.status_code}")

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="OCR temorarily unavailable")

        data = response.json()

        with open(os.path.join(JOB_DIR, f"ocr_response_{jobId}.json"), "w") as f:
            json.dump(data, f, indent=2)


        # Build final markdown with tables injected
        all_pages_markdown = []

        for page in data.get("pages", []):

            markdown = page.get("markdown", "")

            # Create table id -> html mapping
            table_map = {
                table["id"]: table["content"]
                for table in page.get("tables", [])
            }

            # Replace markdown table placeholders with actual HTML tables
            def replace_table(match):
                table_id = match.group(1)
                return table_map.get(table_id, "")

            markdown = re.sub(
                r"\[(tbl-\d+\.html)\]\(.*?\)",
                replace_table,
                markdown
            )

            all_pages_markdown.append(markdown)

        final_markdown = "\n\n".join(all_pages_markdown)
        
        # Save final markdown for debugging
        with open(os.path.join(JOB_DIR, f"final_markdown_{jobId}.txt"), "w", encoding="utf-8") as f:
            f.write(final_markdown)
        

        html_body = markdown_to_html(final_markdown)
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
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
