from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import langextract as lx
from langextract import data as lx_data


DEFAULT_MODEL_ID = "models/gemini-flash-latest"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "cba_extraction_classes.json"


@dataclass
class ProvisionExtraction:
    category: str
    provision_class: str
    provision_text: str
    char_start: int
    char_end: int
    confidence_score: float
    summary: str | None = None
    modal_verb: str | None = None
    legal_weight: float | None = None


class LangExtractProcessor:
    """Wrapper around langextract with config-driven provision classes."""

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_MODEL_ID,
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        api_key: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.config_path = Path(config_path)
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("LANGEXTRACT_API_KEY")
        self.class_map, self.aliases = self._load_class_config(self.config_path)

    @staticmethod
    def _load_class_config(config_path: Path) -> tuple[dict[str, str], dict[str, str]]:
        if not config_path.exists():
            raise FileNotFoundError(f"CBA extraction class config not found: {config_path}")

        payload = json.loads(config_path.read_text(encoding="utf-8"))
        classes = payload.get("classes", [])
        aliases = payload.get("aliases", {})
        if not classes:
            raise ValueError("No extraction classes configured in cba_extraction_classes.json")

        class_map: dict[str, str] = {}
        for item in classes:
            name = str(item.get("name", "")).strip()
            category = str(item.get("category", "")).strip()
            if not name or not category:
                continue
            class_map[name] = category

        normalized_aliases: dict[str, str] = {}
        for alias, target in aliases.items():
            normalized_aliases[str(alias).strip().lower()] = str(target).strip()

        return class_map, normalized_aliases

    def _prompt_description(self) -> str:
        class_lines: list[str] = []
        for provision_class, category in self.class_map.items():
            class_lines.append(f"- {provision_class} (category={category})")

        return (
            "Extract collective bargaining agreement provisions as atomic clauses. "
            "Return every relevant clause occurrence with exact span grounding.\n\n"
            "Rules:\n"
            "- Use one extraction per distinct legal or contractual obligation/right.\n"
            "- Keep extraction_text verbatim from the source.\n"
            "- Prefer complete sentence or subsection level when possible.\n"
            "- Use only the listed classes below.\n"
            "- If uncertain, skip rather than hallucinate.\n"
            "- Add attributes when possible: summary, modal_verb (shall/must/may/will), legal_weight (0.0-1.0).\n\n"
            "Allowed classes:\n"
            + "\n".join(class_lines)
        )

    def _examples(self) -> list[lx_data.ExampleData]:
        return [
            lx_data.ExampleData(
                text="Employees shall receive time and one-half for all hours worked beyond forty in a week.",
                extractions=[
                    lx_data.Extraction(
                        extraction_class="overtime",
                        extraction_text="shall receive time and one-half for all hours worked beyond forty in a week",
                        attributes={"modal_verb": "shall", "summary": "Overtime premium after 40 hours", "legal_weight": "0.9"},
                    )
                ],
            ),
            lx_data.ExampleData(
                text="The Employer will contribute $1.25 per hour to the pension fund for each covered employee.",
                extractions=[
                    lx_data.Extraction(
                        extraction_class="retirement_pension",
                        extraction_text="will contribute $1.25 per hour to the pension fund",
                        attributes={"modal_verb": "will", "summary": "Employer pension contribution", "legal_weight": "0.85"},
                    )
                ],
            ),
            lx_data.ExampleData(
                text="No employee shall be discharged except for just cause and after progressive discipline.",
                extractions=[
                    lx_data.Extraction(
                        extraction_class="discipline_and_discharge",
                        extraction_text="shall be discharged except for just cause and after progressive discipline",
                        attributes={"modal_verb": "shall", "summary": "Just-cause and progressive discipline", "legal_weight": "0.95"},
                    )
                ],
            ),
        ]

    def _normalize_class_name(self, extraction_class: str) -> str:
        normalized = extraction_class.strip().lower().replace(" ", "_")
        if normalized in self.class_map:
            return normalized
        if normalized in self.aliases:
            return self.aliases[normalized]
        return normalized

    def _coerce_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _provider_model_id(self) -> str:
        model_id = self.model_id.strip()
        if model_id.startswith("models/"):
            return model_id.split("/", 1)[1]
        return model_id

    def extract(self, text: str) -> list[ProvisionExtraction]:
        if not text.strip():
            return []
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY (or LANGEXTRACT_API_KEY) is required for CBA extraction.")

        docs = lx.extract(
            text_or_documents=text,
            prompt_description=self._prompt_description(),
            examples=self._examples(),
            model_id=self._provider_model_id(),
            api_key=self.api_key,
            temperature=0.0,
            max_char_buffer=6000,
            extraction_passes=1,
            show_progress=False,
        )
        if not isinstance(docs, list):
            docs = [docs]

        extracted: list[ProvisionExtraction] = []
        for doc in docs:
            for item in getattr(doc, "extractions", []) or []:
                raw_class = str(getattr(item, "extraction_class", "")).strip()
                normalized_class = self._normalize_class_name(raw_class)
                category = self.class_map.get(normalized_class)
                if not category:
                    continue

                span = getattr(item, "char_interval", None)
                if span is None:
                    continue
                char_start = int(getattr(span, "start_pos", -1))
                char_end = int(getattr(span, "end_pos", -1))
                if char_start < 0 or char_end <= char_start:
                    continue

                attrs = getattr(item, "attributes", {}) or {}
                extracted.append(
                    ProvisionExtraction(
                        category=category,
                        provision_class=normalized_class,
                        provision_text=str(getattr(item, "extraction_text", "")).strip(),
                        char_start=char_start,
                        char_end=char_end,
                        confidence_score=1.0,
                        summary=(attrs.get("summary") or "").strip() or None,
                        modal_verb=(attrs.get("modal_verb") or "").strip() or None,
                        legal_weight=self._coerce_float(attrs.get("legal_weight"), default=0.5),
                    )
                )
        return extracted
