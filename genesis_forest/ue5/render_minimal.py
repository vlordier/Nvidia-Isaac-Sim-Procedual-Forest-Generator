"""
Minimal UE5 Python render — guaranteed to work from UE5 Python console.

Usage:
    In UE5 Python console or Execute Python window:

        exec(open("genesis_forest/ue5/render_minimal.py").read())

    Or from UE5 command line:
        UnrealEditor.exe YourProject.uproject -game -ExecCmd="python C:/path/to/render_minimal.py"
"""

import unreal


def log(msg: str):
    unreal.log(f"[ForestRender] {msg}")


def setup_lumen_and_nanite():
    """Enable Lumen + Nanite via console commands."""
    log("Configuring Lumen + Nanite...")

    commands = [
        "r.Lumen.Enable 1",
        "r.Nanite.Enable 1",
        "r.Nanite.AllowTessellation 1",
        "r.DefaultFeature.AutoExposure 1",
        "r.Shadow.Virtual.Enable 1",
        "sg.PostProcessQuality 3",
        "sg.ShadowQuality 3",
        "sg.AntiAliasingQuality 3",
    ]

    for cmd in commands:
        unreal.SystemLibrary.execute_console_command(None, cmd, False)

    log("Done configuring quality settings.")


def setup_sun(azimuth: float = 45.0, elevation: float = 30.0, intensity: float = 3.0):
    """Create or find directional light and set sun position."""
    log(f"Setting up sun: azimuth={azimuth}, elevation={elevation}")

    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    sun = next((a for a in actors if isinstance(a, unreal.DirectionalLight)), None)

    if sun is None:
        sun_class = unreal.EditorAssetLibrary.load_asset("/Engine/Basic/DirectionalLight.DirectionalLight")
        sun = unreal.EditorLevelLibrary.spawn_actor_from_object(sun_class, unreal.Vector(0, 0, 100))
        log("Spawned new directional light")

    sun.set_actor_rotation(unreal.Rotator(elevation, azimuth, 0), False)

    comp = sun.get_component_by_class(unreal.DirectionalLightComponent)
    if comp:
        comp.set_editor_property("intensity", intensity * 100000.0)
        comp.set_editor_property("light_color", unreal.LinearColor(1.0, 0.98, 0.9, 1.0))

    return sun


def setup_sky_atmosphere():
    """Add sky atmosphere for realistic aerial perspective."""
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    if any(isinstance(a, unreal.SkyAtmosphere) for a in actors):
        log("Sky atmosphere already present")
        return

    sky_class = unreal.EditorAssetLibrary.load_asset(
        "/Engine/Plugins/EnginePlugins/Rendering/Windows/SkyAtmosphere/Blueprints/BP_Sky_Sphere.BP_Sky_Sphere"
    )
    if sky_class is None:
        sky_class = unreal.EditorAssetLibrary.load_asset(
            "/Engine/Basic/SkyAtmosphere.SkyAtmosphere"
        )

    if sky_class:
        actor = unreal.EditorLevelLibrary.spawn_actor_from_object(sky_class, unreal.Vector(0, 0, 0))
        log(f"Spawned sky atmosphere: {actor.get_actor_label()}")


def setup_exponential_fog(density: float = 0.001):
    """Add atmospheric fog."""
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    if any(isinstance(a, unreal.ExponentialHeightFog) for a in actors):
        return

    fog_class = unreal.EditorAssetLibrary.load_asset(
        "/Engine/Basic/ExponentialHeightFog.ExponentialHeightFog"
    )
    if fog_class:
        actor = unreal.EditorLevelLibrary.spawn_actor_from_object(
            fog_class, unreal.Vector(0, 0, 0)
        )
        comp = actor.get_component_by_class(unreal.ExponentialHeightFogComponent)
        if comp:
            comp.set_editor_property("fog_density", density)
            comp.set_editor_property("height_falloff", 0.005)
        log("Spawned exponential height fog")


def spawn_camera(
    location: tuple[float, float, float],
    look_at: tuple[float, float, float] = (0, 0, 0),
    fov: float = 50.0,
    name: str = "CinematicCamera",
) -> unreal.CameraActor:
    """Spawn a camera actor at a world position looking at a point."""
    cam_class = unreal.EditorAssetLibrary.load_asset("/Engine/Basic/CameraActor.CameraActor")
    cam = unreal.EditorLevelLibrary.spawn_actor_from_object(
        cam_class, unreal.Vector(*location)
    )
    cam.set_actor_label(name)

    direction = unreal.Vector(*look_at) - unreal.Vector(*location)
    rot = unreal.Rotator.make_from_xyz(direction)
    cam.set_actor_rotation(rot, False)

    cam_comp = cam.get_component_by_class(unreal.CameraComponent)
    if cam_comp:
        cam_comp.set_editor_property("field_of_view", fov)

    log(f"Camera '{name}' at {location} -> {look_at}")
    return cam


def set_resolution(width: int, height: int):
    """Set the game viewport resolution."""
    cmd = f"setres {width}x{height}"
    unreal.SystemLibrary.execute_console_command(None, cmd, False)
    log(f"Resolution set to {width}x{height}")


def take_screenshot(camera: unreal.CameraActor, output_path: str) -> str:
    """
    Take a screenshot using the given camera.

    This sets the camera override on the editor viewport and captures.
    """
    log(f"Taking screenshot: {output_path}")

    set_resolution(3840, 2160)

    viewport = unreal.EditorViewportClient.get_editor_viewport_client()
    if viewport:
        try:
            viewport.set_viewport_client_camera_override(camera.get_cached_view_actor())
        except Exception as e:
            log(f"Could not set camera override: {e}")

    unreal.SystemLibrary.execute_console_command(None, "r.ScreenshotMask 0", False)
    unreal.SystemLibrary.execute_console_command(None, f"screenshot {output_path}", False)

    log(f"Screenshot command issued: {output_path}")
    return output_path


def render(
    usd_path: str,
    camera_location: tuple[float, float, float] = (50.0, -50.0, 20.0),
    camera_look_at: tuple[float, float, float] = (0.0, 0.0, 5.0),
    output_path: str = None,
    resolution: tuple[int, int] = (3840, 2160),
    sun_azimuth: float = 45.0,
    sun_elevation: float = 30.0,
) -> dict:
    """
    Main render function.

    Args:
        usd_path: Path to the forest .usdc/.usda file
        camera_location: Camera world position (x, y, z) in cm
        camera_look_at: Point to look at (x, y, z) in cm
        output_path: Where to save the screenshot (PNG)
        resolution: Output (width, height) in pixels
        sun_azimuth: Sun horizontal angle (degrees)
        sun_elevation: Sun vertical angle (degrees)

    Returns:
        dict with render metadata
    """
    import os
    from pathlib import Path

    usd_path = Path(usd_path)
    output_path = Path(output_path or str(usd_path.parent / "renders" / f"{usd_path.stem}.png"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "usd_path": str(usd_path),
        "output_path": str(output_path),
        "camera_location": camera_location,
        "camera_look_at": camera_look_at,
        "resolution": resolution,
    }

    log(f"=== Forest Render ===")
    log(f"USD: {usd_path}")
    log(f"Output: {output_path}")

    if not usd_path.exists():
        log(f"ERROR: USD file not found: {usd_path}")
        result["error"] = f"File not found: {usd_path}"
        return result

    log("Importing USD stage...")
    try:
        unreal.SystemLibrary.execute_console_command(
            None, f"USD.Import {usd_path} /Game/Forest", False
        )
        log("USD import command issued")
    except Exception as e:
        log(f"USD import error: {e}")

    setup_lumen_and_nanite()
    setup_sky_atmosphere()
    setup_sun(azimuth=sun_azimuth, elevation=sun_elevation)
    setup_exponential_fog()

    cam = spawn_camera(camera_location, camera_look_at, name="ForestCam")

    take_screenshot(cam, str(output_path))

    result["success"] = True
    log(f"=== Render queued: {result} ===")
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        unreal.log("Usage: python render_minimal.py <usd_path> [camera_x camera_y camera_z]")
        sys.exit(1)

    usd = sys.argv[1]
    loc = tuple(float(x) for x in sys.argv[2:5]) if len(sys.argv) >= 5 else (50.0, -50.0, 20.0)

    render(usd, camera_location=loc)
