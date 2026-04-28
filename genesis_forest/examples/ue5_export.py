"""
Generate a forest optimized for UE5 consumption.

Usage:
    python examples/ue5_export.py
    # Then import forest_ue5.usdc in UE5 (File → Import into Level)

UE5 Notes:
    - Enable USDImporter plugin
    - Use .usdc (binary) for fast loading
    - Enable Lumen + Nanite in Project Settings
"""
from backend.forest_generator import ForestGenerator, ForestConfig


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
        use_binary_usd=True,
        asset_base_path="D:/temp_downloads",
    )

    def progress(p: float, msg: str):
        print(f"[{p:.0%}] {msg}")

    with ForestGenerator(config) as generator:
        result = generator.generate(progress)

    print(f"\nExported to: {result.usd_path}")
    print(f"Trees: {result.n_trees} | Rocks: {result.n_rocks} | Veg: {result.n_vegetation}")
    print("\nUE5 import steps:")
    print("  1. Open UE5 with USDImporter plugin enabled")
    print("  2. File → Import into Level → select the .usdc file")
    print("  3. Project Settings → Rendering:")
    print("       Dynamic Global Illumination: Lumen")
    print("       Nanite: Enabled")
    print("       Virtual Shadow Maps: Enabled")


if __name__ == "__main__":
    main()
