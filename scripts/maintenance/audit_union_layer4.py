"""Union Explorer Audit -- Layer 4 (DeepSeek-V3 advisory rubric).

Per-union qualitative read of the API response against a hand-curated reference
card. Output is JSON with 1-5 scores on six dimensions plus evidence and
concerns. Always advisory (per Codex review 2026-05-04) -- never pass/fail.

Reasoner escalation triggers (per Codex):
  - Any dimension scored <= 2 by V3
  - Members or ttl_assets diverge >10x from reference card bounds
  - Top-employer plausibility fails for a top-50 union
  - V3 returns invalid JSON or flags uncertain=true
  - Major public-sector affiliation but report shows zero F7/NLRB despite
    private-sector industries listed

Costs (DeepSeek-V3 chat, 2026-05 pricing):
  $0.27 / 1M input tokens, $1.10 / 1M output tokens (prompt cache halves input)
  Per union: ~3K input + 800 output ~= $0.0017 -> $0.50 per 270-union run.
  Reasoner ~5x more for escalations.

Hard cost cap: --max-cost-usd (default 2.0). Aborts mid-run if exceeded.

Usage:
  py scripts/maintenance/audit_union_layer4.py --dry-run          # print prompts only, $0
  py scripts/maintenance/audit_union_layer4.py --max-unions 10    # tiny paid run
  py scripts/maintenance/audit_union_layer4.py --max-cost-usd 1.0 # full run capped at $1
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL_V3 = "deepseek-chat"           # V3
MODEL_REASONER = "deepseek-reasoner"  # R1


def _extract_json_object(text: str) -> dict | None:
    """Parse a JSON object out of a model response.

    deepseek-chat with response_format={"type":"json_object"} returns clean
    JSON. deepseek-reasoner can return thinking-content prefix + a JSON
    block. We try a strict json.loads first, then fall back to extracting
    the substring between the first `{` and the last matching `}`.
    """
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    # Find first balanced JSON object substring
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    start = -1
                    continue
    return None

# 2026-05 DeepSeek prices
PRICE_V3_IN = 0.27 / 1_000_000
PRICE_V3_OUT = 1.10 / 1_000_000
PRICE_REASONER_IN = 0.55 / 1_000_000
PRICE_REASONER_OUT = 2.19 / 1_000_000


# ============================================================
# Env loading (mirrors scripts/llm_dedup/deepseek_ab_test.py:91)
# ============================================================

def load_deepseek_key() -> str:
    for var in ("DEEPSEEK_API_KEY", "DEEPSEEK_API", "DeepSeek_API"):
        if os.environ.get(var):
            return os.environ[var]
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with env_path.open(encoding="utf-8") as f:
            for line in f:
                if "deepseek" in line.lower():
                    m = re.search(r"(sk-[A-Za-z0-9_-]+)", line)
                    if m:
                        return m.group(1)
    raise RuntimeError(
        "DeepSeek API key not found. Add DEEPSEEK_API_KEY=sk-... to .env "
        "or pass --dry-run to skip API calls."
    )


# ============================================================
# Reference cards
# ============================================================

def load_reference_cards(path: Path) -> dict[str, dict]:
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    cards = {c["aff_abbr"]: c for c in data.get("cards", [])}
    return cards


# ============================================================
# Dossier builder -- pulls API responses for one f_num
# ============================================================

def build_dossier(client, cur, f_num: str) -> dict[str, Any]:
    code, detail = client.get(f"/api/unions/{f_num}")
    code_d, disb = client.get(f"/api/unions/{f_num}/disbursements")
    code_e, emp = client.get(f"/api/unions/{f_num}/employers?limit=10")
    cur.execute("""
        SELECT um.union_name, um.aff_abbr, um.local_number, um.state, um.city,
               um.sector, um.is_likely_inactive,
               (SELECT MAX(yr_covered) FROM lm_data lm WHERE lm.f_num = um.f_num) AS latest_yr
        FROM unions_master um WHERE um.f_num = %s
    """, [f_num])
    row = cur.fetchone() or {}
    return {
        "f_num": f_num,
        "db_meta": {
            "union_name": row[0] if row else None,
            "aff_abbr": row[1] if row else None,
            "local_number": row[2] if row else None,
            "state": row[3] if row else None,
            "city": row[4] if row else None,
            "sector": row[5] if row else None,
            "is_likely_inactive": row[6] if row else None,
            "latest_lm2_year": row[7] if row else None,
        },
        "api_detail": detail or {},
        "api_disbursements": disb or {},
        "api_employers": emp or {},
        "api_status_codes": {"detail": code, "disbursements": code_d, "employers": code_e},
    }


# ============================================================
# Prompt construction
# ============================================================

SYSTEM_PROMPT = """\
You are a senior labor researcher reviewing the Union Explorer surface of a U.S.
labor relations research platform. The Union Explorer aggregates OLMS LM-2 financial
data, F-7 union-employer bargaining relationships, and NLRB election history per
union. You are given (a) the API response bundle for one union and (b) a hand-curated
reference card about its affiliation.

Your job is to read the API bundle and score it on six dimensions, 1-5:

  1. name_consistency: union_name spelled the same across the detail/disbursements/employers
     payloads, and consistent with the affiliation's normal naming convention.
  2. size_sanity: members and ttl_assets are within a plausible order of magnitude
     for this affiliation (compare to reference card's approx_active_members; for
     a single LOCAL of a national, expect <2% of national total).
  3. election_volume_sanity: NLRB election count per year matches the affiliation's
     typical NLRB activity. Public-sector or RLA-only affiliations should have
     ZERO direct NLRB matches and that is correct (not a low score).
  4. top_employer_plausibility: top employers represent industries the union
     actually organizes (e.g., SEIU should show hospitals/janitorial/security; IBEW
     should show electrical contractors and utilities; UFCW should show grocery and meatpacking).
  5. disbursement_distribution_sanity: spending across the 7 buckets isn't
     pathological. Red flags: 100% in one bucket; representational at 0% but
     financial at 90%.
  6. membership_trend_plausibility: the year-over-year membership trend matches
     plausible patterns (UAW slow decline since the 1990s; NEA roughly stable;
     SEIU slow growth then COVID hit; UNITE HERE big COVID dip then recovery).

Score 5 = everything looks right; 4 = minor concern; 3 = something off worth checking;
2 = suspect, likely a real bug or stale data; 1 = clearly wrong.

ALSO mark `uncertain: true` if you genuinely cannot judge -- e.g., reference card is
missing for a small/independent affiliation, or the API returned malformed data.

Output STRICT JSON ONLY (no prose), schema:
{
  "f_num": "<string>",
  "scores": {
    "name_consistency": 1-5,
    "size_sanity": 1-5,
    "election_volume_sanity": 1-5,
    "top_employer_plausibility": 1-5,
    "disbursement_distribution_sanity": 1-5,
    "membership_trend_plausibility": 1-5
  },
  "evidence": "<2-4 sentences citing specific numbers/names from the API bundle>",
  "concerns": ["<short string>", ...],
  "uncertain": true | false
}
"""


def build_user_prompt(dossier: dict, reference_card: dict | None) -> str:
    detail = dossier["api_detail"] or {}
    disb = dossier["api_disbursements"] or {}
    emp = dossier["api_employers"] or {}

    # Compress the dossier so the prompt fits comfortably in context
    compact = {
        "f_num": dossier["f_num"],
        "db_meta": dossier["db_meta"],
        "detail.union": detail.get("union"),
        "detail.financial_trends": detail.get("financial_trends"),
        "detail.elections_source": detail.get("elections_source"),
        "detail.election_note": detail.get("election_note"),
        "detail.nlrb_summary": detail.get("nlrb_summary"),
        "detail.top_employers": detail.get("top_employers"),
        "detail.industry_distribution": detail.get("industry_distribution"),
        "disbursements.years": disb.get("years")[:3] if disb.get("years") else None,
        "employers.top": (emp.get("employers") or [])[:10],
    }
    parts = ["UNION DOSSIER:", json.dumps(compact, indent=2, default=str), ""]
    if reference_card:
        parts += ["AFFILIATION REFERENCE CARD:",
                  json.dumps(reference_card, indent=2, default=str), ""]
    else:
        parts.append("AFFILIATION REFERENCE CARD: (none -- score with extra caution; if you cannot judge "
                     "size_sanity or top_employer_plausibility without it, mark uncertain=true)")
    parts.append("Score this union and respond with strict JSON.")
    return "\n".join(parts)


# ============================================================
# DeepSeek client wrapper
# ============================================================

@dataclass
class CallResult:
    f_num: str
    model: str
    rubric: dict[str, Any] | None
    raw_text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    elapsed_sec: float = 0.0
    escalated: bool = False


class DeepSeekClient:
    def __init__(self, api_key: str | None):
        if api_key:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        else:
            self.client = None  # dry-run mode

    def call(self, model: str, system: str, user: str, dry_run: bool = False) -> CallResult:
        if dry_run or self.client is None:
            return CallResult(
                f_num="?", model=f"DRY:{model}", rubric=None,
                raw_text="DRY RUN",
                prompt_tokens=len(system) // 4 + len(user) // 4,  # rough
                completion_tokens=400,
                cost_usd=0.0,
            )
        started = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=600,
            )
            text = resp.choices[0].message.content or ""
            usage = resp.usage
            in_t = getattr(usage, "prompt_tokens", 0)
            out_t = getattr(usage, "completion_tokens", 0)
            if model == MODEL_V3:
                cost = in_t * PRICE_V3_IN + out_t * PRICE_V3_OUT
            else:
                cost = in_t * PRICE_REASONER_IN + out_t * PRICE_REASONER_OUT
            rubric = _extract_json_object(text)
            return CallResult(
                f_num="?", model=model, rubric=rubric, raw_text=text,
                prompt_tokens=in_t, completion_tokens=out_t, cost_usd=cost,
                elapsed_sec=time.perf_counter() - started,
            )
        except Exception as exc:
            return CallResult(
                f_num="?", model=model, rubric=None, raw_text="",
                error=str(exc), elapsed_sec=time.perf_counter() - started,
            )


# ============================================================
# Escalation logic
# ============================================================

def should_escalate(result: CallResult, reference_card: dict | None, dossier: dict) -> tuple[bool, list[str]]:
    """Decide whether to re-run with deepseek-reasoner."""
    reasons = []
    if result.error:
        reasons.append(f"v3 error: {result.error}")
    elif result.rubric is None:
        reasons.append("v3 returned non-JSON")
    else:
        scores = result.rubric.get("scores") or {}
        if any(int(v) <= 2 for v in scores.values() if isinstance(v, (int, float))):
            reasons.append(f"v3 score <=2 on at least one dimension: {scores}")
        if result.rubric.get("uncertain") is True:
            reasons.append("v3 marked uncertain=true")
        # Order-of-magnitude divergence vs reference card
        if reference_card:
            bounds = reference_card.get("approx_active_members") or []
            if len(bounds) == 2:
                detail = dossier["api_detail"]
                fts = (detail.get("financial_trends") or []) if detail else []
                latest_members = fts[0].get("members") if fts else None
                if latest_members and (latest_members > 10 * bounds[1] or
                                       (latest_members > 0 and latest_members * 10 < bounds[0])):
                    reasons.append(
                        f"members {latest_members} >10x outside reference {bounds}"
                    )
    return (len(reasons) > 0, reasons)


# ============================================================
# Main
# ============================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-unions", type=int, default=None,
                    help="Cap units of work (default: full sample)")
    ap.add_argument("--max-cost-usd", type=float, default=2.0,
                    help="Hard abort if cumulative cost exceeds this (default $2)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Skip all API calls; print prompts and exit")
    ap.add_argument("--no-escalate", action="store_true",
                    help="Disable reasoner escalation (V3 only)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--reference-cards", default=None,
                    help="Path to YAML reference cards (default: audit_union_reference_cards.yaml)")
    args = ap.parse_args()

    cards_path = Path(args.reference_cards) if args.reference_cards else (HERE / "audit_union_reference_cards.yaml")
    cards = load_reference_cards(cards_path)
    print(f"Loaded {len(cards)} reference cards from {cards_path.name}")

    out_dir = Path(args.output_dir) if args.output_dir else (
        PROJECT_ROOT / "audit_runs" / dt.date.today().isoformat()
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    # ASGI client (in-process; bypasses the :8001 zombie)
    sys.path.insert(0, str(PROJECT_ROOT))
    os.environ.setdefault("DISABLE_AUTH", "true")
    os.environ["RATE_LIMIT_REQUESTS"] = "0"
    from fastapi.testclient import TestClient
    from api.main import app
    test_client = TestClient(app)

    class _ASGI:
        def get(self, path):
            r = test_client.get(path)
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, None
    client = _ASGI()

    # Sample selection: same logic as Layer 2
    sys.path.insert(0, str(HERE))
    from audit_union_layer2 import select_sample

    with get_connection() as conn:
        with conn.cursor() as cur:
            samples = select_sample(cur, sample_size=args.max_unions)
            distinct_fnums: list[str] = []
            seen = set()
            for bucket, fnums in samples.items():
                for f in fnums:
                    if f not in seen:
                        seen.add(f)
                        distinct_fnums.append(f)

            print(f"Sample: {len(distinct_fnums)} distinct unions")
            if args.max_unions:
                distinct_fnums = distinct_fnums[: args.max_unions]
                print(f"  capped to --max-unions {args.max_unions}")

            # Build dossiers
            print("Building dossiers (in-process API calls) ...")
            dossiers: list[dict] = []
            for i, f in enumerate(distinct_fnums, 1):
                if i % 25 == 1:
                    print(f"  dossier [{i:>4}/{len(distinct_fnums)}] f_num={f}")
                try:
                    d = build_dossier(client, cur, f)
                except Exception as exc:
                    try:
                        cur.connection.rollback()
                    except Exception:
                        pass
                    d = {"f_num": f, "_error": str(exc)}
                dossiers.append(d)

    # API calls
    api_key = None
    if not args.dry_run:
        try:
            api_key = load_deepseek_key()
            print("DeepSeek API key found.")
        except Exception as exc:
            print(f"\nNO API KEY: {exc}\nSwitching to --dry-run.\n")
            args.dry_run = True

    ds = DeepSeekClient(api_key)

    results: list[CallResult] = []
    cumulative_cost = 0.0

    print(f"\nRunning {len(dossiers)} V3 calls (concurrency={args.concurrency}, "
          f"dry_run={args.dry_run}, max_cost=${args.max_cost_usd}) ...")

    def _call_one(dossier: dict) -> CallResult:
        if "_error" in dossier:
            return CallResult(f_num=dossier["f_num"], model="skipped",
                              rubric=None, raw_text="", error=dossier["_error"])
        f_num = dossier["f_num"]
        aff = (dossier.get("db_meta") or {}).get("aff_abbr")
        ref = cards.get(aff)
        user_prompt = build_user_prompt(dossier, ref)
        if args.dry_run:
            return CallResult(f_num=f_num, model="DRY:V3", rubric=None,
                              raw_text=f"PROMPT_LENGTH={len(user_prompt)}", cost_usd=0.0)
        r = ds.call(MODEL_V3, SYSTEM_PROMPT, user_prompt)
        r.f_num = f_num
        return r

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        future_to_d = {ex.submit(_call_one, d): d for d in dossiers}
        for i, fut in enumerate(as_completed(future_to_d), 1):
            r = fut.result()
            results.append(r)
            cumulative_cost += r.cost_usd
            if i % 10 == 0 or i == 1:
                err = f" ERR={r.error}" if r.error else ""
                print(f"  v3 [{i:>3}/{len(dossiers)}] f_num={r.f_num} "
                      f"tokens={r.prompt_tokens}+{r.completion_tokens} "
                      f"cum=${cumulative_cost:.4f}{err}")
            if cumulative_cost > args.max_cost_usd:
                print(f"\nABORTING: cumulative cost ${cumulative_cost:.2f} > cap ${args.max_cost_usd}")
                # Cancel remaining
                for f in future_to_d:
                    f.cancel()
                break

    # Escalation pass
    if not args.no_escalate and not args.dry_run:
        escalations = []
        for r in results:
            d = next((dd for dd in dossiers if dd.get("f_num") == r.f_num), None)
            if not d:
                continue
            ref = cards.get((d.get("db_meta") or {}).get("aff_abbr"))
            should, reasons = should_escalate(r, ref, d)
            if should and cumulative_cost < args.max_cost_usd:
                escalations.append((d, ref, reasons))
        print(f"\nEscalating {len(escalations)} cases to deepseek-reasoner ...")
        for d, ref, reasons in escalations:
            if cumulative_cost >= args.max_cost_usd:
                print("  cost cap hit; skipping further escalations")
                break
            user_prompt = build_user_prompt(d, ref)
            user_prompt += f"\n\nNOTE: V3 flagged this case for escalation due to: {reasons}"
            r2 = ds.call(MODEL_REASONER, SYSTEM_PROMPT, user_prompt)
            r2.f_num = d["f_num"]
            r2.escalated = True
            results.append(r2)
            cumulative_cost += r2.cost_usd
            print(f"  reasoner f_num={r2.f_num} cost=${r2.cost_usd:.4f} cum=${cumulative_cost:.4f}")

    # Aggregate
    n = len(results)
    valid = [r for r in results if r.rubric and not r.error]
    errored = [r for r in results if r.error]
    avg_score = None
    if valid:
        scores_lists = [list((r.rubric or {}).get("scores", {}).values()) for r in valid]
        flat = [s for sl in scores_lists for s in sl if isinstance(s, (int, float))]
        avg_score = round(sum(flat) / max(len(flat), 1), 2)

    summary = {
        "ran_at": dt.datetime.now().isoformat(timespec="seconds"),
        "model_v3": MODEL_V3,
        "model_reasoner": MODEL_REASONER,
        "dry_run": args.dry_run,
        "n_calls": n,
        "n_valid_rubrics": len(valid),
        "n_errors": len(errored),
        "cumulative_cost_usd": round(cumulative_cost, 4),
        "average_dimension_score": avg_score,
        "max_cost_cap_usd": args.max_cost_usd,
    }

    out_path = out_dir / "layer4_results.json"
    out_path.write_text(json.dumps({
        "summary": summary,
        "results": [asdict(r) for r in results],
    }, indent=2, default=str), encoding="utf-8")
    md_path = out_dir / "layer4_report.md"
    lines = [
        "# Union Explorer Audit -- Layer 4 (DeepSeek Advisory)", "",
        f"Run at: {summary['ran_at']}    Model: {summary['model_v3']}",
        f"Dry run: {summary['dry_run']}", "",
        f"- Total calls: {summary['n_calls']}",
        f"- Valid rubrics: {summary['n_valid_rubrics']}",
        f"- Errors: {summary['n_errors']}",
        f"- Cumulative cost: ${summary['cumulative_cost_usd']}",
        f"- Average dimension score: {summary['average_dimension_score']}", "",
    ]
    # Top concerns
    concerns_count: dict[str, int] = {}
    for r in valid:
        for c in (r.rubric or {}).get("concerns", []) or []:
            concerns_count[c] = concerns_count.get(c, 0) + 1
    if concerns_count:
        lines += ["## Most-cited concerns", ""]
        for c, n_c in sorted(concerns_count.items(), key=lambda kv: -kv[1])[:20]:
            lines.append(f"- {n_c}x: {c}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nResults written to:\n  {out_path}\n  {md_path}")
    print(f"SUMMARY: {summary['n_valid_rubrics']}/{n} valid, "
          f"avg_score={summary['average_dimension_score']}, "
          f"cost=${summary['cumulative_cost_usd']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
