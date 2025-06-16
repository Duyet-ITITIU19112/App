from io import BytesIO
from docx import Document

def parse_stream(filename: str, content: bytes) -> str:
    if filename.lower().endswith(".txt"):
        return content.decode("utf-8", errors="ignore")

    elif filename.lower().endswith(".docx"):
        try:
            doc = Document(io.BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            raise ValueError(f"Failed to parse .docx: {e}")

    else:
        raise ValueError("Unsupported file type")
