"""Implement fixed-size and structure-aware paragraph chunking with full metadata retention."""
import re
from .models import Chunk, DocumentPage


def fixed_size(page: DocumentPage, size: int = 500, overlap: int = 50) -> list[Chunk]:
    """Split page text into fixed-size overlapping character windows and retain page metadata."""
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >= 0 and < size")

    text = page.text.strip()
    if not text or not page.metadata.get("is_valid_content", True):
        return []

    chunks: list[Chunk] = []
    step = size - overlap
    start = 0
    chunk_idx = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + size, text_len)
        window = text[start:end].strip()
        if window:
            chunk_idx += 1
            meta = dict(page.metadata)
            meta.update(
                {
                    "chunk_index": chunk_idx,
                    "chunking_method": "fixed_size",
                    "chunk_size_param": size,
                    "overlap_param": overlap,
                    "char_start": start,
                    "char_end": end,
                    "char_len": len(window),
                }
            )
            chunks.append(
                Chunk(
                    chunk_id=f"{page.document_id}:p{page.page:03d}:fixed:c{chunk_idx:03d}",
                    document_id=page.document_id,
                    source=page.source,
                    page=page.page,
                    text=window,
                    metadata=meta,
                )
            )
        if end >= text_len:
            break
        start += step

    return chunks


def _split_into_semantic_units(text: str) -> list[str]:
    """Group raw PDF lines into logical paragraphs / bullet items / regulation clauses."""
    raw_lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not raw_lines:
        return []

    units: list[str] = []
    current: list[str] = []

    boundary_pattern = re.compile(
        r"^(?:"
        r"[•\+\-]\s*"
        r"|Điều\s+\d+"
        r"|Bước\s+\d+"
        r"|\d+\.\d*\s+"
        r"|0[1-9]\b"
        r"|GIAI ĐOẠN\b"
        r"|PHÒNG\b"
        r"|HƯỚNG DẪN\b"
        r"|QUY ĐỊNH\b"
        r"|ĐIỀU KIỆN\b"
        r"|LƯU Ý\b"
        r")"
    )

    for line in raw_lines:
        # Remove isolated bullet markers that PDF extraction puts on their own line
        if line in ("•", "••", "o", "+"):
            continue
        is_boundary = bool(boundary_pattern.match(line))
        # Also treat a line after a sentence-ending punctuation as a potential paragraph break
        prev_ended_sentence = bool(current and current[-1].endswith((".", ";", ":", "?", "!")))

        if current and (is_boundary or (prev_ended_sentence and len(" ".join(current)) >= 180)):
            units.append("\n".join(current))
            current = [line]
        else:
            current.append(line)

    if current:
        units.append("\n".join(current))

    return units


def _split_oversized_unit(unit: str, max_size: int) -> list[str]:
    """Split an oversized paragraph along sentence boundaries, falling back to word boundaries."""
    if len(unit) <= max_size:
        return [unit]

    sentences = re.split(r"(?<=[\.\;\!\?\n])\s+", unit)
    pieces: list[str] = []
    current = ""

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        candidate = f"{current}\n{sent}".strip() if current else sent
        if len(candidate) <= max_size:
            current = candidate
        else:
            if current:
                pieces.append(current)
            if len(sent) <= max_size:
                current = sent
            else:
                # Word-level fallback if a single sentence is still longer than max_size
                words = sent.split(" ")
                w_buf = ""
                for w in words:
                    w_cand = f"{w_buf} {w}".strip() if w_buf else w
                    if len(w_cand) <= max_size:
                        w_buf = w_cand
                    else:
                        if w_buf:
                            pieces.append(w_buf)
                        w_buf = w[:max_size]
                current = w_buf

    if current:
        pieces.append(current)

    return pieces


def by_paragraph(page: DocumentPage, max_size: int = 850) -> list[Chunk]:
    """Group semantic paragraphs up to max_size, split oversized paragraphs cleanly, and retain metadata."""
    if max_size <= 0:
        raise ValueError("max_size must be positive")

    text = page.text.strip()
    if not text or not page.metadata.get("is_valid_content", True):
        return []

    units = _split_into_semantic_units(text)
    expanded_units: list[str] = []
    for u in units:
        expanded_units.extend(_split_oversized_unit(u, max_size))

    packed_texts: list[str] = []
    current_buf = ""

    for unit in expanded_units:
        candidate = f"{current_buf}\n{unit}".strip() if current_buf else unit
        if len(candidate) <= max_size:
            current_buf = candidate
        else:
            if current_buf:
                packed_texts.append(current_buf)
            current_buf = unit

    if current_buf:
        packed_texts.append(current_buf)

    chunks: list[Chunk] = []
    cursor = 0
    for idx, chunk_text in enumerate(packed_texts, start=1):
        pos = text.find(chunk_text[:30], cursor)
        char_start = pos if pos != -1 else cursor
        char_end = min(char_start + len(chunk_text), len(text))
        cursor = char_end

        meta = dict(page.metadata)
        meta.update(
            {
                "chunk_index": idx,
                "chunking_method": "by_paragraph",
                "max_size_param": max_size,
                "char_start": char_start,
                "char_end": char_end,
                "char_len": len(chunk_text),
            }
        )
        chunks.append(
            Chunk(
                chunk_id=f"{page.document_id}:p{page.page:03d}:para:c{idx:03d}",
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=chunk_text,
                metadata=meta,
            )
        )

    return chunks
