"""
Simple example: Generate a procedural forest and export to USD.
"""
import genesis as gs
from backend.forest_generator import ForestGenerator, ForestConfig


def main():
    gs.init(backend=gs.cpu)

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

    generator = ForestGenerator(config)

    print("Generating terrain with Genesis physics...")
    generator.generate_terrain_genesis()

    print("Generating tree placements...")
    generator.generate_tree_placements()

    print("Generating rock placements...")
    generator.generate_rock_placements()

    print("Generating vegetation placements...")
    generator.generate_vegetation_placements()

    print("Running raycast to determine ground heights...")
    generator.raycast_placements()

    print("Building OpenUSD stage...")
    stage = generator.generate_usd_stage()

    print("Saving USD file...")
    path = stage.save(config.usd_output_path)
    print(f"Saved to: {path}")

    print("\nSummary:")
    print(f"  Trees:      {len(generator.state.tree_placements)}")
    print(f"  Rocks:      {len(generator.state.rock_placements)}")
    print(f"  Vegetation: {len(generator.state.vegetation_placements)}")

    generator.shutdown()


if __name__ == "__main__":
    main()
