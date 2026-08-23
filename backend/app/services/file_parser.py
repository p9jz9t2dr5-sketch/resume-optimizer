import os
from typing import Optional
from pypdf import PdfReader
from docx import Document


def parse_pdf(file_path: str) -> str:
    """Extract text from PDF file."""
    reader = PdfReader(file_path)
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
    return "\n".join(text_parts)


def parse_docx(file_path: str) -> str:
    """Extract text from Word document."""
    doc = Document(file_path)
    text_parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)
    return "\n".join(text_parts)


async def parse_file(file_path: str) -> str:
    """Parse file based on extension. Returns extracted text."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return parse_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return parse_docx(file_path)
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    elif ext in (".png", ".jpg", ".jpeg", ".webp"):
        # 图片简历：调用视觉模型做 OCR（延迟导入，避免循环依赖）
        from app.services.llm_service import llm_service
        return await llm_service.parse_image(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".png", ".jpg", ".jpeg", ".webp"}


def allowed_file(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS
