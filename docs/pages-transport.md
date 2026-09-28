# Pages transport and storage lifecycle

The shared publisher still owns one game folder per producer. Pages still consumes one complete assembled snapshot; a partial archive would replace, not merge, the site. This optimization removes redundant uploads, not source verification or other games.

`tools/pages_plan.py` fingerprints every actual assembled file, including retained assets and the catalogue. It normalizes only the host commit fields in generated deployment/release sidecars and its own digest field. Game versions, source identities, rollback watermarks, file paths and bytes remain significant. The digest is stamped in `deployment.json`. An identical served digest permits skipping upload only after the existing bounded live checker verifies the served deployment and all sub-site identities at the actual served host commit. Legacy deployments without a digest are updated once. Unavailable live state is never treated as an unchanged success. A matching digest with inconsistent identities fails closed. The manual `force` input deliberately permits an unchanged redeploy.

Test-only edits run infrastructure validation and no longer trigger Pages. The deploy workflow remains serialized and checks out current main inside its slot. The plan writes per-folder bytes, largest files, duplicate-byte groups, retained-generation bytes and avoided raw upload bytes to the job log/report. Reports remain outside the public payload. These counts are raw sizes, not compressed storage billing; duplicate hashes are candidates for inspection, not authority to delete required editor/runtime files.

After deployment AND live verification pass, a separate repository-scoped Actions-write job deletes the uploader's exact `artifact_id`. It verifies artifact name, run and attempt, and confirms absence after DELETE. It cannot delete release packages, other runs or review evidence. Failure leaves the one-day fallback retention and a warning; it does not invalidate serving or start a new build. Cancelled/failed deployments retain their artifact for diagnosis. Producers' game versions and immutable packages are unchanged.

Reproduce focused tests with `python3 -m unittest discover -s tests -p test_pages_transport.py -v`; run the full repository suite before integration. The end-to-end check is one successful deployment followed by an unchanged request: the latter must verify identities, upload zero artifacts and leave all game release identities unchanged.

Do not conflate Actions cache and artifact pools. Dependency cache hygiene in each source repository is separate from this transport lifecycle. Unique evidence and immutable release assets are not disposable caches.

## Executed verification — 2026-09-28

Implementation source: `58deaaef4e9d92cc1e938f0f78dba16b79c986f4`; explicit Bash/no-op verification source: `eb0a9fefabdeedeaa35e037b4abbab87530f84f6`. Both were integrated on main without changing producer payloads or release identities. The 18 focused filesystem/HTTP-control tests passed locally. A deliberately invalid unconditional-skip mutation produced five test errors; restoration passed again. Those are test-oracle checks, not live results.

| Actual execution | Outcome |
| --- | --- |
| [Initial Pages deployment 36462489286](https://github.com/AxiomsAwake/web/actions/runs/36462489286), deploy job `109064267104` | Full repository tests and assembled deployment passed; all seven sub-site identities verified live. The old served snapshot lacked a fingerprint, so this first migration correctly uploaded once. |
| Same run, cleanup job `109064544138` | Deleted exact newly used artifact `10988407301`, 106,478,805 bytes; the cleanup checked absence after deletion. |
| [Infrastructure run 36462489480](https://github.com/AxiomsAwake/web/actions/runs/36462489480), job `109064268657` | Passed publication/racing-Git contracts, browser fixture, browser-environment reuse, desktop/touch-sized routes and reload, and the negative console-error case. This fixture smoke is not new game acceptance. |
| [Unchanged-content run 36463240292](https://github.com/AxiomsAwake/web/actions/runs/36463240292), job `109066810511` | All 77 repository tests passed. The plan verified the root plus all seven live sidecars, returned `deploy: false`, and upload/deployment were skipped. An independent workflow-artifact read returned an empty list. |
| [Reviewed old-transport cleanup 36463240163](https://github.com/AxiomsAwake/web/actions/runs/36463240163), job `109066809490` | All 18 guards passed, existing live identities verified, three exact successful-run artifacts deleted and absence checked. No release asset or game file removed. |

The unchanged run compared against served host commit `58deaaef4e9d92cc1e938f0f78dba16b79c986f4` rather than pretending its newer request commit had deployed. Relevant retained result fields:

```json
{
  "requested_commit": "eb0a9fefabdeedeaa35e037b4abbab87530f84f6",
  "served_commit": "58deaaef4e9d92cc1e938f0f78dba16b79c986f4",
  "content_sha256": "437302284eb222c8795538952805dd22e110bddc5e222dd7fee7ea6500cf39cc",
  "deploy": false,
  "reason": "identical-verified-live-content",
  "upload_bytes_avoided": 255813663
}
```

`upload_bytes_avoided` measures the raw assembled payload not sent, not a newly measured compressed upload. The preceding same-content migration artifact was about 106.48 MB compressed. No artifact was created by the no-op run. Action runtime-deprecation and a synthetic HTTPError resource warning were observed; these were successful runs, not warning-free claims.

## Focused payload measurements

The verified no-op assembled 443 files, totaling 255,813,663 raw bytes. Studio accounts for 209,012,037 bytes; the player for 41,753,973. The largest file is Studio's bundled terrain editor engine at 100,728,711 bytes, followed by Studio's 44,078,870-byte runtime and the player's 39,514,754-byte runtime. These are required delivered features, not disposable evidence.

Retained-generation data totaled only 202,554 bytes, all in Little Lines. The measured duplicate-byte total was 4,542,795; most came from three equal 2,124,596-byte terrain extension files at distinct editor/project paths. They were not removed: equal bytes do not establish interchangeable paths or permission to break the editor package. This work reduces repeated transmission and retention without deleting required tools, license/source notices or other games.

## Completed one-time cleanup

| Artifact ID | Original successful Pages run | Bytes deleted |
| --- | --- | ---: |
| `10969853553` | `36422809641` | 106,478,754 |
| `10969394591` | `36422794956` | 106,475,246 |
| `10970210893` | `36421756833` | 106,401,899 |
| **Old transport total** | | **319,355,899** |

Each deletion followed exact ID, size, source/run, workflow and completion checks plus current live verification. The temporary `previous-pages-cleanup.yml` was removed after successful execution; its exact source remains in `eb0a9fe` history. The normal `pages.yml` exact-ID cleanup remains active for future successful deployments. The additional 106,478,805-byte automatic cleanup above is separate from these three pre-existing objects, not double-counted.

This source maintenance does not prove organization-wide private artifact/Packages quota recovery or artistic satisfaction. No producer was rebuilt, no game version was advanced, and no review approval was changed.
