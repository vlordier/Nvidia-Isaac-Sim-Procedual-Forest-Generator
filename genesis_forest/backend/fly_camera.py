import subprocess
import os
import math
import numpy as np
from typing import Optional, Callable

from pxr import Gf, Usd, UsdGeom, Sdf, UsdLux


class FlyCamera:
    def __init__(
        self,
        start_pos: tuple[float, float, float],
        end_pos: tuple[float, float, float],
        look_at: Optional[tuple[float, float, float]] = None,
        duration: float = 10.0,
        height: float = 3.0,
        sway: float = 0.5,
        sway_frequency: float = 0.3,
        look_ahead: float = 0.1,
    ):
        self.start_pos = np.array(start_pos, dtype=float)
        self.end_pos = np.array(end_pos, dtype=float)
        self.look_at = np.array(look_at, dtype=float) if look_at is not None else None
        self.duration = duration
        self.height = height
        self.sway = sway
        self.sway_frequency = sway_frequency
        self.look_ahead = look_ahead

    def get_position(self, t: float) -> np.ndarray:
        pos = self.start_pos + (self.end_pos - self.start_pos) * t
        pos[2] += self.height + self.sway * math.sin(2 * math.pi * self.sway_frequency * t)
        return pos

    def get_look_at(self, t: float) -> np.ndarray:
        if self.look_at is not None:
            return self.look_at
        look_t = min(t + self.look_ahead, 1.0)
        return self.start_pos + (self.end_pos - self.start_pos) * look_t


def catmull_rom_spline(points: np.ndarray, num_samples: int = 100) -> np.ndarray:
    if len(points) < 2:
        return points
    if len(points) == 2:
        return points

    result = []
    for i in range(len(points) - 1):
        p0 = points[max(i - 1, 0)]
        p1 = points[i]
        p2 = points[min(i + 1, len(points) - 1)]
        p3 = points[min(i + 2, len(points) - 1)]

        for j in range(num_samples):
            t = j / num_samples
            t2 = t * t
            t3 = t2 * t

            pos = 0.5 * (
                (2 * p1) +
                (-p0 + p2) * t +
                (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                (-p0 + 3 * p1 - 3 * p2 + p3) * t3
            )
            result.append(pos)

    result.append(points[-1])
    return np.array(result)


class PathFlyCamera:
    def __init__(
        self,
        waypoints: list[tuple[float, float, float]],
        duration: float = 10.0,
        look_at_waypoints: Optional[list[tuple[float, float, float]]] = None,
        height_offset: float = 0.0,
        sway: float = 0.3,
        sway_frequency: float = 0.2,
        loop: bool = False,
    ):
        self.raw_waypoints = np.array(waypoints, dtype=float)
        self.look_at_waypoints = np.array(look_at_waypoints, dtype=float) if look_at_waypoints else None
        self.duration = duration
        self.height_offset = height_offset
        self.sway = sway
        self.sway_frequency = sway_frequency
        self.loop = loop

        self.spline_points = catmull_rom_spline(self.raw_waypoints, num_samples=50)
        self.n_points = len(self.spline_points)

    def get_position(self, t: float) -> np.ndarray:
        idx = int(t * (self.n_points - 1))
        idx = min(idx, self.n_points - 1)
        pos = self.spline_points[idx].copy()
        pos[2] += self.height_offset + self.sway * math.sin(2 * math.pi * self.sway_frequency * t)
        return pos

    def get_look_at(self, t: float) -> np.ndarray:
        if self.look_at_waypoints is not None:
            idx = int(t * (len(self.look_at_waypoints) - 1))
            idx = min(idx, len(self.look_at_waypoints) - 1)
            return self.look_at_waypoints[idx]

        idx = int((t + 0.05) * (self.n_points - 1))
        idx = min(idx, self.n_points - 1)
        return self.spline_points[idx]


def render_flythrough(
    usd_path: str,
    output_path: str,
    camera: FlyCamera,
    fps: int = 30,
    width: int = 1280,
    height: int = 720,
    renderer: str = "Metal",
    camera_name: str = "/World/flyCamera",
    progress_callback=None,
) -> str:
    import shutil
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found - required for video encoding")

    tmp_dir = f"/tmp/flythrough_{os.getpid()}"
    os.makedirs(tmp_dir, exist_ok=True)

    total_frames = int(camera.duration * fps)

    for frame in range(total_frames):
        t = frame / total_frames
        pos = camera.get_position(t)
        look_at = camera.get_look_at(t)

        stage = Usd.Stage.Open(usd_path)

        cam_prim = stage.GetPrimAtPath(camera_name)
        if not cam_prim:
            cam_prim = stage.DefinePrim(camera_name, "Camera")

        cam = UsdGeom.Camera(cam_prim)
        cam.CreateHorizontalApertureAttr().Set(20.0)
        cam.CreateVerticalApertureAttr().Set(11.25)
        cam.CreateFocalLengthAttr().Set(50.0)
        cam.CreateClippingRangeAttr().Set(Gf.Vec2f(0.1, 10000.0))

        camera_xform = UsdGeom.Xformable(cam_prim)
        existing_order = cam_prim.GetAttribute("xformOpOrder")
        if existing_order:
            existing_order.Clear()
        camera_xform.SetResetXformStack(True)
        camera_xform.AddTranslateOp().Set(Gf.Vec3f(float(pos[0]), float(pos[1]), float(pos[2])))

        dx = look_at[0] - pos[0]
        dy = look_at[1] - pos[1]
        dz = look_at[2] - pos[2]
        horiz = math.sqrt(dx * dx + dy * dy)
        yaw = math.degrees(math.atan2(dx, -dy)) if horiz > 0 else 0.0
        pitch = math.degrees(math.atan2(dz, horiz))
        camera_xform.AddRotateXYZOp().Set(Gf.Vec3f(pitch, yaw, 0.0))

        frame_path = f"{tmp_dir}/frame_{frame:04d}.png"
        stage.GetRootLayer().Export(frame_path)

        if progress_callback:
            progress_callback((frame + 1) / total_frames, f"Frame {frame + 1}/{total_frames}")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", f"{tmp_dir}/frame_%04d.png",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        "-preset", "medium",
        output_path,
    ]

    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    for frame in range(total_frames):
        os.unlink(f"{tmp_dir}/frame_{frame:04d}.png")
    os.rmdir(tmp_dir)

    return output_path


def render_flythrough_single_pass(
    usd_path: str,
    output_path: str,
    camera: FlyCamera,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    renderer: str = "Metal",
    camera_name: str = "/World/flyCamera",
    progress_callback=None,
) -> str:
    import shutil
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found - required for video encoding")

    tmp_dir = f"/tmp/flythrough_{os.getpid()}"
    os.makedirs(tmp_dir, exist_ok=True)

    total_frames = int(camera.duration * fps)

    stage = Usd.Stage.Open(usd_path)
    cam_prim = stage.GetPrimAtPath(camera_name)
    if not cam_prim:
        cam_prim = stage.DefinePrim(camera_name, "Camera")

    cam = UsdGeom.Camera(cam_prim)
    cam.CreateHorizontalApertureAttr().Set(20.0)
    cam.CreateVerticalApertureAttr().Set(11.25)
    cam.CreateFocalLengthAttr().Set(50.0)
    cam.CreateClippingRangeAttr().Set(Gf.Vec2f(0.1, 10000.0))

    camera_xform = UsdGeom.Xformable(cam_prim)
    camera_xform.SetResetXformStack(True)

    stage.GetRootLayer().Export(usd_path)

    for frame in range(total_frames):
        t = frame / total_frames
        pos = camera.get_position(t)
        look_at = camera.get_look_at(t)

        stage = Usd.Stage.Open(usd_path)
        cam_prim = stage.GetPrimAtPath(camera_name)
        camera_xform = UsdGeom.Xformable(cam_prim)

        existing_order = cam_prim.GetAttribute("xformOpOrder")
        if existing_order:
            existing_order.Clear()
        camera_xform.SetResetXformStack(True)

        dx = look_at[0] - pos[0]
        dy = look_at[1] - pos[1]
        dz = look_at[2] - pos[2]
        horiz = math.sqrt(dx * dx + dy * dy)
        yaw = math.degrees(math.atan2(dx, -dy)) if horiz > 0 else 0.0
        pitch = math.degrees(math.atan2(dz, horiz))

        camera_xform.AddTranslateOp().Set(Gf.Vec3f(float(pos[0]), float(pos[1]), float(pos[2])))
        camera_xform.AddRotateXYZOp().Set(Gf.Vec3f(pitch, yaw, 0.0))

        frame_usd = f"{tmp_dir}/frame_{frame:04d}.usdc"
        frame_png = f"{tmp_dir}/frame_{frame:04d}.png"
        stage.GetRootLayer().Export(frame_usd)

        result = subprocess.run(
            ["usdrecord", frame_usd, frame_png, "--imageWidth", str(width), "--renderer", renderer, "--cam", camera_name],
            capture_output=True, text=True
        )
        os.unlink(frame_usd)

        if result.returncode != 0:
            print(f"Warning: usdrecord failed for frame {frame}: {result.stderr}")

        if progress_callback:
            progress_callback((frame + 1) / total_frames, f"Frame {frame + 1}/{total_frames}")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", f"{tmp_dir}/frame_%04d.png",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        "-preset", "medium",
        output_path,
    ]

    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    for frame in range(total_frames):
        png_path = f"{tmp_dir}/frame_{frame:04d}.png"
        if os.path.exists(png_path):
            os.unlink(png_path)
    os.rmdir(tmp_dir)

    return output_path


def create_straight_flythrough(
    start: tuple[float, float],
    end: tuple[float, float],
    z_height: float = 3.0,
    duration: float = 10.0,
    look_direction: str = "forward",
) -> FlyCamera:
    return FlyCamera(
        start_pos=(start[0], start[1], z_height),
        end_pos=(end[0], end[1], z_height),
        look_at=None,
        duration=duration,
        height=0,
        sway=0.3,
        sway_frequency=0.2,
    )


def create_circle_flythrough(
    center: tuple[float, float],
    radius: float,
    z_height: float = 3.0,
    duration: float = 20.0,
    start_angle: float = 0.0,
    look_at_center: bool = True,
) -> FlyCamera:
    start_x = center[0] + radius * math.cos(math.radians(start_angle))
    start_y = center[1] + radius * math.sin(math.radians(start_angle))
    end_angle = start_angle + 360
    end_x = center[0] + radius * math.cos(math.radians(end_angle))
    end_y = center[1] + radius * math.sin(math.radians(end_angle))

    return FlyCamera(
        start_pos=(start_x, start_y, z_height),
        end_pos=(end_x, end_y, z_height),
        look_at=(center[0], center[1], 0) if look_at_center else None,
        duration=duration,
        height=0,
        sway=0.2,
        sway_frequency=0.1,
    )


def create_spiral_flythrough(
    center: tuple[float, float],
    start_radius: float,
    end_radius: float,
    z_start: float = 3.0,
    z_end: float = 8.0,
    duration: float = 30.0,
    num_turns: float = 2.0,
) -> PathFlyCamera:
    waypoints = []
    num_points = int(num_turns * 20) + 1

    for i in range(num_points):
        t = i / (num_points - 1)
        angle = t * num_turns * 2 * math.pi
        r = start_radius + (end_radius - start_radius) * t
        z = z_start + (z_end - z_start) * t
        x = center[0] + r * math.cos(angle)
        y = center[1] + r * math.sin(angle)
        waypoints.append((x, y, z))

    return PathFlyCamera(
        waypoints=waypoints,
        duration=duration,
        height_offset=0,
        sway=0.5,
        sway_frequency=0.1,
    )


def create_forest_drone_flythrough(
    area_x: float,
    area_y: float,
    start_x: float = -8.0,
    start_y: float = -8.0,
    height: float = 2.0,
    duration: float = 15.0,
    figure_8: bool = True,
) -> PathFlyCamera:
    if figure_8:
        waypoints = [
            (start_x, start_y, height),
            (start_x + area_x * 0.15, start_y + area_y * 0.2, height + 0.2),
            (start_x + area_x * 0.35, start_y + area_y * 0.35, height + 0.3),
            (start_x + area_x * 0.5, start_y + area_y * 0.5, height + 0.4),
            (start_x + area_x * 0.65, start_y + area_y * 0.6, height + 0.3),
            (start_x + area_x * 0.8, start_y + area_y * 0.7, height + 0.2),
            (start_x + area_x * 0.85, start_y + area_y * 0.5, height + 0.4),
            (start_x + area_x * 0.7, start_y + area_y * 0.35, height + 0.3),
            (start_x + area_x * 0.5, start_y + area_y * 0.2, height + 0.2),
            (start_x + area_x * 0.3, start_y + area_y * 0.15, height + 0.3),
            (start_x, start_y, height),
        ]
        look_at_waypoints = [
            (start_x + area_x * 0.1, start_y + area_y * 0.1, height - 0.5),
            (start_x + area_x * 0.2, start_y + area_y * 0.3, height - 0.3),
            (start_x + area_x * 0.4, start_y + area_y * 0.45, height - 0.2),
            (start_x + area_x * 0.6, start_y + area_y * 0.6, height - 0.2),
            (start_x + area_x * 0.9, start_y + area_y * 0.8, height - 0.3),
            (start_x + area_x * 0.95, start_y + area_y * 0.6, height - 0.2),
            (start_x + area_x * 0.8, start_y + area_y * 0.4, height - 0.3),
            (start_x + area_x * 0.6, start_y + area_y * 0.25, height - 0.2),
            (start_x + area_x * 0.4, start_y + area_y * 0.1, height - 0.3),
            (start_x + area_x * 0.2, start_y + area_y * 0.05, height - 0.2),
            (start_x + area_x * 0.1, start_y + area_y * 0.1, height - 0.5),
        ]
    else:
        waypoints = [
            (start_x, start_y, height),
            (start_x + area_x * 0.2, start_y + area_y * 0.25, height + 0.2),
            (start_x + area_x * 0.4, start_y + area_y * 0.4, height + 0.3),
            (start_x + area_x * 0.6, start_y + area_y * 0.5, height + 0.4),
            (start_x + area_x * 0.8, start_y + area_y * 0.55, height + 0.3),
            (start_x + area_x * 0.75, start_y + area_y * 0.35, height + 0.2),
            (start_x + area_x * 0.5, start_y + area_y * 0.2, height + 0.3),
            (start_x, start_y, height),
        ]
        look_at_waypoints = [
            (start_x + area_x * 0.1, start_y + area_y * 0.15, height - 0.3),
            (start_x + area_x * 0.3, start_y + area_y * 0.35, height - 0.2),
            (start_x + area_x * 0.5, start_y + area_y * 0.5, height - 0.2),
            (start_x + area_x * 0.9, start_y + area_y * 0.65, height - 0.1),
            (start_x + area_x * 0.85, start_y + area_y * 0.4, height - 0.2),
            (start_x + area_x * 0.65, start_y + area_y * 0.25, height - 0.2),
            (start_x + area_x * 0.35, start_y + area_y * 0.1, height - 0.3),
            (start_x + area_x * 0.1, start_y + area_y * 0.15, height - 0.3),
        ]

    return PathFlyCamera(
        waypoints=waypoints,
        look_at_waypoints=look_at_waypoints,
        duration=duration,
        height_offset=0,
        sway=0.15,
        sway_frequency=0.1,
    )
