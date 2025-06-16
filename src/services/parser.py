from io import BytesIO
from docx import Document

def parse_stream(filename: str, file_bytes: bytes) -> str:
    """
    Parses .txt or .docx content into plain text.
    """
    if filename.lower().endswith(".txt"):
        return file_bytes.decode("utf-8", errors="ignore")
    elif filename.lower().endswith(".docx"):
        try:
            doc = Document(BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            return f"[Error reading .docx]: {e}"
    else:
        return ""
