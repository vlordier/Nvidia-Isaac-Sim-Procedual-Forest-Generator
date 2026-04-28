# Genesis Forest Generator

Procedural forest generation using **OpenUSD** + **Genesis Physics** + **Gradio UI** + **UE5 Rendering**.

```
┌──────────────────────────────────────────────────────────────────┐
│  Gradio Web UI                                                   │
│  Tree density, age, proportions, terrain roughness, etc.         │
└────────────────────────────┬─────────────────────────────────────┘
                             │ REST / form POST
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  Python Backend                                                   │
│                                                                   │
│  ┌──────────────┐   ┌─────────────────┐   ┌──────────────────┐  │
│  │ OpenUSD pxr  │◄──│ Genesis Physics │──►│ OpenUSD prim Z   │  │
│  │ (scene def)  │   │ (terrain, ray-  │   │ (corrected from  │  │
│  │              │   │  cast heights)   │   │  raycast)        │  │
│  └──────────────┘   └─────────────────┘   └──────────────────┘  │
│       │                                                        │
│       │ USD file (.usda / .usdc)                               │
└───────┼────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│  UE5 (Rendering only)                                             │
│  USDImporter plugin → Lumen + Nanite                             │
└──────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
pip install genesis-world gradio numpy scipy noise

# Optional: for USD support with material baking
pip install -e ".[usd]"
export OMNI_KIT_ACCEPT_EULA=yes
```

## Quick Start

### 1. Configure asset paths

Edit `backend/forest_generator.py` or pass `asset_base_path` to `ForestConfig`:

```python
config = ForestConfig(
    asset_base_path="D:/temp_downloads",
    # ...
)
```

Assets expected:
```
D:/temp_downloads/
  Birch_obj/Birch.usd
  Spruce_obj/Spruce.usd
  Pine_obj/Pine.usd
  Rock_obj/Rock.usd
  Bush_obj/Bush.usd
  Blueberry_obj/Blueberry.usd
```

### 2. Generate a forest

```bash
cd genesis_forest
python -m examples.simple_forest
```

### 3. Open in UE5

1. Open UE5 with USDImporter plugin enabled
2. File → Import into Level → select `forest_output.usda`
3. Enable Lumen + Nanite in Project Settings

## Running the Gradio UI

```bash
cd genesis_forest
python -m gradio_app.app
```

Then open `http://localhost:7860` in your browser.

## Architecture

| Component | Technology | Role |
|-----------|------------|------|
| Scene definition | OpenUSD (`pxr.Usd*`) | Platform-neutral scene description |
| Physics + raycasting | Genesis | Terrain heightfield, ground height via raycast |
| UI | Gradio | Web-based parameter controls |
| Rendering | UE5 | Lumen GI, Nanite, HDRI sky |

## Key Modules

| File | Description |
|------|-------------|
| `backend/forest_generator.py` | Main orchestration: terrain → placements → raycast → USD |
| `backend/terrain.py` | Perlin noise terrain generation + heightfield mesh conversion |
| `backend/tree_placement.py` | Tree/rock/vegetation placement logic + Genesis raycast call |
| `backend/usd_stage.py` | OpenUSD stage building: prim creation, transforms, collision |
| `gradio_app/app.py` | Gradio web UI |

## Genesis Raycast Flow

```
Genesis scene.build()
       │
       ▼
For each tree position (x, y, 100):
  scene.raycast(
      origin=[x, y, 100],
      direction=[0, 0, -1],
      max_distance=200
  )
       │
       ▼
  ground_z = 100 - result.distance
       │
       ▼
  OpenUSD prim.xformOp:translate = (x, y, ground_z)
```

## Limitations

- HDR dome lighting from `omni.replicator` has no direct equivalent — lighting must be recreated in UE5
- Physics sync (live) between Genesis and UE5 is not implemented — requires a Python↔Unreal plugin bridge
- Genesis-USD material baking requires Omniverse Kit EULA acceptance

## License

MIT — same as original repository.
