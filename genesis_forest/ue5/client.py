"""
UE5 render client for Gradio — posts render requests to the UE5 server.

This module is imported by the Gradio app. It runs OUTSIDE UE5 (normal Python)
and sends HTTP requests to the UE5 server running inside UE5.

Usage:
    from ue5.client import UE5RenderClient

    client = UE5RenderClient(host="localhost", port=8787)
    result = client.render(
        usd_path="./forest_output.usdc",
        camera_location=(5000, -5000, 2000),
        camera_look_at=(0, 0, 500),
        resolution=(3840, 2160),
    )
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_PORT = 8787


@dataclass
class RenderParams:
    """Parameters for a UE5 render request."""
    usd_path: str
    camera_location: tuple[float, float, float] = (5000, -5000, 2000)
    camera_look_at: tuple[float, float, float] = (0, 0, 500)
    output_path: Optional[str] = None
    resolution: tuple[int, int] = (3840, 2160)
    sun_azimuth: float = 45.0
    sun_elevation: float = 30.0
    lumen: bool = True
    nanite: bool = True

    def to_dict(self) -> dict:
        return {
            "usd_path": self.usd_path,
            "camera_location": list(self.camera_location),
            "camera_look_at": list(self.camera_look_at),
            "output_path": self.output_path,
            "resolution": list(self.resolution),
            "sun_azimuth": self.sun_azimuth,
            "sun_elevation": self.sun_elevation,
            "lumen": self.lumen,
            "nanite": self.nanite,
        }


class UE5RenderClient:
    """
    HTTP client that sends render requests to the UE5 server.

    This runs in the Gradio backend (normal Python, outside UE5).
    It posts JSON to the UE5 server which runs inside Unreal Engine 5.
    """

    def __init__(self, host: str = "localhost", port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"

    def _post(self, path: str, payload: dict, timeout: int = 180) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def health_check(self) -> dict:
        """Check if UE5 server is reachable."""
        try:
            req = urllib.request.Request(f"{self.base_url}/health")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            return {"status": "error", "message": str(e), "ue5": False}

    def test_connection(self) -> dict:
        """Test the connection and return UE5 subsystem status."""
        try:
            req = urllib.request.Request(f"{self.base_url}/test")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            return {"status": "error", "message": str(e)}

    def render(self, params: RenderParams) -> dict:
        """
        Send a render request to the UE5 server.

        Args:
            params: RenderParams with all render settings

        Returns:
            dict with keys: success (bool), output_path (str), error (str or None),
            elapsed_seconds (float), camera_location, resolution, etc.
        """
        return self._post("/render", params.to_dict())

    def render_simple(
        self,
        usd_path: str,
        camera_location: tuple[float, float, float] = (5000, -5000, 2000),
        camera_look_at: tuple[float, float, float] = (0, 0, 500),
        output_path: Optional[str] = None,
        resolution: tuple[int, int] = (3840, 2160),
        sun_azimuth: float = 45.0,
        sun_elevation: float = 30.0,
    ) -> dict:
        """
        Convenience method — create RenderParams and send render request in one call.

        Args:
            usd_path: Path to the forest .usdc/.usda file
            camera_location: Camera world position (x, y, z) in cm
            camera_look_at: Look-at point (x, y, z) in cm
            output_path: PNG output path (auto from usd_path if None)
            resolution: Output resolution (width, height)
            sun_azimuth: Sun horizontal angle (degrees)
            sun_elevation: Sun vertical angle (degrees)

        Returns:
            Render result dict
        """
        params = RenderParams(
            usd_path=usd_path,
            camera_location=camera_location,
            camera_look_at=camera_look_at,
            output_path=output_path,
            resolution=resolution,
            sun_azimuth=sun_azimuth,
            sun_elevation=sun_elevation,
        )
        return self.render(params)


def check_ue5_status(host: str = "localhost", port: int = DEFAULT_PORT) -> dict:
    """
    Quick status check — returns UE5 server health.

    Returns:
        dict with status, ue5 (bool), and message
    """
    client = UE5RenderClient(host=host, port=port)
    return client.health_check()


def render_in_ue5(
    usd_path: str,
    camera_location: tuple[float, float, float] = (5000, -5000, 2000),
    camera_look_at: tuple[float, float, float] = (0, 0, 500),
    resolution: tuple[int, int] = (3840, 2160),
    sun_azimuth: float = 45.0,
    sun_elevation: float = 30.0,
    host: str = "localhost",
    port: int = DEFAULT_PORT,
) -> dict:
    """
    One-shot render — create client, send request, return result.

    This is the simplest integration for the Gradio callback.

    Args:
        usd_path: Path to .usdc/.usda from forest generator
        camera_location: Camera position (x, y, z) in cm
        camera_look_at: Look-at point (x, y, z) in cm
        resolution: Output resolution
        sun_azimuth: Sun horizontal angle (degrees)
        sun_elevation: Sun vertical angle (degrees)
        host: UE5 server hostname
        port: UE5 server port

    Returns:
        dict with render results
    """
    client = UE5RenderClient(host=host, port=port)
    return client.render_simple(
        usd_path=usd_path,
        camera_location=camera_location,
        camera_look_at=camera_look_at,
        resolution=resolution,
        sun_azimuth=sun_azimuth,
        sun_elevation=sun_elevation,
    )
