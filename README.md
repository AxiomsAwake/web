# Axioms Awake Gaming — public web distribution

One public publishing repository; independent game folders; one assembled-site deployment.

**Catalogue:** https://axiomsawake.github.io/web/

Source repositories keep their code, engines, tests and private archives. They publish only deliberately selected browser outputs here. Updating one game does not rebuild the others, replace their files, or require another public repository.

## What is implemented

A source workflow builds/tests its game. Its successful main run starts the source's `Publish browser output` workflow, which calls the reviewed common action at an immutable commit. The action verifies the exact run and source ancestry, downloads its exact public artifact ID, reads `web-publish.json` from the tested source SHA, stages only selected files, and checks the actual `/web/<site>/` prefix in Chromium. Only then does it promote the owned folder.

The publisher can change only `site/<registered-id>/**` and `releases/<registered-id>.json`. It retries real Git conflicts by fetching current main and reapplying only its own output. It never force-pushes. Older source releases cannot overwrite newer accepted ones. Duplicate source SHA/digest is a no-op. Failed builds leave accepted bytes intact.

The destination Pages workflow assembles all current accepted folders into `_site/`, generates the catalogue, uploads one complete artifact, and verifies public deployment/sub-site identities. It does not install or build every game's engine. Deployments are serialized; each acquires current main after its slot starts, so coalesced deployments include accepted publications from other games.

The credential is restricted to this repository, but **GitHub does not grant Contents write by subdirectory**. Folder ownership is enforced by the reviewed helper and tests for trusted producers, not a sandbox against malicious maintainers who possess the destination credential. Do not grant it to untrusted repositories.

| Site ID / public folder | Source repository | Source build | Exact artifact |
| --- | --- | --- | --- |
| `little-lines` | `AxiomsAwake/LittleLines` | `verify.yml` | `public-site` |
| `axis` | `AxiomsAwake/InterdimTicTacToe` | `verify.yml` | `axis-candidate`, selected standalone files only |
| `romi16` | `AxiomsAwake/Romi16` | `ci-cd.yml` | `romi16-site-<sha>` |
| `earth-sim` | `AxiomsAwake/CompBioEarthSim` | `ci.yml` | `compbio-earth-sim-<sha>` |
| `crispery-room` | `AxiomsAwake/CrisperyRoom` | `game.yml` | Selected player/model from `reusable-escape-room-v3` |
| `the-keepers` | `AxiomsAwake/TheKeepers` | `web-build.yml` | `public-web` |
| `living-worlds` | `AxiomsAwake/LivingWorlds` | Reserved, disabled | Requires a dedicated approved `public-web` package |

Only accepted active releases appear in the catalogue. A registry entry is not a claim of a live release. LivingWorlds' private concept handbook/source archive is deliberately not published.

## One-time publishing credential

Choose **one** of the following. Existing source workflows already read these exact names; no game code needs editing. Never paste a key/token into chat, source, a URL or a workflow YAML literal.

### Recommended: a small GitHub App

Create an organization-owned GitHub App (for example `Axioms Awake Web Publisher`) in the organization's developer settings. It needs repository **Contents: Read and write** and the implicit Metadata read permission. No webhook, OAuth callback, source-repository access, administration permission or workflow-file write permission is needed for this publisher.

Install that App on **only `AxiomsAwake/web`**. Generate its private key and retain it securely. In each approved source repository, under **Settings → Secrets and variables → Actions**, configure:

| Type | Name | Value |
| --- | --- | --- |
| Actions variable | `WEB_PUBLISH_APP_ID` | The App ID accepted by the pinned token action |
| Actions secret | `WEB_PUBLISH_APP_PRIVATE_KEY` | The generated PEM private key |

The common action mints a short-lived installation token restricted to `web` and Contents write. Source workflow/API reads use that source's ordinary `GITHUB_TOKEN` with Contents/Actions read, not the App key.

Organization-level variables/secrets can instead be exposed to a selected list of these source repositories when the organization plan supports it. **GitHub Free does not expose organization-level Actions secrets or variables to private repositories**: use repository-level entries with the same names in that case. Do not put these only in an environment, because the source publishing jobs do not select such an environment.

### Alternative: a fine-grained personal access token

Create a fine-grained token with resource owner `AxiomsAwake`, repository selection **only `web`**, and repository **Contents: Read and write**. Complete any required organization approval. Store it as repository Actions secret **`PUBLIC_RELEASE_TOKEN`** in the approved source repositories. Use an expiration/rotation policy. This is the bootstrap alternative, not a requirement to configure both methods.

Do not replace it with the source `GITHUB_TOKEN`: that token is scoped to its source repository and ordinary pushes made with `GITHUB_TOKEN` do not trigger downstream push workflows. App/PAT-authenticated source-to-web commits do trigger the destination Pages workflow. The management workflow below uses an explicit dispatch for its own `GITHUB_TOKEN` commits.

### Local CLI alternative for placing an App credential

After independently creating/installing the App, the owner can use an already authorized `gh` CLI to set repository-level entries without putting the secret in command history. This is an optional local setup helper, not a command that was run by the implementation:

```bash
set -euo pipefail
read -r -p 'Publishing App ID: ' APP_ID
read -r -p 'Local path to the protected App PEM file: ' KEY_FILE
test -r "$KEY_FILE"
for repo in LittleLines InterdimTicTacToe Romi16 CompBioEarthSim CrisperyRoom TheKeepers; do
  gh variable set WEB_PUBLISH_APP_ID --repo "AxiomsAwake/$repo" --body "$APP_ID"
  gh secret set WEB_PUBLISH_APP_PRIVATE_KEY --repo "AxiomsAwake/$repo" < "$KEY_FILE"
done
```

This loop sets only the publishing-specific names. It does not change unrelated tokens or give the App access to private sources. Add LivingWorlds only when its public package is enabled. Keep/delete the local key according to your secret-storage policy; never commit it.

## Pages, Actions and branch settings

**Pages has already deployed successfully with this architecture**: initial unified deployment run `34397372073` at commit `43ff81b0dbbfd3428cfcf31cc050db3cb5ca30a5` included the catalogue and the existing Little Lines release moved byte-for-byte into its folder. That was serving acceptance, not a new full gameplay test of the bootstrap release.

Retain these settings for smooth operation:

- In **web → Settings → Pages**, the source is **GitHub Actions**, not a branch/folder builder. No custom domain is necessary.
- The `github-pages` environment must permit `main`. Recurring human deployment approval would intentionally interrupt automatic publication; do not add it unless that is desired. The workflow declares `pages: write` and `id-token: write` only where needed.
- Actions policy must permit the pinned `AxiomsAwake/web` action, its referenced GitHub actions, and existing game build actions. Do not enable secrets for untrusted pull requests. Publication admits only successful trusted main builds.
- Any `web/main` ruleset must permit the publishing identity's non-force commits. If required-PR rules are added, use a narrowly appropriate App bypass or redesign the promotion permission; do not disable all protections or grant source workflows administrative power. Management operations also need permission for their own GitHub Actions identity to commit.
- GitHub-hosted runners serve the central deployment and most sources. Little Lines intentionally retains its ordinary-user **self-hosted** source build/publish policy. Its runner/group must be authorized for the transferred `AxiomsAwake/LittleLines` repository, have Python 3.10+ and venv plus browser prerequisites, and retain `RUNNER_TOOL_CACHE`. The shared action never installs system dependencies or elevates privileges on self-hosted runners.
- Optional variable `WEB_BASE_URL` overrides the public base URL for producer live checks. Leave it unset for the default Pages URL. A domain change is a serving change, not a new public repository requirement.

The implementation connection can edit source/workflows and inspect runs, but it does not supply the owner's App key/PAT. Successful Pages deployment is not evidence that every source has its publication credential configured.

## First publication and retries

Push a relevant main change after setup, or use a successful retained source run that already contains `web-publish.json`. Normal updates publish automatically. No release PR, tag or second manual click is required after onboarding.

After a credential/network fix, rerun the failed **Publish browser output** job. Alternatively select that workflow's **Run workflow**, keep branch `main`, and enter the **successful source build run ID** (not the failing publication run ID). This reuses its exact artifact; it does not rebuild the game. If an artifact expired, make a fresh source build. An older source run that predates the publication manifest is deliberately not eligible.

A source build failure, missing artifact, path error, browser failure or missing credential is reported as a failure, never silently described as published. `published` means committed to `web`; the following serving check must show `live` or an explicitly newer/restore disposition before calling it served. After a prolonged Pages failure, rerun the destination deployment and then the source publication job if a fresh verified report is needed.

## Redeploy, rollback and unpublish

In this repository's Actions tab:

**Deploy all public sub-sites → Run workflow** redeploys currently accepted files without building any games.

**Manage one public sub-site → Run workflow** supports:

| Operation | Effect |
| --- | --- |
| `redeploy` | Dispatch Pages without changing published files. |
| `restore` | Restore only the selected site's accepted files from a supplied full **web commit SHA**. Preserve its newest accepted-source watermark so an old queued build cannot undo that explicit restore. New source descendants remain eligible. |
| `unpublish` | Remove that site's current files and suspend its publisher. Retain a tombstone/order record so a queued publication cannot immediately recreate it. |
| `resume` | Lift suspension. A new eligible source release or an explicit restore is still needed to make the site active again. |

Management uses this repository's own token, then explicitly dispatches Pages because ordinary `GITHUB_TOKEN` pushes do not trigger another push workflow. Check the separately dispatched Pages run for completion. Management never rewinds other games or force-pushes history. Do not use an older source-repository SHA as a web restore commit.

Unpublishing or hiding a catalogue listing does **not** erase Git history, cached public bytes or copies already downloaded. Do not publish confidential material and rely on later unpublishing for secrecy.

## Onboard another game, demo or showcase

Add a unique site ID and producer/workflow/artifact mapping to `catalog/sites.json`; the producer may belong to another explicitly trusted organization. One producer can own multiple separately registered sites. Registry/hosting changes are maintainer changes, not part of a game payload.

In the source, produce a tested artifact and add `web-publish.json`:

```json
{
  "schema": 1,
  "site": "example-game",
  "enabled": true,
  "files": [{"from": ".", "to": "."}],
  "smoke": {"ready_selector": "#play", "steps": [{"click": "#play"}], "touch": true}
}
```

Use the `.` mapping only for an explicitly public-only artifact. Mixed CI archives need explicit file mappings, as in AXIS and CrisperyRoom. Supporting notices can be selected with `source_files` from the exact tested source SHA. All games need `index.html` and complete runtime-required files. Test at the eventual subfolder; relative assets are preferable. `smoke` checks are additional startup/declared interaction/reload checks, not replacements for game tests or physical-device certification.

Copy a working source publication wrapper, change its source workflow name and site ID, and pin the shared action to a reviewed web commit that contains the new registry entry. Grant that source its publishing credential. Ordinary future main releases then need no host-side intervention. The action is deliberately version-pinned; changes to shared code or new registry entries require a reviewed pin update, not a moving unreviewed reference.

Deliberately public JS/HTML/scripts, images, models, audio and downloadable artifacts are legitimate. Do not copy entire private checkouts, original room photos, research/session archives, secrets, developer source maps or mixed evidence wholesale. Preserve each game's actual credits/license notices. There is no new umbrella game license here.

Scope localStorage, IndexedDB names, caches and service workers by project. Subdirectories share an origin: these names avoid accidental cross-game interference, not hostile same-origin access. No catalogue-wide worker or blanket storage reset is introduced. Keep offline capabilities where games actually provide them; CDN-dependent output is not automatically offline.

## Capacity and tests

Current conservative guards: 90 MiB per file, 250 MiB per sub-site, 900 MiB combined current serving payload, and 5,000 files per sub-site. GitHub Pages currently limits the published site to 1 GB and has a soft 100 GB/month bandwidth allowance. Normal Git rejects files over 100 MiB; LFS pointers are not a Pages asset-serving solution. Monitor Git history growth separately from the current serving tree. Do not copy every historical build or native installer into this repository. If actual traffic/headers/commercial-hosting needs outgrow Pages, retain this producer contract and change the final serving adapter rather than multiplying public mirrors.

```bash
python3 -m unittest discover -s tests -v
python3 tools/publish.py assemble --output _site --commit "$(git rev-parse HEAD)"
```

The regression suite uses real local Git repositories and simultaneous pushes, not a mocked claim of collision protection. Infrastructure CI also performs desktop and touch-sized Chromium fixture interactions/reload at the subpath. Initial green run: `34396933187`, commit `94c6b945b9f7e5895db2b7aa83fa2841e6882627`. Game-specific source/production acceptance must be checked separately.

## Old publishing repositories

Source automation now targets this repository. After each replacement is accepted, disable obsolete Pages serving and privately retire `Romi16-play` and `TheKeepersGame-Web`; public archiving alone is not the single-public-publisher end state. Disable EarthSim's old source-repository Pages site as well. Do not delete recovery history or change unrelated public/open-source projects. Repository visibility and old Pages settings require an authorized administrative action; this README does not claim they have already changed.

## Official references

Checked 2026-09-09; configuration UI and plan entitlements may change.

- GitHub App authentication in Actions: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/making-authenticated-api-requests-with-a-github-app-in-a-github-actions-workflow
- Actions secrets and private-repository organization-secret limits: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- GITHUB_TOKEN scope and workflow-trigger exceptions: https://docs.github.com/en/actions/concepts/security/github_token
- Fine-grained personal access tokens: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- Custom Pages workflows: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- Pages limits: https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
- Large files: https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github
- Browser storage scope: https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API
