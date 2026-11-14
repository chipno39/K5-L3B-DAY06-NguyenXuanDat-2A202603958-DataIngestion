"""Evaluate retrieved evidence and preserve per-query top-3 traces."""
import re
from typing import Any


def _clean_for_match(text: str) -> str:
    """Normalize whitespace and strip standalone bullet symbols for fair substring verification."""
    if not text:
        return ""
    # Remove isolated bullet characters that may be stripped during paragraph packing
    cleaned = re.sub(r"[•●▪]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def _chunk_contains_evidence(question: dict[str, Any], hit: dict[str, Any]) -> tuple[bool, str]:
    """Check whether a single retrieved chunk matches gold source/page and contains the full gold evidence."""
    gold_source = question.get("gold_source_id")
    gold_page = int(question.get("gold_page", -1))
    alt_pages = [int(p) for p in question.get("alt_gold_pages", [])]
    valid_pages = {gold_page, *alt_pages}

    if hit.get("document_id") != gold_source:
        return False, "wrong_document_id"
    if int(hit.get("page", -2)) not in valid_pages:
        return False, "wrong_page"

    hit_norm = _clean_for_match(hit.get("text", ""))
    candidate_quotes = [question.get("evidence_quote", "")]
    candidate_quotes.extend(question.get("alt_evidence_quotes", []))

    for quote in candidate_quotes:
        q_norm = _clean_for_match(quote)
        if q_norm and q_norm in hit_norm:
            return True, "full_evidence_match"

    return False, "same_page_partial_or_missing_evidence"


def evaluate_query(
    question: dict[str, Any],
    hits: list[dict[str, Any]],
    strategy: str = "",
    applied_filter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check source/page and gold evidence sufficiency; keep full top-3 trace and split-evidence diagnostics.

    Note: Automated Hit@1 and Evidence Hit@3 do NOT replace manual human labels for
    Chunk Coherence or Grounding Quality.
    """
    gold_source = question.get("gold_source_id")
    gold_page = int(question.get("gold_page", -1))
    alt_pages = [int(p) for p in question.get("alt_gold_pages", [])]
    valid_pages = {gold_page, *alt_pages}

    annotated_hits: list[dict[str, Any]] = []
    hit_flags: list[bool] = []
    page_match_flags: list[bool] = []

    for h in hits[:3]:
        is_hit, match_reason = _chunk_contains_evidence(question, h)
        is_gold_page = (
            h.get("document_id") == gold_source and int(h.get("page", -2)) in valid_pages
        )
        hit_flags.append(is_hit)
        page_match_flags.append(is_gold_page)

        meta = h.get("metadata", {})
        has_required_meta = bool(
            h.get("document_id")
            and h.get("source")
            and isinstance(h.get("page"), int)
            and h.get("page", 0) > 0
            and (h.get("section") or meta.get("section"))
        )

        annotated_hits.append(
            {
                "rank": h.get("rank"),
                "chunk_id": h.get("chunk_id"),
                "document_id": h.get("document_id"),
                "source": h.get("source"),
                "page": h.get("page"),
                "section": h.get("section") or meta.get("section", ""),
                "score": h.get("score"),
                "is_gold_page": is_gold_page,
                "is_evidence_hit": is_hit,
                "match_reason": match_reason,
                "has_required_metadata": has_required_meta,
                "text": h.get("text", ""),
                "metadata": meta,
            }
        )

    hit_at_1 = bool(hit_flags[0]) if hit_flags else False
    hit_at_3 = any(hit_flags[:3])

    # Check if evidence was split across multiple retrieved chunks from the gold page in top-3
    gold_page_texts = [
        h.get("text", "")
        for h in annotated_hits
        if h["is_gold_page"]
    ]
    combined_gold_text = _clean_for_match(" ".join(gold_page_texts))
    primary_quote_norm = _clean_for_match(question.get("evidence_quote", ""))
    multi_chunk_union_hit = bool(
        primary_quote_norm and primary_quote_norm in combined_gold_text
    )
    evidence_split_across_chunks = (not hit_at_3) and multi_chunk_union_hit

    # Check filter compliance when the question defines a metadata filter
    q_filter = question.get("filter")
    if q_filter:
        compliant_hits = 0
        for h in annotated_hits:
            ok = True
            for fk, fv in q_filter.items():
                actual_val = h.get(fk) or h.get("metadata", {}).get(fk)
                if str(actual_val) != str(fv):
                    ok = False
                    break
            if ok:
                compliant_hits += 1
        filter_compliant = len(annotated_hits) > 0 and compliant_hits == len(annotated_hits)
    else:
        filter_compliant = None

    return {
        "strategy": strategy,
        "question_id": question["id"],
        "split": question["split"],
        "question_type": question.get("type", ""),
        "question": question["question"],
        "expected_answer": question.get("expected_answer", ""),
        "gold_source_id": gold_source,
        "gold_page": gold_page,
        "alt_gold_pages": alt_pages,
        "evidence_quote": question.get("evidence_quote", ""),
        "question_filter": q_filter,
        "applied_filter": applied_filter,
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "page_hit_at_1": bool(page_match_flags[0]) if page_match_flags else False,
        "page_hit_at_3": any(page_match_flags[:3]),
        "multi_chunk_union_hit_at_3": multi_chunk_union_hit,
        "evidence_split_across_chunks": evidence_split_across_chunks,
        "filter_compliant_top3": filter_compliant,
        "top_3_hits": annotated_hits,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1, Evidence Hit@3, and filter compliance by strategy and dev/test split."""
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for tr in traces:
        strat = tr.get("strategy", "unknown")
        split = tr.get("split", "unknown")
        grouped.setdefault(strat, {}).setdefault(split, []).append(tr)
        grouped.setdefault(strat, {}).setdefault("all", []).append(tr)

    summary: dict[str, Any] = {}
    for strat, splits in grouped.items():
        summary[strat] = {}
        for split_name, items in splits.items():
            total = len(items)
            h1 = sum(1 for x in items if x["hit_at_1"])
            h3 = sum(1 for x in items if x["hit_at_3"])
            p1 = sum(1 for x in items if x.get("page_hit_at_1"))
            p3 = sum(1 for x in items if x.get("page_hit_at_3"))
            split_err = sum(1 for x in items if x.get("evidence_split_across_chunks"))

            filter_items = [x for x in items if x.get("question_filter") is not None]
            f_total = len(filter_items)
            f_ok = sum(1 for x in filter_items if x.get("filter_compliant_top3") is True)

            summary[strat][split_name] = {
                "total_questions": total,
                "hit_at_1_count": h1,
                "hit_at_1_fraction": f"{h1}/{total}",
                "hit_at_1_pct": round((h1 / total) * 100, 2) if total else 0.0,
                "evidence_hit_at_3_count": h3,
                "evidence_hit_at_3_fraction": f"{h3}/{total}",
                "evidence_hit_at_3_pct": round((h3 / total) * 100, 2) if total else 0.0,
                "page_hit_at_1_fraction": f"{p1}/{total}",
                "page_hit_at_3_fraction": f"{p3}/{total}",
                "evidence_split_error_count": split_err,
                "filter_questions_count": f_total,
                "filter_compliant_count": f_ok if f_total > 0 else None,
                "filter_compliance_fraction": f"{f_ok}/{f_total}" if f_total > 0 else "N/A",
                "filter_compliance_pct": round((f_ok / f_total) * 100, 2) if f_total > 0 else None,
            }

    return summary
