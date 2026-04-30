# Genesis Procedural Forest Generator

Procedural forest generation pipeline: **Genesis Physics** → **OpenUSD** → `usdrecord` → **fly-through video**. Colored materials, cinematic camera paths, and GPU-accelerated terrain + entity placement.

```
Genesis (physics + GPU raycast)
         │
         ▼
  OpenUSD stage (.usdc) + UsdPreviewSurface materials
         │
         ▼
  usdrecord + ffmpeg → MP4 video
```

## Quick Start

```bash
# Install dependencies
pip install genesis-world numpy scipy noise torch

# Generate forest + render fly-through
cd genesis_forest
python -m examples.forest_video

# Or use the Gradio UI
python -m gradio_app.app
# → http://localhost:7860
```

## Commands

```bash
# Generate to binary USD
uv run --with genesis-world,numpy,scipy,noise,torch,usd-core,trimesh \
  python -m examples.simple_forest

# Render a single frame
usdrecord forest_output.usdc frame.png -w 1280 --renderer=Metal

# Render fly-through video (requires ffmpeg)
uv run --with genesis-world,numpy,scipy,noise,torch,usd-core \
  python -m examples.forest_video
```

## Architecture

```
1. build_terrain_genesis()
     └── Genesis Terrain morph from Perlin noise heightfield

2. place_entities_genesis()
     └── Place tree/rock/bush entities at Z=100 (above terrain)

3. raycast_heights()
     └── scene.raycast_batch() — GPU-parallel batched raycast
         Drops entities onto terrain surface

4. build_usd_stage()
     └── Query final transforms from Genesis entities
         Write mesh prims with UsdPreviewSurface materials to USD
         Add 3x DistantLight + camera for rendering
```

## Features

- **Terrain**: Perlin noise heightfields with configurable roughness
- **Forest**: Birch, Spruce, Pine trees with density/age parameters
- **Rocks & Vegetation**: Rocks, Bushes, Blueberries — randomized placement
- **Colored Materials**: UsdPreviewSurface with per-type diffuse colors
- **Cinematic Camera**: Catmull-Rom spline fly-through with figure-8 or linear paths
- **Video Rendering**: usdrecord + ffmpeg → MP4 (supports Metal, Storm, Embree renderers)
- **Gradio UI**: Web interface for parameter tuning
- **UE5 Export**: Binary USD with Lumen + Nanite support

## Module Reference

| Path | Purpose |
|------|---------|
| `backend/forest_generator.py` | `ForestGenerator`: terrain → place → raycast → USD |
| `backend/terrain.py` | Perlin noise terrain → heightfield + trimesh |
| `backend/tree_placement.py` | Placement logic + GPU batched raycast |
| `backend/usd_stage.py` | USD stage: meshes, materials, camera, lighting |
| `backend/fly_camera.py` | FlyCamera, PathFlyCamera, video rendering |
| `examples/forest_video.py` | Generate forest + render fly-through video |
| `examples/ue5_export.py` | Optimized export for UE5 |
| `examples/simple_forest.py` | Minimal generation example |
| `gradio_app/app.py` | Gradio web UI |

## Renderers

| Renderer | Platform | Notes |
|----------|----------|-------|
| Metal | macOS | Default, GPU-accelerated |
| Storm | All | OpenGL-based |
| Embree | All | CPU-based |

## Hardware Support

Genesis auto-detects: **NVIDIA CUDA** → **AMD ROCm** → **Apple Metal** → **CPU fallback**.

## Legacy

The original Isaac Sim extension is preserved in `exts/company.hello.world/` for reference. The core pipeline was rewritten for Genesis with GPU batched raycasting and standalone OpenUSD rendering.

## UE5 Import

```bash
python -m examples.ue5_export
# In UE5:
#   1. Enable USDImporter plugin
#   2. File → Import into Level → forest_ue5.usdc
#   3. Rendering: Lumen + Nanite + Virtual Shadow Maps
```

## License

MIT — see [LICENSE](LICENSE).
