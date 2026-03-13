# R3-1: ActionLog Collapse (2026-03-04)

## What was done
Refactored `frontend/src/features/research/ActionLog.jsx` from a flat table to a 3-category layout:

1. **Summary bar** (always visible when card expanded): "3/6 tools found data | 1 error | 1.0s total"
2. **Found-data rows**: full 6-column table, only tools where `data_found && !error_message`
3. **Error rows**: full table with `text-destructive` styling and `AlertTriangle` icon
4. **Not-found collapse**: single expandable line with tool count + preview names, click to expand compact list (tool name + latency)

CollapsibleCard summary updated: `"6 tools called -- 3 found data, 1 error"`

## Files changed
- `frontend/src/features/research/ActionLog.jsx` -- rewritten (55 -> ~115 lines), split into 3 sub-components: `ActionLog`, `ActionTable`, `NotFoundSummary`
- `frontend/__tests__/ActionLog.test.jsx` -- NEW, 9 tests
- `frontend/__tests__/ResearchResult.test.jsx` -- updated MOCK_RESULT.action_log (added not-found + errored actions)

## Test results
- ActionLog.test.jsx: 9/9 pass
- ResearchResult.test.jsx: 13/13 pass (was 12)
- Total frontend: 249 tests, 1 pre-existing failure in SettingsPage (duplicate "osha" text, unrelated)

## Notes
- `CollapsibleCard` with `defaultOpen={false}` does NOT render children -- tests must click header to expand
- Pre-existing SettingsPage test failure: `getByText('osha')` finds multiple elements -- needs `getAllByText` fix (not part of R3-1)
- Not committed yet (user didn't ask)
