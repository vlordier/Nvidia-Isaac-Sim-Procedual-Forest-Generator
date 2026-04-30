# Genesis Forest Generator

Procedural forest generation: **OpenUSD** + **Genesis Physics** + **Gradio UI** + **Video Rendering** + **UE5 Export**.

```
Genesis (physics + GPU raycast)
         │
         ▼
  OpenUSD stage (.usdc) + UsdPreviewSurface materials
         │
         ├──► usdrecord + ffmpeg → MP4 fly-through video
         │
         └──► UE5 (Lumen + Nanite)
```

## Installation

```bash
pip install genesis-world gradio numpy scipy noise torch
# For USD material creation + mesh loading:
pip install usd-core trimesh
```

Genesis auto-detects hardware: **NVIDIA CUDA** → **AMD ROCm** → **Apple Metal** → **CPU**.

## Quick Start

```bash
cd genesis_forest

# Generate forest + render fly-through video
python -m examples.forest_video

# Minimal generation only
python -m examples.simple_forest
# → forest_output.usdc

# Gradio web UI
python -m gradio_app.app
# → http://localhost:7860
```

## Architecture

```
1. build_terrain_genesis()
     └── Perlin noise heightfield → Genesis Terrain morph

2. place_entities_genesis()
     └── Place tree/rock/bush entities above terrain

3. raycast_heights()
     └── GPU-parallel batched raycast drops entities to surface

4. build_usd_stage()
     └── Query Genesis entity transforms
         Write mesh prims with UsdPreviewSurface materials
         Add DistantLight ×3 + camera + lighting
```

## Features

- **Terrain**: Perlin noise heightfields with configurable roughness
- **Trees**: Birch, Spruce, Pine with density/age variation
- **Rocks & Vegetation**: Rocks, Bushes, Blueberries
- **Colored Materials**: UsdPreviewSurface (diffuseColor) per entity type
- **Cinematic Fly-Through**: Catmull-Rom spline paths (figure-8, linear) → MP4
- **Video Rendering**: usdrecord + ffmpeg on Metal/Storm/Embree renderers
- **Gradio UI**: Web interface with live progress

## Module Reference

| File | Role |
|------|------|
| `backend/forest_generator.py` | `ForestGenerator`: terrain → place → raycast → USD |
| `backend/terrain.py` | Perlin noise terrain → heightfield + trimesh |
| `backend/tree_placement.py` | Placement logic + GPU batched raycast |
| `backend/usd_stage.py` | USD stage: meshes, UsdPreviewSurface materials, camera, lighting |
| `backend/fly_camera.py` | FlyCamera, PathFlyCamera, preset paths, ffmpeg video encoding |
| `examples/forest_video.py` | Generate forest + render fly-through video |
| `examples/ue5_export.py` | Optimized forest export for UE5 |
| `examples/simple_forest.py` | Minimal forest generation |
| `gradio_app/app.py` | Gradio web UI |

## UE5 Import

```bash
python -m examples.ue5_export
# In UE5:
#   1. Enable USDImporter plugin
#   2. File → Import into Level → forest_ue5.usdc
#   3. Rendering: Lumen + Nanite + Virtual Shadow Maps
```

## Limitations

- `scene.raycast_batch()` availability depends on Genesis version
- Live physics sync Genesis↔UE5 not implemented (static USD export only)

## License

MIT — see [LICENSE](../../LICENSE).
