# Small producer requests, exact publication, useful failure evidence

The common publisher remains the only promotion owner. A game can expose a commit-based request front door when its chat tools lack Actions dispatch; that front door must still resolve an exact trusted-main producer run and call this pinned action. It must not manufacture an action success, bypass browser checks, copy a whole source tree or grant a model publishing credentials.

## Browser routes

The optional `smoke.routes` array adds up to eight named query-only routes to the default entry point. Each retains the same origin and owned path. Example:

```json
{"name":"editor","query":{"workspace":"editor"},"steps":[{"click":"#canvas"}]}
```

Base readiness, hidden-loader, touch and assertion policy are inherited. Interaction steps are explicit per route; gameplay-only shortcuts are not sent to arbitrary editors. Runtime JavaScript exceptions, genuine engine `console.error` messages, missing same-origin files and reload errors fail the smoke. Explicit `WARNING:` stderr lines are not promoted to errors. A visible canvas alone is not enough to dismiss engine errors.

Reports include route, viewport, cold boot, warm reload and screenshot duration. They are real Chromium execution, not native PCK tests, but still do not prove full game semantics, touch gesture completeness, physical-GPU frame time or human acceptance. Optional screenshots retain their existing five-second compositor bound.

## Avoid repeated setup and lost evidence

The exact existing Playwright version is reused from a Python-version-keyed ordinary-user runner environment. Preparation is locked, all subprocesses are bounded, and the upstream browser installer reuses its pinned browser revision. Job payloads remain isolated; destination credentials are not exposed to browser execution. The credentials-presence check happens before package download and browser installation. Token validity is still established by the actual authorized operations, not guessed from presence.

Release-asset browser reports and images are copied to runner evidence storage before temporary payload removal. Failure reports are written even when a later route fails. Other producers retain their existing artifact evidence path. Source/tag/digest/ancestry checks, per-game path ownership, no-op/stale publication, non-force conflict retries and final serialized serving verification are unchanged.

`Publishing infrastructure` runs the actual default and additional routes at desktop/touch size, checks cache reuse, and deliberately emits a console error to prove the negative gate. Do not pin a producer to a new shared revision until its tests pass.
