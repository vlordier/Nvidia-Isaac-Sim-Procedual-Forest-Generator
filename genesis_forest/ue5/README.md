# UE5 Setup for Forest Rendering

## Overview

The Python backend generates a `.usda` / `.usdc` file. UE5 (5.3+) consumes this natively via the **USDImporter** plugin or **USDUtilities** plugin.

## Prerequisites

- Unreal Engine 5.3 or later
- `USDImporter` plugin enabled (comes built-in with UE5)
- `USDContent` plugin (optional, for Content Browser integration)

## Importing the Forest USD

### Option 1: Import into Level

1. Open your UE5 project
2. Go to **File → Import into Level**
3. Navigate to your `.usda` file (e.g., `forest_output.usda`)
4. In the import dialog:
   - **Scale**: 1.0 (OpenUSD is in centimeters by default, UE5 also uses cm)
   - **Material Import Method**: `Do Not Create Materials` (use if materials are already USD Principled Shading)
   - **Collision**: `No Collision` (physics handled by Genesis, not UE5)
   - **Generate Mesh LODs**: Yes (for Nanite optimization)

### Option 2: USD Layers Window

1. Open **USD Layers** window (Window → USD)
2. Drag your `.usda` file into the viewport
3. Use the **Stage** panel to toggle layers on/off

## Recommended UE5 Settings

### Renderer Settings (Project Settings → Rendering)

| Setting | Value |
|---------|-------|
| **Dynamic Global Illumination** | Lumen |
| **Reflections** | Lumen |
| **Nanite** | Enabled |
| **Virtual Shadow Maps** | Enabled |

### Lighting

The forest USD includes HDR dome light prims if configured. UE5 will pick these up as `RectLight` or `DirectionalLight` actors.

For best results:
- Add a **Sky Atmosphere** actor
- Add a **HDRI backdrop** or custom skybox
- Enable **Volumetric Clouds** for depth

### Foliage Optimization

UE5's **Foliage** system is ideal for rendering hundreds/thousands of trees:

1. Select a tree mesh in the Content Browser
2. Right-click → **Asset Actions → Create Foliage Type**
3. Place a **Foliage Volume** actor in your level
4. Configure density, scale variation, wind

However, since Genesis handles placement, you may prefer **Instanced Static Mesh** actors converted from the USD.

## USD Stage Structure

The Python backend exports this hierarchy:

```
/World
  /terrain                    # Ground mesh
  /Tree_parent
    /Tree_0000 (Birch)        # Xform with USD reference
    /Tree_0001 (Spruce)
    ...
  /Rock_parent
    /Rock_0000
    ...
  /Bush_parent
    /Plant_0000 (Blueberry/Bush)
    ...
```

## Material Considerations

Genesis bakes materials to `UsdPreviewSurface` when exporting. UE5 imports these as **MDL** or **USF** materials automatically.

For the best visual quality:
- Use **Nanite** with `Render in Nanite` enabled on meshes
- Assign **Lumen**-compatible materials (no heavy normal maps)

## Performance Tips

1. **Use `.usdc`** (binary USD) instead of `.usda` (ASCII) for production — faster loading
2. Enable **GPU Lightmass** for static lighting precompute
3. For very large forests, use UE5's **World Partition** system with USD as the data source
4. Consider **HLOD** (Hierarchical LOD) for distant foliage

## Limitations

- UE5 USD support is read-mostly — editing USD prims in UE5 is limited
- For live physics sync between Genesis and UE5, a **Python-UE plugin bridge** is needed (future work)
- HDR dome lighting from `omni.replicator` is not directly imported — re-create lighting in UE5 manually
