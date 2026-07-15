# Weekend cleanup — TODO (FIXTURE: ID-less input for the route-plan minting smoke test)

A fictional, ID-less task list. It has no `### U<N>.` headings on purpose — route-plan
must MINT `[U<N>]` markers (writing them back here, behind a consent gate) before routing.
Used by SETUP.md Phase 4c-bis. Mix of full (has a verify command) and bare (no verify) items.

- [ ] Extract the 400 legacy tag strings from `data/tags.csv` into the new normalized enum, one row at a time per the mapping in `docs/tag-map.md`. Verify: 20-row random spot-check matches the mapping + row count in == row count out.
- [ ] Rename the `LegacyExporter` class to `CsvExporter` across the module and update its callers. Verify: `pnpm test exporter` green.
- [ ] Make the settings page feel snappier.
- [ ] Decide whether the export API should be sync-download or async-job-plus-URL, and write the contract.
