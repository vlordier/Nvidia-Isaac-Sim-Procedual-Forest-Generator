"""
Export forest to USD format optimized for UE5 consumption.
UE5.3+ has native USD support via USDImporter / USDUtilities plugin.

Usage:
    1. Run this script: python examples/ue5_export.py
    2. Open UE5 project with USDImporter plugin enabled
    3. Use File -> Import into Level, select forest_output.usda
    4. Or use USD Layers window to open the file
"""
import genesis as gs
from pathlib import Path
from backend.forest_generator import ForestGenerator, ForestConfig


UE5_OPTIMIZATIONS = {
    "flatten_stage": True,
    "export_units_in_cm": True,
    "default_prim_path": "/World",
}


def export_for_ue5(
    config: ForestConfig,
    output_path: str = "./forest_ue5.usda",
) -> str:
    generator = ForestGenerator(config)

    generator.generate_terrain_genesis()
    generator.generate_tree_placements()
    generator.generate_rock_placements()
    generator.generate_vegetation_placements()
    generator.raycast_placements()

    stage = generator.generate_usd_stage()

    root_layer = stage.get_root_layer()

    root_layer.Export(output_path)

    generator.shutdown()
    return output_path


def main():
    config = ForestConfig(
        density=15,
        age_min=30,
        age_max=120,
        birch_p=40.0,
        spruce_p=30.0,
        pine_p=30.0,
        area_x=200,
        area_y=200,
        roughness=2.0,
        rockiness=8,
        vegetation_enabled=True,
        vegetation_density=10,
        usd_output_path="./forest_ue5.usda",
        asset_base_path="D:/temp_downloads",
    )

    print("Generating forest for UE5...")
    path = export_for_ue5(config, config.usd_output_path)
    print(f"\nExported to: {path}")
    print("\nTo use in Unreal Engine 5:")
    print("  1. Open UE5 with USDImporter plugin enabled")
    print("  2. File -> Import into Level (or drag into Content Browser)")
    print("  3. Enable Lumen for dynamic global illumination")
    print("  4. Enable Nanite for micro-triangle rendering of vegetation")


if __name__ == "__main__":
    main()
