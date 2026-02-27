# Project State: Labor Research Platform

**Date:** 2026-02-27
**Current Phase:** Phase 2 (Launch Readiness) — items 2.1/2.3/2.4/2.5 done

---

## Completed This Session

### Phase 2.3 — Docker/Deployment
- `frontend/Dockerfile`: Multi-stage build (Node 22 → nginx Alpine)
- `frontend/nginx.conf`: SPA routing + API proxy (replaces legacy `organizer_v5.html`)
- `.dockerignore` (root + frontend): Added
- `docker-compose.yml`: Frontend builds from Dockerfile, API healthcheck, `DISABLE_AUTH=false`
- `Dockerfile` (API): HEALTHCHECK added
- Root `nginx.conf`: Legacy index removed

### Phase 2.4 — Database Cleanup
- 7 unused objects dropped via `scripts/maintenance/drop_unused_db_objects.py`
- 6 "probably safe" tables kept (strategic reference data)
- `scripts/ml/` directory deleted (stale propensity code)

### Phase 2.1 — Propensity Model
- Already killed 2026-02-26. Stale files cleaned up this session.

### Phase 2.5 — Membership Overcounting
- Confirmed already resolved (Jan 2025). Marked in roadmap.

### Research Agent Phase 5.8 (prior session, committed this session)
- Async parallel engine (asyncio.gather), 24 tools (was 18)
- New: solidarity_network, local_subsidies, worker_sentiment, sos_filings, compare_industry_wages
- Address-aware search (company_address field)
- Gold Standard profiles in <45s

### Test Cleanup
- Deleted `test_research_agent_52.py` (tested pre-5.8 functions, all 48 failing/erroring)
- Fixed `test_db_config_migration_guard` (use `get_connection()` in new script)

---

## System State
- **Tests:** 886 backend (0 failures, 3 skipped), 158 frontend (0 failures)
- **Database:** 7 unused objects dropped, all MVs intact
- **Docker:** Production-ready compose (db + api + frontend)
- **Roadmap:** Phase 0 COMPLETE, Phase 1 COMPLETE, Phase 2 items 2.1/2.3/2.4/2.5 DONE

---

## Remaining Phase 2
- **2.2** — Data confidence indicators (match confidence in profiles)
- **2.6** — Launch strategy decision (beta vs read-only vs full transparency)

## Deferred
- Phase 2 re-runs (SAM/WHD/990/SEC with RapidFuzz), grouping quality, master dedup — do NOT prompt until most roadmap is done
