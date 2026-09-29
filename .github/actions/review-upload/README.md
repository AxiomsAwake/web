# Optional private diagnostic transfer

This self-contained action runs in the caller's repository. It creates no service, release, deployment or alternate storage account. To avoid a shared-repository download in each test job, vendor its two executable files (`action.yml` and `review_transfer.py`) at a reviewed full commit, record that source and their SHA-256 hashes, and call the local action. Validate those hashes in the consumer. Do not fork the implementation silently. A publisher already loading this repository can also use an exact remote action pin.

The caller retains originals on its trusted runner before calling. Pass `directory` for a report subdirectory under the job workspace or `RUNNER_TEMP`, 1–16 relative `patterns`, a diagnostic `name`, and `enabled` bound to an explicit default-false manual input. The action additionally requires `github.event_name == workflow_dispatch` and the caller's repository variable `CI_REVIEW_UPLOADS_ENABLED=true`. An absent variable disables transfer. Routine pushes, failed tests and a new billing month do not enable it.

Transfers contain at most 96 selected diagnostic files plus their SHA-256 manifest, with a total 16 MiB byte limit including metadata. PNG/JPEG/WebP, MP4/WebM, JSON and text/log files are admitted; executable packages, archives, hidden files, whole-workspace roots, symlinks and traversal patterns are rejected. Overlapping globs copy a file once. Over-budget requests are skipped as a whole, not silently truncated. Narrow the request rather than raising the bound.

One official Actions upload is attempted with one-day retention. A quota failure is nonfatal and reported as transport failure, not a test or inspection result. The disposable staging copy is removed without deleting originals. Do not rerun a game simulation just to retry an upload. Hosted-runner files are not durably retained by this action; callers must state that boundary rather than claim a local path survives the job.

This replaces optional diagnostic uploads, never a package required by another job. Preserve registered release assets and the central Pages transport path. Roll out a new pin only after checking each consumer's dependencies and existing evidence retention.

Focused tests: `python3 -m unittest discover -s tests -p test_review_transfer.py -v`. Full shared publisher validation remains `python3 -m unittest discover -s tests -v`; the existing infrastructure workflow also exercises actual browser readiness and negative controls. Unit tests use synthetic file bytes, not game screenshots or quota availability probes.
