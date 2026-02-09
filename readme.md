Steps to run the server  

Step 1: source venv/bin/activate
Step 2: uvicorn main_9feb:app --host 0.0.0.0 --port 8000

<!--  This code implements a FastAPI application that provides an OCR service using the Mistral API.
It allows users to upload PDF files, processes them with OCR, and returns the extracted text in HTML format. 
The application includes two main endpoints: one for uploading PDFs and another for retrieving the OCR results.
Then the OCR results are converted from Markdown to HTML . -->

<!-- post request Api : "http://192.168.0.113:8000/ocr" -->