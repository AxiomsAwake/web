# Runner evidence lifecycle

`runner_evidence.py` owns bounded immutable local evidence publication. Invoke it
from the producing workflow's completion path, with a stable distinct channel:

```sh
python3 .github/actions/publish-site/runner_evidence.py evidence-directory --channel verification
python3 -B -m unittest discover -s .github/actions/publish-site -p 'test_runner_evidence.py'
```

It defaults to the runner tool cache, twelve previous runs, a seven-day minimum
lifetime, 256 MiB per run and 4 GiB per repository/channel. Expired managed outputs
are pruned while publishing; no schedule is involved. Quota pressure cannot
delete protected or unexpired evidence. Consistently pass `--pin RUN-ATTEMPT` for
retained investigations. Unknown or modified history is preserved and reported.

`--evidence-root` supports the runner's declared shared evidence root. Repeated
`--include` relative paths/globs select files without pre-copying a checkout.
Symlinks, special files, escapes and unbounded incoming copying are rejected.
Original verification results stay in their owning reports; storage failures
are a separate workflow step.

Canonical owner: AxiomsAwake/GameDev `.github/scripts/runner_evidence.py`.
`runner-evidence-origin.json` identifies the admitted shared copy. Change the
owner, run its behavior tests and update identical consumer copies together.
Do not archive whole source trees or infer that unknown scratch is disposable.
