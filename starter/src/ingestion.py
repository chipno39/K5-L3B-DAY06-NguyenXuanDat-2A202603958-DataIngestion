"""Read and normalize source data with full page/section traceability and error logging."""
from pathlib import Path
import re
import unicodedata
from typing import Any
from pypdf import PdfReader
from .models import DocumentPage


def normalize_text(text: str) -> str:
    """Normalize Unicode (NFC) and whitespace without discarding paragraph/line structure."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = (
        text.replace("\u00a0", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\u00ad", "")
    )
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    # Filter out consecutive blank lines while keeping paragraph boundaries
    cleaned_lines: list[str] = []
    blank_Streak = 0
    for line in lines:
        if not line:
            blank_Streak += 1
            if blank_Streak <= 1:
                cleaned_lines.append("")
        else:
            blank_Streak = 0
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def classify_fptu_handbook_page(page_num: int, norm_len: int) -> tuple[str, str]:
    """Return (section_code, page_status) based on the handbook Table of Contents (page 5)."""
    if page_num in (1, 2, 111, 112):
        return "00_bia_va_muc_luc", "excluded_cover_or_blank_photo"
    if page_num in (3, 6):
        return "00_bia_va_muc_luc", "excluded_front_matter"
    if page_num in (4, 5):
        return "00_bia_va_muc_luc", "excluded_table_of_contents"
    if page_num in (7, 13, 19, 31, 40, 54, 58, 66, 85, 109):
        divider_map = {
            7: "01_gioi_thieu_chung",
            13: "02_noi_quy_sinh_vien",
            19: "03_quy_che_dao_tao",
            31: "04_tai_chinh_hoc_phi",
            40: "05_ho_tro_sinh_vien",
            54: "05_ho_tro_sinh_vien",
            58: "06_thu_vien",
            66: "07_cntt_it_support",
            85: "08_nhung_dieu_can_biet",
            109: "09_cam_ket_trung_thuc",
        }
        return divider_map[page_num], "excluded_section_divider"

    if 8 <= page_num <= 12:
        return "01_gioi_thieu_chung", "valid_content"
    if 14 <= page_num <= 18:
        return "02_noi_quy_sinh_vien", "valid_content"
    if 20 <= page_num <= 30:
        return "03_quy_che_dao_tao", "valid_content"
    if 32 <= page_num <= 39:
        return "04_tai_chinh_hoc_phi", "valid_content"
    if 41 <= page_num <= 57:
        return "05_ho_tro_sinh_vien", "valid_content"
    if 59 <= page_num <= 65:
        return "06_thu_vien", "valid_content"
    if 67 <= page_num <= 84:
        return "07_cntt_it_support", "valid_content"
    if 86 <= page_num <= 108:
        return "08_nhung_dieu_can_biet", "valid_content"
    if page_num == 110:
        return "09_cam_ket_trung_thuc", "valid_content"
    if norm_len == 0:
        return "unknown", "excluded_empty_page"
    return "unknown", "valid_content"


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract each physical page; keep its page number, source, section, and status metadata.

    Detects and records pages with no text or non-content status (cover, TOC, section dividers).
    """
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found at: {path}")

    reader = PdfReader(str(path))
    pages: list[DocumentPage] = []

    for idx, pdf_page in enumerate(reader.pages, start=1):
        try:
            raw_text = pdf_page.extract_text() or ""
            extraction_error = None
        except Exception as exc:
            raw_text = ""
            extraction_error = str(exc)

        norm_text = normalize_text(raw_text)
        section, status = classify_fptu_handbook_page(idx, len(norm_text))
        is_valid = status == "valid_content" and len(norm_text) > 0

        meta: dict[str, Any] = {
            "page_id": f"{document_id}:p{idx:03d}",
            "section": section,
            "status": status,
            "is_valid_content": is_valid,
            "has_text": len(norm_text) > 0,
            "raw_chars": len(raw_text),
            "normalized_chars": len(norm_text),
            "document_type": "student_handbook",
            "language": "vi",
        }
        if extraction_error:
            meta["extraction_error"] = extraction_error

        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=idx,
                text=norm_text,
                metadata=meta,
            )
        )

    return pages
