# Pages transport and storage lifecycle

The shared publisher still owns one game folder per producer. Pages still consumes one complete assembled snapshot; a partial archive would replace, not merge, the site. This optimization removes redundant uploads, not source verification or other games.

`tools/pages_plan.py` fingerprints every actual assembled file, including retained assets and the catalogue. It normalizes only the host commit fields in generated deployment/release sidecars and its own digest field. Game versions, source identities, rollback watermarks, file paths and bytes remain significant. The digest is stamped in `deployment.json`. An identical served digest permits skipping upload only after the existing bounded live checker verifies the served deployment and all sub-site identities at the actual served host commit. Legacy deployments without a digest are updated once. Unavailable live state is never treated as an unchanged success. A matching digest with inconsistent identities fails closed. The manual `force` input deliberately permits an unchanged redeploy.

Test-only edits run infrastructure validation and no longer trigger Pages. The deploy workflow remains serialized and checks out current main inside its slot. The plan writes per-folder bytes, largest files, duplicate-byte groups, retained-generation bytes and avoided raw upload bytes to the job log/report. Reports remain outside the public payload. These counts are raw sizes, not compressed storage billing; duplicate hashes are candidates for inspection, not authority to delete required editor/runtime files.

After deployment AND live verification pass, a separate repository-scoped Actions-write job deletes the uploader's exact `artifact_id`. It verifies artifact name, run and attempt, and confirms absence after DELETE. It cannot delete release packages, other runs or review evidence. Failure leaves the one-day fallback retention and a warning; it does not invalidate serving or start a new build. Cancelled/failed deployments retain their artifact for diagnosis. Producers' game versions and immutable packages are unchanged.

Initial local verification: 18 focused filesystem/HTTP-control tests passed. Full-repository and actual Pages/cleanup results are recorded separately after execution; these local tests are not live serving or gameplay acceptance.

Reproduce focused tests with `python3 -m unittest discover -s tests -p test_pages_transport.py -v`; run the full repository suite before integration. The end-to-end check is one successful deployment followed by an unchanged request: the latter must verify identities, upload zero artifacts and leave all game release identities unchanged.

Do not conflate Actions cache and artifact pools. Dependency cache hygiene in each source repository is separate from this transport lifecycle. Unique evidence and immutable release assets are not disposable caches.
