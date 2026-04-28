"""
Simple example: Generate a procedural forest and export to USD.
"""
from backend.forest_generator import ForestGenerator, ForestConfig


def main():
    config = ForestConfig(
        density=10,
        age_min=50,
        age_max=100,
        birch_p=33.33,
        spruce_p=33.33,
        pine_p=33.34,
        area_x=100,
        area_y=100,
        roughness=1.5,
        rockiness=5,
        vegetation_enabled=True,
        vegetation_density=5,
        usd_output_path="./forest_output.usda",
        asset_base_path="D:/temp_downloads",
    )

    def progress(p: float, msg: str):
        print(f"[{p:.0%}] {msg}")

    try:
        with ForestGenerator(config) as generator:
            result = generator.generate(progress)

        print(f"\nSaved to: {result.usd_path}")
        print(f"Trees: {result.n_trees}")
        print(f"Rocks: {result.n_rocks}")
        print(f"Vegetation: {result.n_vegetation}")
        print(f"Genesis version: {result.genesis_version}")
    except FileNotFoundError as e:
        print(f"\nAsset error: {e}")
        print("\nFix: Ensure your tree assets exist at D:/temp_downloads/")
        print("Or convert USD assets to GLB/OBJ and update asset paths in ASSET_PATHS.")


if __name__ == "__main__":
    main()
