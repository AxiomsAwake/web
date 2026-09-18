# Blockbench browser companion

Upstream: https://github.com/JannisX11/blockbench/tree/574d8a0ae148fc5b36bb52b7bb1f8940022dd079

License: GPL-3.0-or-later; see LICENSE.MD. This is the real upstream editor, not an Axioms-owned modeler.

The exact upstream source, companion scripts, modified HTML, build recipe and bundled-dependency source map are in corresponding-source.zip. Use the included lockfile and `npm ci --ignore-scripts; npm run build-web` to reproduce the upstream bundle. The companion uses the versioned artifact protocol; no game code is linked into this editor.

Modifications: namespaced browser storage and the same-origin project/GLB handoff script, loaded by two added script tags. The loose source-map reference is removed; its complete contents remain in corresponding-source.zip. Editor source and GLB are separate artifacts. Download both from Studio to retain/share your work.
