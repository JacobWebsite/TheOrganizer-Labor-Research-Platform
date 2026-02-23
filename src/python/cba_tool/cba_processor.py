from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pdfplumber

from db_config import get_connection

from .langextract_processor import LangExtractProcessor, ProvisionExtraction


@dataclass
class PageSpan:
    page_number: int
    char_start: int
    char_end: int


@dataclass
class DocumentText:
    text: str
    page_count: int
    spans: list[PageSpan]


class CBAProcessor:
    """End-to-end CBA ingestion and provision extraction pipeline."""

    def __init__(self, *, model_id: str = "models/gemini-flash-latest") -> None:
        self.extractor = LangExtractProcessor(model_id=model_id)

    def _load_pdf_text(self, pdf_path: Path, *, max_pages: int | None = None) -> DocumentText:
        spans: list[PageSpan] = []
        chunks: list[str] = []
        cursor = 0

        with pdfplumber.open(str(pdf_path)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                if max_pages is not None and idx > max_pages:
                    break
                page_text = page.extract_text(layout=True) or ""
                if page_text and not page_text.endswith("\n"):
                    page_text = page_text + "\n"
                start = cursor
                chunks.append(page_text)
                cursor += len(page_text)
                spans.append(PageSpan(page_number=idx, char_start=start, char_end=cursor))

            return DocumentText(text="".join(chunks), page_count=len(pdf.pages), spans=spans)

    @staticmethod
    def _is_scanned_document(doc: DocumentText) -> bool:
        if doc.page_count == 0:
            return True
        avg_chars = len(doc.text.strip()) / max(doc.page_count, 1)
        return avg_chars < 80

    @staticmethod
    def _page_for_char(spans: list[PageSpan], char_pos: int) -> int | None:
        lo, hi = 0, len(spans) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            span = spans[mid]
            if char_pos < span.char_start:
                hi = mid - 1
            elif char_pos >= span.char_end:
                lo = mid + 1
            else:
                return span.page_number
        return None

    def _insert_document(
        self,
        *,
        cur,
        employer_name: str,
        union_name: str,
        source_name: str,
        source_url: str,
        file_path: str,
        page_count: int,
        is_scanned: bool,
        effective_date: date | None = None,
        expiration_date: date | None = None,
    ) -> int:
        cur.execute(
            """
            INSERT INTO cba_documents (
                employer_name_raw,
                union_name_raw,
                source_name,
                source_url,
                file_path,
                file_format,
                is_scanned,
                page_count,
                effective_date,
                expiration_date,
                is_current,
                structure_quality,
                ocr_status,
                extraction_status
            )
            VALUES (%s, %s, %s, %s, %s, 'PDF', %s, %s, %s, %s, TRUE, %s, %s, 'pending')
            RETURNING cba_id
            """,
            [
                employer_name,
                union_name,
                source_name,
                source_url,
                file_path,
                is_scanned,
                page_count,
                effective_date,
                expiration_date,
                "well-organized",
                "needed" if is_scanned else "not_needed",
            ],
        )
        return int(cur.fetchone()[0])

    @staticmethod
    def _update_document_status(cur, cba_id: int, status: str) -> None:
        cur.execute(
            """
            UPDATE cba_documents
            SET extraction_status = %s, updated_at = NOW()
            WHERE cba_id = %s
            """,
            [status, cba_id],
        )

    @staticmethod
    def _clear_existing_provisions(cur, cba_id: int) -> None:
        cur.execute("DELETE FROM cba_provisions WHERE cba_id = %s", [cba_id])

    def _insert_provisions(
        self,
        *,
        cur,
        cba_id: int,
        spans: list[PageSpan],
        provisions: list[ProvisionExtraction],
    ) -> int:
        inserted = 0
        for provision in provisions:
            page_start = self._page_for_char(spans, provision.char_start)
            page_end = self._page_for_char(spans, max(provision.char_end - 1, provision.char_start))

            cur.execute(
                """
                INSERT INTO cba_provisions (
                    cba_id,
                    category,
                    provision_class,
                    provision_text,
                    summary,
                    page_start,
                    page_end,
                    char_start,
                    char_end,
                    modal_verb,
                    legal_weight,
                    confidence_score,
                    model_version,
                    is_human_verified
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)
                """,
                [
                    cba_id,
                    provision.category,
                    provision.provision_class,
                    provision.provision_text,
                    provision.summary,
                    page_start,
                    page_end,
                    provision.char_start,
                    provision.char_end,
                    provision.modal_verb,
                    provision.legal_weight,
                    provision.confidence_score,
                    self.extractor.model_id,
                ],
            )
            inserted += 1
        return inserted

    def _extract_ai_best_effort(self, text: str) -> list[ProvisionExtraction]:
        bounded_text = text[:120000]
        if len(bounded_text) > 50000:
            return []
        try:
            return self.extractor.extract(bounded_text)
        except Exception:
            return []

    def _heuristic_extract(self, text: str, max_items: int = 250) -> list[ProvisionExtraction]:
        class_keywords = {
            "overtime": [r"\bovertime\b", r"time and one[- ]half", r"\bdouble time\b"],
            "discipline_and_discharge": [r"\bjust cause\b", r"\bdiscipline\b", r"\bdischarge\b"],
            "grievance_and_arbitration": [r"\bgrievance\b", r"\barbitration\b"],
            "health_insurance": [r"\bhealth insurance\b", r"\bmedical coverage\b", r"\bbenefits\b"],
            "retirement_pension": [r"\bpension\b", r"\bretirement\b", r"\bannuity\b"],
            "wages_base_pay": [r"\bwage\b", r"\bsalary\b", r"\bpay rate\b"],
            "union_security_and_dues": [r"\bdues\b", r"\bcheckoff\b", r"\bunion security\b"],
            "seniority": [r"\bseniority\b"],
            "job_security_layoff_recall": [r"\blayoff\b", r"\brecall\b", r"\bbumping\b"],
            "hours_and_scheduling": [r"\bschedule\b", r"\bshift\b", r"\bhours of work\b"],
        }
        modal_re = re.compile(r"\b(shall|must|may|will)\b", re.IGNORECASE)
        sentence_re = re.compile(r"[^.\n!?]{20,600}[.\n!?]")

        extracted: list[ProvisionExtraction] = []
        for match in sentence_re.finditer(text):
            sentence = match.group(0).strip()
            lower = sentence.lower()
            provision_class = None
            for cls, patterns in class_keywords.items():
                if any(re.search(p, lower) for p in patterns):
                    provision_class = cls
                    break
            if not provision_class:
                continue

            category = self.extractor.class_map.get(provision_class, "misc")
            modal_match = modal_re.search(sentence)
            extracted.append(
                ProvisionExtraction(
                    category=category,
                    provision_class=provision_class,
                    provision_text=sentence,
                    char_start=match.start(),
                    char_end=match.end(),
                    confidence_score=0.35,
                    summary=f"Heuristic extraction for {provision_class}",
                    modal_verb=(modal_match.group(1).lower() if modal_match else None),
                    legal_weight=0.35,
                )
            )
            if len(extracted) >= max_items:
                break
        return extracted

    def process_pdf(
        self,
        *,
        pdf_path: str | Path,
        employer_name: str,
        union_name: str,
        source_name: str = "Local Archive",
        source_url: str | None = None,
        effective_date: date | None = None,
        expiration_date: date | None = None,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        file_path = Path(pdf_path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"PDF not found: {file_path}")

        doc = self._load_pdf_text(file_path, max_pages=max_pages)
        is_scanned = self._is_scanned_document(doc)

        with get_connection() as conn:
            with conn.cursor() as cur:
                cba_id = self._insert_document(
                    cur=cur,
                    employer_name=employer_name,
                    union_name=union_name,
                    source_name=source_name,
                    source_url=source_url or f"local://{file_path.name}",
                    file_path=str(file_path),
                    page_count=doc.page_count,
                    is_scanned=is_scanned,
                    effective_date=effective_date,
                    expiration_date=expiration_date,
                )

                try:
                    self._update_document_status(cur, cba_id, "processing")
                    if is_scanned:
                        self._update_document_status(cur, cba_id, "needs_ocr")
                        conn.commit()
                        return {
                            "cba_id": cba_id,
                            "provisions_inserted": 0,
                            "is_scanned": True,
                            "status": "needs_ocr",
                        }

                    provisions = self._extract_ai_best_effort(doc.text)
                    if not provisions:
                        provisions = self._heuristic_extract(doc.text)
                    self._clear_existing_provisions(cur, cba_id)
                    inserted = self._insert_provisions(
                        cur=cur,
                        cba_id=cba_id,
                        spans=doc.spans,
                        provisions=provisions,
                    )
                    final_status = "completed" if inserted > 0 else "completed_empty"
                    self._update_document_status(cur, cba_id, final_status)
                    conn.commit()
                    return {
                        "cba_id": cba_id,
                        "provisions_inserted": inserted,
                        "is_scanned": False,
                        "status": final_status,
                    }
                except Exception:
                    self._update_document_status(cur, cba_id, "failed")
                    conn.commit()
                    raise


def default_test_pdf_path() -> Path:
    cwd = Path(os.getcwd())
    return cwd / "archive" / "Claude Ai union project" / "2021-2024_League_CBA_Booklet_PDF_1.pdf"
