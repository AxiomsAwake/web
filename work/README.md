# Work

Current work uses the shared `axioms-task/v1` and `axioms-frontier/v1` format.

- [NOW](NOW.md) is the generated current view.
- [Frontier](frontier.json) owns the objective and ordered task references.
- `tasks/<ID>.json` owns task status, dependencies, acceptance, evidence and next action.
- [Project README](../README.md) owns the product context and links to full requirements.

Edit records and frontier, then run `python3 tools/work.py build`; validate with `python3 tools/work.py check`. NOW is derived, and this README is a router, not another queue.

No current approved tasks are recorded. Known limitations and future acceptance contracts do not automatically authorize new implementation work.
