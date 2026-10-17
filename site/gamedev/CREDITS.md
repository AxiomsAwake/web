# Studio asset credits and rights

These are actual animated source assets, imported by Godot as native PackedScenes. Asset rights are per-file; the Studio/repository license does not replace these licenses. No paid assets or services were used. The native setting composition and code are authored for this Studio.

## Alpaca

Quaternius (Tomás Laulhé)

License: **CC0-1.0**. Retained upstream rights source: [alpaca/AUTHORS.txt](alpaca/AUTHORS.txt).

Pinned repository: https://github.com/castle-engine/castle-engine/tree/0c21dcbc42ba9d9d2b605f518cc962068bcf2030

No asset byte changes; instance scaled 0.62 in authored native setting.

- `alpaca/Alpaca.gltf` — SHA-256 `572100e7237b173e874d2c14a5f69a90a4837401efc51ae073f0619e2a7f10fc`
- `alpaca/Alpaca.bin` — SHA-256 `ce14f9911ad649b3e874f5c0214c585489c8b598bc164db95bafe3a41e5d09f3`

## Fox

Model: PixelMannen; rigging and animation: tomkranis; glTF conversion: @AsoboStudio and @scurest.

License: **CC0-1.0 AND CC-BY-4.0**. Retained upstream rights source: [fox-LICENSE.md](fox-LICENSE.md).

Pinned repository: https://github.com/KhronosGroup/glTF-Sample-Assets/tree/edc7c9e67c639d230715049ee31f9a96a6babbbe

The original source is retained unchanged. The wildlife setting selects the
derived `fox-wildlife-authored.glb`, scaled 0.022. AxiomsAwake contributors (2026)
applied two constrained subdivision rounds and smooth normals. Original rig,
clips, embedded markings texture and protected anatomical endpoints are
retained; full derivation, limits and byte identities are recorded in
[fox-wildlife-refinement.json](fox-wildlife-refinement.json). These changes retain
the original CC0-1.0 AND CC-BY-4.0 rights and required attribution. Refinement is
a candidate pending rendered anatomy and motion review.

The authored candidate builds on that retained refined base with bounded
rest-shape changes to cheek, shoulder, haunch, lower limbs, paws and tail.
Only POSITION/NORMAL streams are appended. Original weights, UVs, skeleton,
animation and texture bytes remain unchanged. Exact regeneration, region
measurements, protected landmarks and limitations are recorded in
[fox-wildlife-authoring.json](fox-wildlife-authoring.json). This remains a
candidate pending normal-speed deformation, ground-contact and anatomy review.

The setting additionally composes `fox-wildlife-fur-v1.png` as an external
albedo override on independent instance materials. AxiomsAwake contributors
used the built-in image_gen edit tool to add fine fur detail over the original
atlas layout. The original embedded texture remains unchanged. The exact
prompt, source/output hashes, generated dimensions and inspection limits are
retained in [the fur derivation record](fox-wildlife-fur-v1.json). The original
source rights and attribution above remain applicable; UV seams and native
material appearance require rendered review.

- `fox.glb` — SHA-256 `d97044e701822bac5a62696459b27d7b375aada5de8574ed4362edbba94771f7`
- `fox-wildlife-refined.glb` — SHA-256 `48d16c8003ef601be02565fca627e943c599914821f489beb842a6301719bc5f`
- `fox-wildlife-authored.glb` — SHA-256 `4b5c57d470eb791374f655068af24c5f67653d4f575e789d4f7ec5c3abcf3966`
- `fox-wildlife-fur-v1.png` — SHA-256 `15a84f3242d106fcede1c311cfc703b6e0e34ed568ffd980f91697c79cf1a82c`

## Robot

Tomás Laulhé (Quaternius); facial morph targets and glTF conversion/modifications by Don McCurdy.

License: **CC0-1.0**. Retained upstream rights source: [robot-README.md](robot-README.md).

Pinned repository: https://github.com/mrdoob/three.js/tree/e38bc18ad719622c497de07c5f0cef847aca4bf5

No asset byte changes; instance scaled 0.48 in authored native setting.

- `robot.glb` — SHA-256 `047f5e5fb3bb6d378bd1df16ca6137f2a596c99b3a1b5690b4020c05aaf6f319`

Fox attribution is required by CC-BY-4.0 for rigging, animation and conversion. The Fox model itself is CC0; do not relabel the combined animated asset as entirely CC0. Full attribution metadata is retained in [fox-metadata.json](fox-metadata.json). [CC-BY-4.0 legal terms](https://creativecommons.org/licenses/by/4.0/legalcode), [CC0 legal terms](https://creativecommons.org/publicdomain/zero/1.0/legalcode).

Quaternius original pack: https://quaternius.com/packs/ultimateanimatedanimals.html (CC0). The primary Google Drive download returned quota-exceeded HTML on 2026-10-15; no error HTML was treated as an asset. Alpaca bytes were obtained from the pinned Castle Engine public mirror, whose AUTHORS file links that original pack and explicitly records public-domain rights. The mirrored Alpaca.gltf is the distribution used here; no claim that it is byte-identical to the unavailable original download is made.

RobotExpressive rights follow the model's own README, which identifies CC0 1.0, rather than the three.js code license.

`manifest.json` provides machine-readable sources, rights and byte identities. Audio mood strings in settings describe intended direction only; they are not shipped recordings or listening evidence.

## Woodland material scan

Brown Mud Leaves 01 by **Rob Tuytel / Poly Haven**, **CC0-1.0**. Original
1K JPEG albedo, OpenGL normal and roughness maps are bundled without image edits.
See [material provenance and license](environment/README.md) and
[exact bytes and download URLs](environment/brown-mud-leaves-01/SOURCE.json).

## Original audio cues

The 18 PCM WAV cues under `audio/` were synthesized for the Studio by AxiomsAwake contributors (2026), released under CC0-1.0. These are authored confirmation/impact textures, with no sampled recordings. The setting-specific timbres are wood-like harmonics, filtered earthen noise and electronic resonance.

## Laboratory material scan

Concrete Floor Painted by **Rob Tuytel / Poly Haven**, **CC0-1.0**. Original 1K JPEG albedo, OpenGL normal and roughness maps are bundled without image edits. See [material provenance](environment/README.md) and [exact byte pins](environment/concrete-floor-painted/SOURCE.json).

## Captured woodland environment

Nature Reserve Forest by **Dimitrios Savva (photography), Jarod Guest (processing) / Poly Haven**, **CC0-1.0**. Original 2K Radiance HDR; see [provenance](environment/nature-reserve-forest/SOURCE.json).

## Woodland bark scan

Bark Brown 01 by **Rob Tuytel / Poly Haven**, **CC0-1.0**. Original 1K JPEG
albedo, OpenGL normal and roughness maps, with native cylindrical UVs and
mipmaps. No image edits. See [exact source and byte pins](environment/bark-brown-01/SOURCE.json).
