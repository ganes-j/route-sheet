---
title: "feat: Add member CSV export (FIXTURE — fictional plan for the SETUP.md smoke test)"
type: feat
date: 2026-03-02
---

# feat: Add member CSV export

Fictional plan for a fictional app. Used by SETUP.md Phase 4c: route these three units under the installed `ROUTING_POLICY.md` and compare your manifest against `expected-routing.md`.

## Implementation Units

### U1. Decide the export API shape

**Goal:** Choose between a synchronous download endpoint and an async job + signed URL, and specify the chosen contract (params, auth, rate limits).
**Files:** `docs/design/export-api.md`
**Approach:** Weigh payload sizes (up to 200k rows) against request-timeout limits; write the decision and contract as the deliverable.
**Test scenarios:** Test expectation: none — design document, no behavioral change.
**Verification:** Contract doc reviewed and approved.

### U2. Implement the CSV export service from the frozen spec

**Goal:** A `MemberExportService` that streams the member table to CSV per the U1 contract, with unit tests.
**Dependencies:** U1.
**Files:** `src/services/member-export.ts`, `src/services/member-export.test.ts`
**Approach:** Frozen spec from U1; mirror the existing `OrderExportService` streaming pattern; no design latitude. Repo `.env` holds localhost URLs and one dev API key only.
**Test scenarios:** happy path (10 rows → valid CSV with header); empty table → header-only file; unicode names round-trip; column order matches contract; error path: DB connection failure surfaces a typed error.
**Verification:** `pnpm test member-export` green.

### U3. Backfill-classify 500 legacy member records into the new `segment` enum

**Goal:** Every legacy member row (NULL `segment`) gets one of {`active`, `lapsed`, `prospect`} written to a review file, derived from last-activity and purchase-count fields per the mapping table in the unit.
**Dependencies:** none.
**Files:** `scripts/backfill-segment.jsonl` (input), `scripts/backfill-segment-out.jsonl` (output)
**Approach:** Mechanical per-row classification against a fixed mapping table; each row independently verifiable; no customer contact data leaves the machine (rows include purchase history — treat as sensitive customer data).
**Test scenarios:** spot-check sample against the mapping table; row count in == row count out; no row with an empty classification.
**Verification:** 20-row random spot-check matches the mapping table 20/20; counts equal.
