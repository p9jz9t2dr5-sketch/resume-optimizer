"""File parsing tests, including scanned-PDF rendering and OCR fallback."""

import asyncio
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.services import file_parser


def _write_blank_pdf(path: Path, pages: int = 1) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    with path.open("wb") as output:
        writer.write(output)
    return path


def test_text_pdf_skips_ocr(monkeypatch, tmp_path):
    pdf_path = _write_blank_pdf(tmp_path / "text.pdf")
    monkeypatch.setattr(file_parser, "parse_pdf", lambda _: "完整文字层" * 20)

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("text PDF must not invoke OCR")

    monkeypatch.setattr(file_parser, "_ocr_pdf", fail_if_called)

    result = asyncio.run(file_parser.parse_file(str(pdf_path)))

    assert result == "完整文字层" * 20


def test_scanned_pdf_renders_every_page_and_combines_ocr(monkeypatch, tmp_path):
    pdf_path = _write_blank_pdf(tmp_path / "scanned.pdf", pages=2)
    rendered_paths: list[str] = []
    # CI 没有 .env.local，必须显式给 key；否则会走「缺 Key」分支而不是渲染路径。
    # （本地因为 .env.local 里有真实 key，这个依赖曾经被掩盖。）
    monkeypatch.setattr(file_parser.settings, "DASHSCOPE_API_KEY", "test-key")

    async def fake_parse_image(image_path: str) -> str:
        assert Path(image_path).is_file()
        assert Path(image_path).suffix == ".jpg"
        rendered_paths.append(image_path)
        return f"第 {len(rendered_paths)} 页识别内容"

    monkeypatch.setattr(file_parser, "parse_pdf", lambda _: "")
    monkeypatch.setattr(
        "app.services.llm_service.llm_service.parse_image",
        fake_parse_image,
    )

    result = asyncio.run(file_parser.parse_file(str(pdf_path)))

    assert len(rendered_paths) == 2
    assert "## 第 1 页" in result
    assert "第 1 页识别内容" in result
    assert "## 第 2 页" in result
    assert "第 2 页识别内容" in result


def test_scanned_pdf_without_vision_key_has_actionable_error(monkeypatch, tmp_path):
    pdf_path = _write_blank_pdf(tmp_path / "scanned.pdf")
    monkeypatch.setattr(file_parser, "parse_pdf", lambda _: "")
    monkeypatch.setattr(file_parser.settings, "DASHSCOPE_API_KEY", "")

    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        asyncio.run(file_parser.parse_file(str(pdf_path)))


def test_short_text_pdf_skips_ocr(monkeypatch, tmp_path):
    """短但确为文字的 PDF 不应被误判成扫描件。"""
    pdf_path = _write_blank_pdf(tmp_path / "short.pdf", pages=1)
    monkeypatch.setattr(file_parser, "parse_pdf", lambda _: "这是一份很短的纯文字简历")

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("短文字 PDF 不应触发 OCR")

    monkeypatch.setattr(file_parser, "_ocr_pdf", fail_if_called)

    assert asyncio.run(file_parser.parse_file(str(pdf_path))) == "这是一份很短的纯文字简历"


def test_sparse_text_multipage_pdf_triggers_ocr(monkeypatch, tmp_path):
    """8 页却只有 15 个字——是扫描件里带页码的典型特征，应走 OCR。"""
    pdf_path = _write_blank_pdf(tmp_path / "sparse.pdf", pages=8)
    monkeypatch.setattr(file_parser, "parse_pdf", lambda _: "123456789012345")

    async def fake_ocr(file_path, fallback_text=""):
        return "OCR 识别结果"

    monkeypatch.setattr(file_parser, "_ocr_pdf", fake_ocr)

    assert asyncio.run(file_parser.parse_file(str(pdf_path))) == "OCR 识别结果"
