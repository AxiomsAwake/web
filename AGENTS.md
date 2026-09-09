# Public web distribution: agent contract

Work on main without force pushes. This is the only public publishing repository for selected Axioms Awake browser games and cross-project showcases. It is not a game-source monorepo. Read README.md and catalog/sites.json before editing.

A producer owns only site/<registered-id>/** and releases/<registered-id>.json. Use the shared pinned action; never push a whole source checkout, replace all of site/, or run a producer-specific Pages deployment. Shared infrastructure and registry changes are maintainer work, not part of a game's publication payload.

Keep public JavaScript, images, models and deliberately approved artifacts; exclude secrets, source maps, private source archives and unselected research/room photographs. Preserve individual game credits and licenses. This repository does not assign a new umbrella license to its games.

Run python3 -m unittest discover -s tests -v for contract changes. The tests use actual racing Git pushes and cover stale publication, explicit rollback watermarks and unpublish suspension. Keep exact artifact/source identity, explicit selection and bounded conflict retries. Directory ownership is enforced by the trusted publishing helper, not by a GitHub per-directory credential permission.

Pages deploys one complete _site/ snapshot assembled from stored outputs. It never builds all game engines. Keep deployments serialized and resolve current main inside the slot. A public Git commit is not yet a verified live deployment; report actual serving and browser evidence separately.

To restore one game, use the management workflow with a known-good web commit. Preserve its newest accepted-source watermark so an old queued build cannot undo the restore. Unpublish removes current files and suspends future publication; hiding a catalogue entry alone is not privacy. Git history and downloaded public copies remain public even after unpublishing.

Do not change source repository visibility or disclose a private artifact just because this host can serve it. LivingWorlds is registered but disabled until its public package is deliberately prepared. Do not create empty duplicate platforms or impose shared-library extraction on publishing. Record actual commits, test runs and outstanding configuration in the private docs/publishing handoff.
