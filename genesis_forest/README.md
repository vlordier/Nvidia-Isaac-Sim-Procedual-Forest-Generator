# Genesis Forest Generator

Procedural forest generation: **OpenUSD** + **Genesis Physics** + **Gradio UI** + **UE5 Rendering**.

```
Gradio UI  ────►  Python Backend  ────►  Genesis (physics + GPU raycast)
                                       │
                                       ▼
                               OpenUSD stage (.usdc)
                                       │
                                       ▼
                               UE5 (Lumen + Nanite)
```

## Installation

```bash
pip install genesis-world gradio numpy scipy noise
# Optional: for OpenUSD Python bindings (alternative to Isaac Sim's pxr)
pip install usd-core
```

Genesis auto-detects hardware: **NVIDIA CUDA** → **AMD ROCm** → **Apple Metal** → **CPU**.

## Quick Start

```bash
cd genesis_forest
python -m examples.simple_forest
# → forest_output.usda
```

```bash
python -m gradio_app.app
# → http://localhost:7860
```

## Architecture

### Genesis-authoritative pipeline

```
1. build_terrain_genesis()
     └── Genesis Terrain morph from LOCAL mesh coords
         (mesh_to_heightfield gets local verts, Genesis applies world pos)

2. place_entities_genesis()
     └── Place tree/rock/bush entities at Z=100 (high above terrain)
         Each entity = gs.morphs.URDF loaded asset

3. raycast_heights()
     └── scene.raycast_batch() — GPU-parallel batched raycast
         Updates entity Z positions in-place

4. build_usd_stage()
     └── Query final transforms from Genesis entities
         Write prims to OpenUSD stage with correct ground Z
```

### Why Genesis is authoritative

The original Isaac Sim code did sequential Python-raycast → Python-list-update → USD-write.
Genesis lets us run GPU batched raycasts across all placements simultaneously,
then query the corrected world transforms directly from the physics engine.
The USD file reflects exactly what Genesis simulated.

### Key fixes vs naive port

| Issue | Fix |
|-------|-----|
| `layer.Import()` wrong for USD refs | `refs.AddReference(usd_path)` |
| Terrain double-offset | `mesh_to_heightfield` gets LOCAL coords; world pos via Genesis `pos=` |
| Sequential O(n) raycasts | `scene.raycast_batch()` GPU parallel |
| CPU-only backend | `_detect_genesis_backend()` → cuda/amdgpu/cpu |
| Blocking UI | `gr.Progress()` for live feedback |
| `.usda` for UE5 | `.usdc` (binary) default — 10× faster load |
| USD stage disconnected from Genesis | Query `entity.get_pos()` / `entity.get_quat()` after raycast |

## Module reference

| File | Role |
|------|------|
| `backend/forest_generator.py` | `ForestGenerator`: terrain → place → raycast → USD |
| `backend/terrain.py` | Perlin noise terrain → heightfield + trimesh (local coords) |
| `backend/tree_placement.py` | Placement logic + `batch_raycast_heights()` |
| `backend/usd_stage.py` | OpenUSD stage: `AddReference()`, prim transforms |
| `gradio_app/app.py` | Gradio UI with `gr.Progress()` |

## UE5 import

```bash
# Generate binary USD
python -m examples.ue5_export

# In UE5:
#   1. Enable USDImporter plugin (built-in)
#   2. File → Import into Level → forest_ue5.usdc
#   3. Project Settings → Rendering:
#        Dynamic Global Illumination: Lumen
#        Nanite: Enabled
#        Virtual Shadow Maps: Enabled
```

## Limitations

- `scene.raycast_batch()` availability depends on Genesis version — fallback to sequential if unavailable
- HDR dome lighting (from `omni.replicator`) has no Genesis equivalent; recreate in UE5
- Live physics sync Genesis↔UE5 not implemented (static USD export only)

## License

MIT — same as original repository.
