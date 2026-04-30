from .usd_stage import USDStage
from .terrain import (
    generate_terrain,
    SubTerrain,
    convert_heightfield_to_trimesh,
)
from .tree_placement import (
    TreePlacement,
    generate_tree_placements,
    generate_rock_placements,
    generate_vegetation_placements,
    euler_to_quaternion,
)
from .fly_camera import (
    FlyCamera,
    PathFlyCamera,
    create_straight_flythrough,
    create_circle_flythrough,
    create_spiral_flythrough,
    create_forest_drone_flythrough,
    render_flythrough,
    render_flythrough_single_pass,
)


def __getattr__(name):
    if name in {
        "ForestGenerator",
        "ForestConfig",
        "GenerationResult",
        "HeightSampler",
        "AssetLoader",
        "_detect_genesis_backend",
        "_get_genesis_version",
        "_check_usd_support",
    }:
        from . import forest_generator as _fg

        return getattr(_fg, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ForestGenerator",
    "ForestConfig",
    "GenerationResult",
    "HeightSampler",
    "AssetLoader",
    "USDStage",
    "generate_terrain",
    "SubTerrain",
    "convert_heightfield_to_trimesh",
    "TreePlacement",
    "generate_tree_placements",
    "generate_rock_placements",
    "generate_vegetation_placements",
    "euler_to_quaternion",
    "_detect_genesis_backend",
    "_get_genesis_version",
    "_check_usd_support",
    "FlyCamera",
    "PathFlyCamera",
    "create_straight_flythrough",
    "create_circle_flythrough",
    "create_spiral_flythrough",
    "create_forest_drone_flythrough",
    "render_flythrough",
    "render_flythrough_single_pass",
]
