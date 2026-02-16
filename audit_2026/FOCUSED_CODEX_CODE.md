# FOCUSED TASK: Code Architecture & Security Deep Scan — CODEX
# Run AFTER the full audit is complete

You already completed a full audit. Now go deeper on code quality and security specifically.

## TASK 1: API Security Line-by-Line
Read api/labor_api_v6.py completely. For EVERY database query in the file:
1. Is it parameterized (safe) or using string concatenation/f-strings (vulnerable)?
2. List every vulnerable query with: line number, endpoint, the problematic code, and what an attacker could do
3. For each vulnerable query, write the fixed version using parameterized queries
Save to: docs/API_SECURITY_FIXES.md

## TASK 2: Password & Credential Scan
Search EVERY file in the project for:
- Literal password strings (especially "Juniordog33!")
- API keys, tokens, secrets
- The broken pattern: os.environ.get('DB_PASSWORD', '') being passed as a literal string
- .env file contents exposed in version control

For each finding: file path, line number, what the risk is, and the fix.
Save to: docs/CREDENTIAL_SCAN_2026.md

## TASK 3: Matching Module Architecture Review
Read scripts/matching/ completely:
- __init__.py, config.py, normalizer.py, pipeline.py, differ.py, cli.py
- matchers/base.py, exact.py, address.py, fuzzy.py

Assess:
1. Is the architecture well-designed? Could a new matching scenario be added easily?
2. Are there code paths that could produce wrong results? (edge cases in normalization, tie-breaking logic)
3. Is the confidence scoring consistent across tiers?
4. Does the fuzzy matcher handle Unicode and special characters correctly?
5. Are there race conditions or concurrency issues if run in parallel?
6. Error handling — what happens when a match attempt fails?
Save to: docs/MATCHING_CODE_REVIEW.md

## TASK 4: Frontend Architecture Assessment
Read all files in files/ directory:
1. Map the data flow: which JS file talks to which API endpoint
2. Identify all places where scoring values are referenced — are they all using the unified 9-factor system?
3. Find all hardcoded URLs (especially localhost references)
4. The modals.js file is 2,598 lines — identify natural break points where it could be split
5. Count and list all inline onclick handlers
6. Check error handling — when an API call fails, what does the user see?
7. Assess the CSS/styling approach — is it maintainable?
Save to: docs/FRONTEND_CODE_REVIEW.md

## TASK 5: Test Coverage Assessment
Read tests/ directory:
1. What do the 165 tests actually cover?
2. What's NOT covered? (endpoints with no tests, matching scenarios not tested, edge cases)
3. Are there tests that pass but test the wrong thing?
4. Are there fragile tests that depend on specific data?
5. What tests should be added?
Save to: docs/TEST_COVERAGE_REVIEW.md

## TASK 6: Dependency & Environment Assessment
Check requirements.txt and pyproject.toml:
1. Are all dependencies pinned to versions?
2. Are any dependencies outdated or have known vulnerabilities?
3. Is there anything installed that isn't used?
4. Would this project build cleanly from a fresh clone?
Save to: docs/DEPENDENCY_REVIEW.md
