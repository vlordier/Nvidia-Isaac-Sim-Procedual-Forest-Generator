"""
UE5 HTTP Server — runs inside Unreal Engine 5 with Python Editor Script Plugin.

This script starts an HTTP server inside UE5 that listens for render requests
from the Gradio backend. It uses `unreal.get_editor_subsystem()` for all
editor operations.

Usage inside UE5:
    Option A — Python console (View → Developer Tools → Python Console):
        exec(open("genesis_forest/ue5/ue5_server.py").read())

    Option B — Execute Python window (Edit → Editor Scripting → Execute Python):
        Paste contents of this file

    Option C — Command line:
        UnrealEditor.exe YourProject.uproject -game -ExecCmd="python C:/path/to/ue5_server.py"

The server listens on 0.0.0.0:8787 by default. Gradio posts render requests here.

Architecture:
    Gradio UI  ──HTTP POST /render──►  UE5 Python HTTP Server  ──►  Lumen + Nanite + Screenshot
                                              │
                                              └── uses unreal.get_editor_subsystem()
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

try:
    import unreal
except ImportError:
    raise ImportError(
        "The 'unreal' module is only available inside Unreal Engine 5 "
        "with the Python Editor Script Plugin enabled."
    )


DEFAULT_PORT = 8787
RENDER_DIR = Path(__file__).parent / "renders"


class UE5RenderHandler(BaseHTTPRequestHandler):
    """HTTP request handler for UE5 render commands."""

    server: "UE5RenderServer"

    def log_message(self, format_str: str, *args):
        unreal.log(f"[UE5Server] {format_str % args}")

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "ue5": True}).encode())
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = (
                "<html><head><title>UE5 Forest Render Server</title></head>"
                "<body><h1>UE5 Forest Render Server</h1>"
                "<p>Send POST /render with JSON body.</p>"
                "<p>Or open <a href='/test'>test page</a>.</p>"
                "</body></html>"
            )
            self.wfile.write(html.encode())
        elif self.path == "/test":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            subsystems = {
                "EditorScriptingUtilities": bool(unreal.get_editor_subsystem(unreal.EditorScriptingUtilitiesSubsystem)),
                "EditorPerformance": bool(unreal.get_editor_subsystem(unreal.EditorPerformanceSubsystem)),
            }
            actors_count = len(unreal.EditorLevelLibrary.get_all_level_actors())
            self.wfile.write(json.dumps({
                "status": "ok",
                "subsystems": subsystems,
                "actors_in_level": actors_count,
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/render":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            params = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())
            return

        result = self.server.render_scene(params)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())


class UE5RenderServer:
    """
    HTTP server that runs inside UE5, listening for render commands.

    Uses `unreal.get_editor_subsystem()` for editor operations:
    - EditorScriptingUtilitiesSubsystem: import USD assets
    - EditorPerformanceSubsystem: performance/settings queries
    """

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def log(self, msg: str):
        unreal.log(f"[UE5RenderServer] {msg}")

    def _configure_rendering(self, settings: dict) -> None:
        """Apply console commands for Lumen, Nanite, and quality settings."""
        self.log("Configuring rendering: Lumen + Nanite + quality")

        commands = [
            ("r.Lumen.Enable", 1),
            ("r.Nanite.Enable", 1),
            ("r.Nanite.AllowTessellation", 1),
            ("r.DefaultFeature.AutoExposure", 1),
            ("r.Shadow.Virtual.Enable", 1),
            ("r.DefaultFeature.MotionBlur", 0),
            ("sg.PostProcessQuality", 3),
            ("sg.ShadowQuality", 3),
            ("sg.AntiAliasingQuality", 3),
            ("sg.TextureQuality", 3),
        ]

        for var, value in commands:
            cmd = f"set {var} {value}"
            unreal.SystemLibrary.execute_console_command(None, cmd, False)

        self.log("Rendering settings applied")

    def _import_usd(self, usd_path: str, destination: str = "/Game/Forest") -> list:
        """
        Import a USD file into the current level using EditorScriptingUtilitiesSubsystem.

        Uses `unreal.get_editor_subsystem()` to access the subsystem's import method.
        Falls back to console command if subsystem import fails.
        """
        usd_path = Path(usd_path)
        if not usd_path.exists():
            raise FileNotFoundError(f"USD file not found: {usd_path}")

        self.log(f"Importing USD: {usd_path}")

        imported_actors: list = []

        subsystem = unreal.get_editor_subsystem(unreal.EditorScriptingUtilitiesSubsystem)

        if subsystem and hasattr(subsystem, "import_assets"):
            try:
                task = unreal.AssetImportTask()
                task.set_editor_property("automated", True)
                task.set_editor_property("destination_path", destination)
                task.set_editor_property("filename", str(usd_path))
                task.set_editor_property("replace_existing", True)
                task.set_editor_property("save", False)

                options = unreal.USdImportOptions()
                options.set_editor_property("import_textures", True)
                options.set_editor_property("import_materials", True)
                options.set_editor_property("import_geometries", True)
                options.set_editor_property("import_skeletons", False)
                options.set_editor_property("create_world", True)
                options.set_editor_property("world_bin_path", destination)
                task.set_editor_property("options", options)

                result = unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
                if result and result[0].num_assets_imported > 0:
                    self.log(f"Imported {result[0].num_assets_imported} assets via subsystem")
                    return imported_actors
            except Exception as e:
                self.log(f"Subsystem import failed, falling back to console: {e}")

        unreal.SystemLibrary.execute_console_command(
            None, f"USD.Import {usd_path} {destination}", False
        )
        self.log("Import via console command issued")
        return imported_actors

    def _setup_sun(
        self,
        azimuth: float = 45.0,
        elevation: float = 30.0,
        intensity: float = 3.0,
    ) -> None:
        """Create or configure directional light for sun."""
        actors = unreal.EditorLevelLibrary.get_all_level_actors()
        sun = next((a for a in actors if isinstance(a, unreal.DirectionalLight)), None)

        if sun is None:
            sun_class = unreal.EditorAssetLibrary.load_asset(
                "/Engine/Basic/DirectionalLight.DirectionalLight"
            )
            if sun_class:
                sun = unreal.EditorLevelLibrary.spawn_actor_from_object(
                    sun_class, unreal.Vector(0, 0, 1000)
                )
                self.log("Spawned new directional light")
            else:
                self.log("WARNING: Could not find or spawn DirectionalLight class")
                return

        rot = unreal.Rotator(elevation, azimuth, 0.0)
        sun.set_actor_rotation(rot, False)

        comp = sun.get_component_by_class(unreal.DirectionalLightComponent)
        if comp:
            comp.set_editor_property("intensity", intensity * 100000.0)
            comp.set_editor_property("light_color", unreal.LinearColor(1.0, 0.98, 0.9, 1.0))

        self.log(f"Sun configured: azimuth={azimuth}, elevation={elevation}")

    def _setup_sky_atmosphere(self) -> None:
        """Add sky atmosphere for realistic aerial perspective."""
        actors = unreal.EditorLevelLibrary.get_all_level_actors()
        if any(isinstance(a, unreal.SkyAtmosphere) for a in actors):
            self.log("Sky atmosphere already present")
            return

        sky_class = unreal.EditorAssetLibrary.load_asset(
            "/Engine/Basic/SkyAtmosphere.SkyAtmosphere"
        )
        if sky_class is None:
            sky_class = unreal.EditorAssetLibrary.load_asset(
                "/Engine/Plugins/EnginePlugins/Rendering/Windows/SkyAtmosphere/"
                "Blueprints/BP_Sky_Sphere.BP_Sky_Sphere"
            )

        if sky_class:
            actor = unreal.EditorLevelLibrary.spawn_actor_from_object(
                sky_class, unreal.Vector(0, 0, 0)
            )
            self.log(f"Spawned sky atmosphere: {actor.get_actor_label()}")
        else:
            self.log("WARNING: Could not find SkyAtmosphere class")

    def _setup_fog(self, density: float = 0.001) -> None:
        """Add exponential height fog."""
        actors = unreal.EditorLevelLibrary.get_all_level_actors()
        if any(isinstance(a, unreal.ExponentialHeightFog) for a in actors):
            self.log("Exponential height fog already present")
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
            self.log("Spawned exponential height fog")
        else:
            self.log("WARNING: Could not find ExponentialHeightFog class")

    def _spawn_camera(
        self,
        location: tuple[float, float, float],
        look_at: tuple[float, float, float],
        fov: float = 50.0,
        name: str = "ForestCam",
    ) -> Optional[unreal.CameraActor]:
        """Spawn a camera at world position looking at a point."""
        cam_class = unreal.EditorAssetLibrary.load_asset(
            "/Engine/Basic/CameraActor.CameraActor"
        )
        if cam_class is None:
            self.log("ERROR: Could not find CameraActor class")
            return None

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

        self.log(f"Camera '{name}' at {location} -> {look_at}")
        return cam

    def _set_resolution(self, width: int, height: int) -> None:
        """Set game viewport resolution."""
        cmd = f"setres {width}x{height}"
        unreal.SystemLibrary.execute_console_command(None, cmd, False)
        self.log(f"Resolution set to {width}x{height}")

    def _take_screenshot(self, camera: unreal.CameraActor, output_path: str) -> str:
        """Trigger a high-resolution screenshot from the given camera."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        viewport = None
        try:
            viewport = unreal.EditorViewportClient.get_editor_viewport_client()
        except Exception as e:
            self.log(f"Could not get viewport client: {e}")

        if viewport and camera:
            try:
                camera_actor = camera.get_cached_view_actor()
                if camera_actor:
                    viewport.set_viewport_client_camera_override(camera_actor)
            except Exception as e:
                self.log(f"Camera override failed (non-critical): {e}")

        unreal.SystemLibrary.execute_console_command(None, "r.ScreenshotMask 0", False)
        unreal.SystemLibrary.execute_console_command(None, f"screenshot {output_path}", False)
        self.log(f"Screenshot command issued: {output_path}")
        return str(output_path)

    def render_scene(self, params: dict) -> dict:
        """
        Execute the full render pipeline.

        Expected params:
            usd_path: str — path to .usdc/.usda file
            camera_location: tuple — (x, y, z) in cm
            camera_look_at: tuple — (x, y, z) in cm
            output_path: str — PNG output path (optional, auto from usd_path)
            resolution: tuple — (width, height) in pixels
            sun_azimuth: float — sun horizontal angle (degrees)
            sun_elevation: float — sun vertical angle (degrees)
            lumen: bool — enable Lumen GI
            nanite: bool — enable Nanite
        """
        import time
        start = time.time()

        usd_path = params.get("usd_path", "")
        camera_location = tuple(params.get("camera_location", (5000, -5000, 2000)))
        camera_look_at = tuple(params.get("camera_look_at", (0, 0, 500)))
        output_path = params.get("output_path")
        resolution = tuple(params.get("resolution", (3840, 2160)))
        sun_azimuth = params.get("sun_azimuth", 45.0)
        sun_elevation = params.get("sun_elevation", 30.0)
        lumen = params.get("lumen", True)
        nanite = params.get("nanite", True)

        result = {
            "usd_path": usd_path,
            "camera_location": camera_location,
            "camera_look_at": camera_look_at,
            "resolution": resolution,
            "output_path": None,
            "success": False,
            "error": None,
        }

        try:
            if not usd_path:
                raise ValueError("usd_path is required")

            usd_path_p = Path(usd_path)
            if not usd_path_p.exists():
                raise FileNotFoundError(f"USD file not found: {usd_path}")

            if output_path is None:
                output_path = str(RENDER_DIR / f"{usd_path_p.stem}.png")
            result["output_path"] = output_path

            self.log("=== Render request received ===")
            self.log(f"USD: {usd_path}")
            self.log(f"Output: {output_path}")
            self.log(f"Camera: {camera_location} -> {camera_look_at}")

            if not lumen or not nanite:
                self.log(f"Skipping Lumen/Nanite: lumen={lumen}, nanite={nanite}")
            else:
                self._configure_rendering(params)

            self._import_usd(usd_path)
            self._setup_sun(azimuth=sun_azimuth, elevation=sun_elevation)
            self._setup_sky_atmosphere()
            self._setup_fog()

            cam = self._spawn_camera(camera_location, camera_look_at)
            if cam is None:
                raise RuntimeError("Failed to spawn camera")

            self._set_resolution(*resolution)
            self._take_screenshot(cam, output_path)

            result["success"] = True
            result["elapsed_seconds"] = round(time.time() - start, 2)
            self.log(f"=== Render complete: {result['elapsed_seconds']}s ===")

        except Exception as e:
            result["error"] = str(e)
            self.log(f"ERROR: {e}")
            import traceback
            traceback.print_exc()

        return result

    def start(self, background: bool = True) -> "UE5RenderServer":
        """Start the HTTP server."""
        handler = UE5RenderHandler
        handler.server = self
        self._server = HTTPServer(("0.0.0.0", self.port), handler)

        if background:
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            self.log(f"Server started on port {self.port} (background thread)")
            unreal.log(f"[UE5] Forest render server listening on 0.0.0.0:{self.port}")
            unreal.log(f"[UE5] POST http://localhost:{self.port}/render to trigger a render")
        else:
            self.log(f"Server starting on port {self.port} (blocking)...")
            self._server.serve_forever()

        return self

    def stop(self) -> None:
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self.log("Server stopped")


_server_instance: Optional[UE5RenderServer] = None


def start_server(port: int = DEFAULT_PORT, background: bool = True) -> UE5RenderServer:
    """Start the UE5 render server (call this from inside UE5)."""
    global _server_instance
    if _server_instance is not None:
        unreal.log("[UE5] Server already running")
        return _server_instance
    _server_instance = UE5RenderServer(port=port)
    _server_instance.start(background=background)
    return _server_instance


def stop_server() -> None:
    """Stop the UE5 render server."""
    global _server_instance
    if _server_instance:
        _server_instance.stop()
        _server_instance = None


def render(
    usd_path: str,
    camera_location: tuple[float, float, float] = (5000, -5000, 2000),
    camera_look_at: tuple[float, float, float] = (0, 0, 500),
    output_path: Optional[str] = None,
    resolution: tuple[int, int] = (3840, 2160),
    sun_azimuth: float = 45.0,
    sun_elevation: float = 30.0,
    host: str = "localhost",
    port: int = DEFAULT_PORT,
) -> dict:
    """
    Client-side render trigger — sends a request to the UE5 server.

    This function runs in the Gradio/Python backend (outside UE5) and
    sends an HTTP POST to the UE5 server running inside UE5.

    Args:
        usd_path: Path to the generated .usdc/.usda file
        camera_location: Camera world position (x, y, z) in cm
        camera_look_at: Look-at point (x, y, z) in cm
        output_path: PNG output path (auto from usd_path if None)
        resolution: Output resolution (width, height) in pixels
        sun_azimuth: Sun horizontal angle (degrees)
        sun_elevation: Sun vertical angle (degrees)
        host: UE5 server hostname (default localhost)
        port: UE5 server port (default 8787)

    Returns:
        dict with render results
    """
    import urllib.request
    import urllib.error

    payload = {
        "usd_path": usd_path,
        "camera_location": list(camera_location),
        "camera_look_at": list(camera_look_at),
        "output_path": output_path,
        "resolution": list(resolution),
        "sun_azimuth": sun_azimuth,
        "sun_elevation": sun_elevation,
        "lumen": True,
        "nanite": True,
    }

    url = f"http://{host}:{port}/render"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {
            "success": False,
            "error": f"Could not connect to UE5 server at {url}. "
                     f"Is UE5 running with the server script loaded? "
                     f"Error: {e}",
        }


if __name__ == "__main__":
    if "unreal" not in sys.modules:
        raise RuntimeError(
            "This script must be run inside Unreal Engine 5 with "
            "the Python Editor Script Plugin enabled."
        )

    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    unreal.log(f"[UE5] Starting render server on port {port}...")
    start_server(port=port, background=False)
