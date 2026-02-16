# API Security Fixes (2026)

## Scope note
The requested file `api/labor_api_v6.py` is not present in this repository. The active API is split across `api/routers/*.py` and mounted by `api/main.py`.

This review covers database query patterns in those active router files.

## Summary
- Most queries are parameterized for values (`%s` + params), which is good.
- Main risk area: dynamic SQL identifiers/clauses built with f-strings.
- I did not find a confirmed live exploit path in current code, but these are **high-risk patterns** and should be hardened.

## High-risk query patterns and safer replacements

### 1) Dynamic table name interpolation
- File: `api/routers/organizing.py:1156`
- Endpoint: `GET /api/admin/match-quality`
- Problematic code:
```python
cur.execute(f"SELECT COUNT(*) FROM {tbl}")
```
- Risk in plain language: if `tbl` ever comes from user input (now or in future edits), someone could inject SQL and read or change data.

Safer version:
```python
from psycopg2 import sql

ALLOWED_TABLES = {
    "osha_establishments",
    "whd_cases",
    "mergent_employers",
    "gleif_us_entities",
}

if tbl not in ALLOWED_TABLES:
    raise HTTPException(400, "Invalid table")

cur.execute(
    sql.SQL("SELECT COUNT(*) FROM {}")
       .format(sql.Identifier(tbl))
)
```

### 2) Dynamic view name interpolation
- File: `api/routers/sectors.py:151`, `api/routers/sectors.py:160`, `api/routers/sectors.py:187`, etc.
- Endpoint family: `/api/sectors/{sector}/...`
- Problematic pattern:
```python
cur.execute(f"SELECT * FROM {view_name}")
```
- Risk in plain language: this is safe only while `view_name` remains tightly controlled. If a future change weakens the mapping, it can become SQL injection.

Safer version:
```python
from psycopg2 import sql

if sector_key not in SECTOR_VIEWS:
    raise HTTPException(404, "Sector not found")

view_name = f"v_{SECTOR_VIEWS[sector_key]}_organizing_targets"

cur.execute(
    sql.SQL("SELECT * FROM {} WHERE id = %s")
       .format(sql.Identifier(view_name)),
    [target_id],
)
```

### 3) Dynamic WHERE fragment interpolation
- File examples: `api/routers/employers.py:296`, `api/routers/vr.py:107`, `api/routers/whd.py:109`, many others
- Endpoint family: search/list endpoints
- Problematic pattern:
```python
cur.execute(f"SELECT COUNT(*) FROM ... WHERE {where_clause}", params)
```
- Risk in plain language: this is currently composed from trusted fragments, but if any raw user text is appended later, injection becomes possible.

Safer pattern:
```python
clauses = []
params = []

if state:
    clauses.append(sql.SQL("state = %s"))
    params.append(state.upper())

where_sql = sql.SQL(" AND ").join(clauses) if clauses else sql.SQL("TRUE")

query = sql.SQL("SELECT COUNT(*) FROM my_table WHERE {}" ).format(where_sql)
cur.execute(query, params)
```

### 4) Dynamic ORDER BY interpolation
- File examples: `api/routers/museums.py:83`, `api/routers/sectors.py:163`, `api/routers/density.py:673`
- Problematic pattern:
```python
ORDER BY {sort_by} {order_dir}
```
- Risk in plain language: if `sort_by` or `order_dir` is not strictly validated, attackers can inject SQL through sorting fields.

Safer version:
```python
ALLOWED_SORT = {
    "total_score": sql.Identifier("total_score"),
    "employer_name": sql.Identifier("employer_name"),
}
sort_expr = ALLOWED_SORT.get(sort_by, sql.Identifier("total_score"))
order_expr = sql.SQL("DESC") if sort_order == "desc" else sql.SQL("ASC")

query = sql.SQL("""
SELECT *
FROM v_museum_organizing_targets
WHERE {where_sql}
ORDER BY {sort_col} {sort_dir}
LIMIT %s OFFSET %s
""").format(where_sql=where_sql, sort_col=sort_expr, sort_dir=order_expr)

cur.execute(query, params + [limit, offset])
```

## Immediate hardening checklist
1. Replace dynamic identifier f-strings with `psycopg2.sql.Identifier`.
2. Keep strict allowlists for sortable columns and view/table names.
3. Add a lint/check script that flags `cur.execute(f"` usage in API routers.
4. Add regression tests for malicious sort/table/view inputs.
