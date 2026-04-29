"""
Example: Generate a procedural forest and create a flythrough video.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.forest_generator import ForestGenerator, ForestConfig
from backend.fly_camera import (
    create_forest_drone_flythrough,
    create_straight_flythrough,
    create_circle_flythrough,
    render_flythrough_single_pass,
)


def generate_forest(output_path="/tmp/forest.usdc", area_size=20):
    models_path = Path(__file__).parent.parent.parent / "models"
    config = ForestConfig(
        density=10,
        area_x=area_size,
        area_y=area_size,
        roughness=1.0,
        rockiness=5,
        vegetation_enabled=True,
        vegetation_density=8,
        usd_output_path=output_path,
        asset_base_path=str(models_path),
    )

    def progress(p: float, msg: str):
        print(f"[{p:.0%}] {msg}")

    with ForestGenerator(config) as generator:
        result = generator.generate(progress)

    print(f"Forest saved to: {result.usd_path}")
    print(f"Trees: {result.n_trees}, Rocks: {result.n_rocks}, Veg: {result.n_vegetation}")
    return result.usd_path


def render_video(usd_path, output_path="/tmp/forest_flythrough.mp4", duration=8):
    print(f"Creating drone flythrough camera...")

    camera = create_forest_drone_flythrough(
        area_x=20.0,
        area_y=20.0,
        start_x=2.0,
        start_y=2.0,
        height=5.0,
        duration=duration,
        figure_8=True,
    )

    def progress(p, msg):
        print(f"[{p:.0%}] {msg}")

    print(f"Rendering flythrough video at 1920x1080...")
    result = render_flythrough_single_pass(
        usd_path=usd_path,
        output_path=output_path,
        camera=camera,
        fps=30,
        width=1920,
        height=1080,
        progress_callback=progress,
    )

    import os
    size = os.path.getsize(result)
    print(f"Video saved to: {result} ({size / 1e6:.1f} MB)")
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate forest and render flythrough video")
    parser.add_argument("--usd-path", default="/tmp/forest.usdc", help="Output USD path")
    parser.add_argument("--video-path", default="/tmp/forest_flythrough.mp4", help="Output video path")
    parser.add_argument("--area", type=int, default=20, help="Forest area size (meters)")
    parser.add_argument("--duration", type=int, default=8, help="Video duration (seconds)")
    parser.add_argument("--skip-gen", action="store_true", help="Skip generation, use existing USD")
    args = parser.parse_args()

    if args.skip_gen:
        usd_path = args.usd_path
        if not Path(usd_path).exists():
            print(f"Error: {usd_path} does not exist")
            return 1
        print(f"Using existing USD: {usd_path}")
    else:
        print("Generating forest...")
        usd_path = generate_forest(args.usd_path, args.area)

    print(f"Rendering video...")
    video_path = render_video(usd_path, args.video_path, args.duration)
    print(f"Done! Video: {video_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
