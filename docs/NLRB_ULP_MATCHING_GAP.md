# NLRB ULP Matching Gap Analysis (Task 5)

Date: 2026-02-18
Database: `olms_multiyear`
Scope: Research only. No updates were made to `nlrb_participants`.

## Participant-Type Coverage Snapshot

| participant_type | total | matched | unmatched |
|---|---:|---:|---:|
| Charged Party / Respondent | 866,037 | 0 | 866,037 |
| Charged Party | 5,688 | 0 | 5,688 |
| Employer | 114,980 | 10,812 | 104,168 |
| Charging Party | 605,638 | 0 | 605,638 |
| Involved Party | 159,903 | 0 | 159,903 |
| Petitioner | 69,677 | 0 | 69,677 |
| All other types combined | 84,619 | 0 | 84,619 |

`Charged%` total rows (ULP respondent-oriented types): **871,725**

## Name+State Matchability Check

Method used:
- Build temp normalized tables with `UPPER(participant_name)` + `UPPER(state)` and join to `f7_employers_deduped` `UPPER(name_standard)` + `UPPER(state)`.
- Filter to `participant_type LIKE 'Charged%'` and `matched_employer_id IS NULL`.

Result:
- Potentially matchable by simple name+state equality: **146** distinct participants

Sample candidate matches indicate some plausible hits (for example, Southern California Gas Company, United Parcel Service), but also obvious false-positive risk in union-name collisions.

## Data Quality Finding (Primary blocker)

Most `Charged%` rows cannot be matched by state because state/city are not populated with real geography:

- `state = ''`: **501,065** rows
- `state = 'Charged Party Address State'`: **370,043** rows
- `city = ''`: **501,065** rows
- `city = 'Charged Party Address City'`: **370,043** rows

This indicates parser/template placeholders are stored as literal values for a large share of ULP participants.

## Recommendation

Run deterministic matching on `Charged%` only **after** a cleanup pass:

1. Replace placeholder city/state tokens with NULL and recover real fields from source payload where possible.
2. Recompute candidate matches with normalized names and fallback keys (name-only, name+city when state missing).
3. Route low-confidence many-to-one name collisions to review queue.
4. Then run deterministic matcher for this participant slice.

Without cleanup, running matcher now will produce low yield and noisy links.
