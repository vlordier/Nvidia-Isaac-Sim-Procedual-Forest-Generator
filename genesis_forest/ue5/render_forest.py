"""
UE5 Python script for rendering a forest from a USD file.

Usage (inside UE5):
    Option A — Editor Python console:
        exec(open("genesis_forest/ue5/render_forest.py").read())

    Option B — Command line (with UE5 installed):
        "C:\Program Files\Epic Games\UE_5.3\Engine\Binaries\Win64\UnrealEditor.exe"
            "YourProject.uproject" -game -ExecCmd="python C:\path\to\render_forest.py"
            -Messaging

    Option C — Python editor script:
        In UE5: Edit -> Plugins -> Python Editor Script Plugin (enable)
        Then: Edit -> Editor Scripting -> Execute Python Script

This script:
    1. Imports a .usdc/.usda USD file as a stage
    2. Places camera(s) at configurable positions
    3. Configures Lumen + Nanite + Sky Atmosphere
    4. Sets up HDRI / directional lighting
    5. Renders via Movie Render Queue or high-res screenshot
"""

import unreal
import os
import sys
from pathlib import Path


class ForestRenderer:
    """
    Renders a forest USD file in UE5 with Lumen, Nanite, and cinematic camera.
    """

    def __init__(self, usd_path: str, output_dir: str = None):
        self.usd_path = Path(usd_path)
        self.output_dir = Path(output_dir or str(self.usd_path.parent / "renders"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
        self.editor_util = unreal.EditorUtilityLibrary
        self.movie_pipeline = unreal.MovieRenderPipelineCore

    def log(self, msg: str):
        unreal.log(f"[ForestRenderer] {msg}")

    def import_usd_stage(self, usd_path: str) -> unreal.World:
        """
        Import a USD stage into the current editor world.

        Uses USDImporter plugin to load the USD as a actor hierarchy.
        """
        if not Path(usd_path).exists():
            raise FileNotFoundError(f"USD file not found: {usd_path}")

        self.log(f"Importing USD: {usd_path}")

        task = unreal.AssetImportTask()
        task.set_editor_property("automated", True)
        task.set_editor_property("destination_path", "/Game/Forest")
        task.set_editor_property("filename", usd_path)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", False)

        task.options = unreal.USdImportOptions()
        task.options.set_editor_property("import_textures", True)
        task.options.set_editor_property("import_materials", True)
        task.options.set_editor_property("import_geometries", True)
        task.options.set_editor_property("import_skeletons", False)
        task.options.set_editor_property("import_only_selected", False)
        task.options.set_editor_property("import_visible", True)
        task.options.set_editor_property("create_world", True)
        task.options.set_editor_property("world_bin_path", "/Game/Forest")

        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

        if task.num_assets_imported < 1:
            raise RuntimeError(f"USD import failed for {usd_path}")

        self.log(f"Imported {task.num_assets_imported} assets")

        imported_actors = []
        for path in task.imported_object_paths:
            obj = unreal.load_asset(path)
            if isinstance(obj, unreal.Actor):
                unreal.EditorLevelLibrary.maybe_load_world_from_object(obj)
                imported_actors.append(obj)

        return imported_actors

    def setup_sun(self, azimuth: float = 45.0, elevation: float = 30.0):
        """
        Configure the sun (directional light) with HDRI sky.
        """
        self.log("Setting up sun lighting...")

        actors = unreal.EditorLevelLibrary.get_all_level_actors()

        directional_light = None
        sky_light = None
        sky_atmosphere = None

        for actor in actors:
            if isinstance(actor, unreal.DirectionalLight):
                directional_light = actor
            elif isinstance(actor, unreal.SkyLight):
                sky_light = actor
            elif isinstance(actor, unreal.SkyAtmosphere):

                sky_atmosphere = actor

        if directional_light is None:
            actor_type = unreal.EditorAssetLibrary.load_asset("/Engine/Basic/DirectionalLight.DirectionalLight")
            spawned = unreal.EditorLevelLibrary.spawn_actor_from_object(actor_type, unreal.Vector(0, 0, 0))
            directional_light = spawned

        light_comp = directional_light.get_component_by_class(unreal.DirectionalLightComponent)
        if light_comp:
            light_comp.set_editor_property("light_color", unreal.Color(255, 250, 235))
            light_comp.set_editor_property("intensity", 3.0)

            rot = unreal.Rotator(elevation, azimuth, 0.0)
            directional_light.set_actor_rotation(rot, False)

        if sky_light is None:
            actor_type = unreal.EditorAssetLibrary.load_asset("/Engine/Basic/SkyLight.SkyLight")
            spawned = unreal.EditorLevelLibrary.spawn_actor_from_object(actor_type, unreal.Vector(0, 0, 500))
            sky_light = spawned

        sky_light.set_editor_property("light_source_angle", 0.5)
        sky_light.set_editor_property("indirect_intensity", 1.0)

        if sky_atmosphere is None:
            actor_type = unreal.EditorAssetLibrary.load_asset("/Engine/Basic/SkyAtmosphere.SkyAtmosphere")
            if actor_type is None:
                actor_type = unreal.EditorAssetLibrary.load_asset(
                    "/Engine/Plugins/EnginePlugins/Rendering/Windows/SkyAtmosphere/Blueprints/BP_Sky_Sphere.BP_Sky_Sphere"
                )
            if actor_type:
                spawned = unreal.EditorLevelLibrary.spawn_actor_from_object(actor_type, unreal.Vector(0, 0, 0))
                sky_atmosphere = spawned

        self.log("Lighting configured")

    def setup_fog(self, density: float = 0.001):
        """
        Add exponential height fog for atmospheric depth.
        """
        actors = unreal.EditorLevelLibrary.get_all_level_actors()
        for actor in actors:
            if isinstance(actor, unreal.ExponentialHeightFog):
                return

        actor_type = unreal.EditorAssetLibrary.load_asset(
            "/Engine/Basic/ExponentialHeightFog.ExponentialHeightFog"
        )
        spawned = unreal.EditorLevelLibrary.spawn_actor_from_object(actor_type, unreal.Vector(0, 0, 0))
        fog_comp = spawned.get_component_by_class(unreal.ExponentialHeightFogComponent)
        if fog_comp:
            fog_comp.set_editor_property("fog_density", density)
            fog_comp.set_editor_property("height_falloff", 0.005)

    def place_camera(
        self,
        location: tuple[float, float, float],
        look_at: tuple[float, float, float] = (0, 0, 0),
        fov: float = 50.0,
        name: str = "ForestCamera",
    ) -> unreal.CameraActor:
        """
        Place a cinematic camera at a given world location.
        """
        actor_type = unreal.EditorAssetLibrary.load_asset("/Engine/Basic/CameraActor.CameraActor")
        cam = unreal.EditorLevelLibrary.spawn_actor_from_object(actor_type, unreal.Vector(*location))
        cam.set_actor_label(name)

        cam_controller = cam.get_component_by_class(unreal.CameraComponent)
        if cam_controller:
            cam_controller.set_editor_property("field_of_view", fov)
            cam_controller.set_editor_property("focus_settings", unreal.CameraFocusSettings())

        look_at_rot = unreal.Rotator.make_from_xyz(
            unreal.Vector(*look_at) - unreal.Vector(*location)
        )
        cam.set_actor_rotation(look_at_rot, False)

        self.log(f"Camera placed at {location} looking at {look_at}")
        return cam

    def configure_render_settings(self):
        """
        Configure project rendering settings for high quality output.
        """
        self.log("Configuring render settings...")

        settings = unreal.get_default_object(unreal.ProjectSettings)
        rhi = settings.get_editor_property("rhi")

        quality_settings = unreal.get_default_object(unreal.RenderSettings)

        console_vars = [
            ("r.Lumen.Enable", 1),
            ("r.Shadow.Virtual.Enable", 1),
            ("r.Nanite.Enable", 1),
            ("r.Nanite.AllowTessellation", 1),
            ("r.DefaultFeature.AutoExposure", 1),
            ("r.DefaultFeature.MotionBlur", 0),
            ("r.AntiAliasingMethod", 2),
            ("sg.PostProcessQuality", 3),
            ("sg.ShadowQuality", 3),
            ("sg.TextureQuality", 3),
        ]

        for var, value in console_vars:
            cmd = f"set {var} {value}"
            unreal.SystemLibrary.execute_console_command(None, cmd, False)

        self.log("Render settings configured")

    def render_highres_screenshot(
        self,
        camera: unreal.CameraActor,
        output_path: str,
        resolution_x: int = 3840,
        resolution_y: int = 2160,
    ) -> str:
        """
        Capture a high-resolution screenshot from a camera using the viewer.
        """
        self.log(f"Capturing high-res screenshot: {resolution_x}x{resolution_y}")

        viewport_client = unreal.EditorViewportClient.get_editor_viewport_client()
        if viewport_client:
            viewport_client.set_viewport_client_camera_override(camera)

        unreal.SystemLibrary.execute_console_command(
            None, f"setres {resolution_x}x{resolution_y}", False
        )

        unreal.SystemLibrary.execute_console_command(None, "r.ScreenshotMask 0", False)

        screenshot_path = output_path
        unreal.SystemLibrary.execute_console_command(
            None, f"screenshot {screenshot_path}", False
        )

        self.log(f"Screenshot saved to: {screenshot_path}")
        return screenshot_path

    def setup_movie_render_queue(self) -> unreal.MoviePipelineQueue:
        """
        Setup Movie Render Queue for high-quality sequenced renders.
        """
        pipeline = unreal.MovieRenderPipelineRenderQueue.get_or_create()
        job = pipeline.create_new_job(unreal.MoviePipelineExecutorJob)

        output = unreal.MoviePipelineOutputSetting()
        output.resolution = unreal.IntPoint(3840, 2160)
        output.file_name_format = "{sequence_name}.{frame_number>"
        output.output_path = str(self.output_dir / "movie")
        job.set_editor_property("output", output)

        camera = None
        for actor in unreal.EditorLevelLibrary.get_all_level_actors():
            if isinstance(actor, unreal.CameraActor):
                camera = actor
                break

        if camera:
            unreal.log(f"Using camera: {camera.get_actor_label()}")

        return pipeline

    def render(
        self,
        usd_path: str,
        camera_location: tuple[float, float, float] = (50, -50, 20),
        camera_look_at: tuple[float, float, float] = (0, 0, 5),
        resolution: tuple[int, int] = (3840, 2160),
        mode: str = "screenshot",
    ) -> dict:
        """
        Full render pipeline.

        Args:
            usd_path: Path to the .usdc/.usda file from forest generator
            camera_location: (x, y, z) world position for camera
            camera_look_at: (x, y, z) world position for camera to look at
            resolution: (width, height) output resolution
            mode: "screenshot" or "movie"

        Returns:
            dict with render output paths and metadata
        """
        results = {
            "usd_input": usd_path,
            "output_dir": str(self.output_dir),
            "camera_location": camera_location,
            "camera_look_at": camera_look_at,
            "resolution": resolution,
            "mode": mode,
        }

        try:
            actors = self.import_usd_stage(usd_path)
            results["actors_imported"] = len(actors)
            self.log(f"Stage imported: {len(actors)} actors")
        except Exception as e:
            unreal.log_error(f"Failed to import USD: {e}")
            results["error"] = str(e)
            return results

        self.setup_sun()
        self.setup_fog()
        self.configure_render_settings()

        cam = self.place_camera(camera_location, camera_look_at, name="ForestCinematic")

        if mode == "screenshot":
            output_file = str(
                self.output_dir / f"{self.usd_path.stem}_{resolution[0]}x{resolution[1]}.png"
            )
            path = self.render_highres_screenshot(cam, output_file, *resolution)
            results["screenshot_path"] = path

        elif mode == "movie":
            pipeline = self.setup_movie_render_queue()
            executor = unreal.MovieRenderPipelineExecutor()
            executor.render(pipeline)
            results["movie_output"] = str(self.output_dir / "movie")

        self.log(f"Render complete. Output: {results}")
        return results


def render_forest(
    usd_path: str,
    camera_location: tuple[float, float, float] = (50, -50, 20),
    camera_look_at: tuple[float, float, float] = (0, 0, 5),
    resolution: tuple[int, int] = (3840, 2160),
    mode: str = "screenshot",
) -> dict:
    """
    Convenience function matching the Gradio API signature.

    Usage from UE5 Python console:
        from genesis_forest.ue5.render_forest import render_forest
        render_forest("C:/path/to/forest_output.usdc")
    """
    renderer = ForestRenderer(usd_path)
    return renderer.render(
        usd_path=usd_path,
        camera_location=camera_location,
        camera_look_at=camera_look_at,
        resolution=resolution,
        mode=mode,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Render forest USD in UE5")
    parser.add_argument("usd_path", help="Path to .usdc/.usda file")
    parser.add_argument("--camera-location", nargs=3, type=float,
                        default=[50, -50, 20],
                        help="Camera world position (x y z)")
    parser.add_argument("--camera-look-at", nargs=3, type=float,
                        default=[0, 0, 5],
                        help="Camera look-at world position (x y z)")
    parser.add_argument("--resolution", nargs=2, type=int,
                        default=[3840, 2160],
                        help="Output resolution (width height)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory for renders")
    parser.add_argument("--mode", choices=["screenshot", "movie"],
                        default="screenshot")

    args = parser.parse_args()

    camera_location = tuple(args.camera_location)
    camera_look_at = tuple(args.camera_look_at)
    resolution = tuple(args.resolution)

    renderer = ForestRenderer(args.usd_path, args.output_dir)

    result = renderer.render(
        usd_path=args.usd_path,
        camera_location=camera_location,
        camera_look_at=camera_look_at,
        resolution=resolution,
        mode=args.mode,
    )

    unreal.log(f"Render complete: {result}")
