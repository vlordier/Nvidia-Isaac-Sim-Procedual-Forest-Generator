from __future__ import annotations

import os
import numpy as np
from pathlib import Path
from typing import Optional, Sequence

from pxr import Gf, Usd, UsdGeom, Sdf, UsdPhysics, UsdLux

try:
    from pxr import PhysxSchema
except ImportError:
    PhysxSchema = None


def _load_mesh_geometry(file_path: str) -> tuple[np.ndarray, np.ndarray]:
    import trimesh
    scene = trimesh.load(file_path, force='scene')
    if isinstance(scene, trimesh.Trimesh):
        mesh = scene
    elif isinstance(scene, trimesh.Scene):
        if len(scene.geometry) == 0:
            raise ValueError(f"No geometry in {file_path}")
        mesh = list(scene.geometry.values())[0]
        if not isinstance(mesh, trimesh.Trimesh):
            mesh = mesh.copy()
    else:
        mesh = scene

    vertices = np.array(mesh.vertices, dtype=np.float32)
    if hasattr(mesh, 'faces'):
        triangles = np.array(mesh.faces, dtype=np.uint32)
    else:
        triangles = np.array([], dtype=np.uint32)
    return vertices, triangles


class USDStage:
    def __init__(
        self,
        output_path: Optional[str] = None,
    ):
        if output_path:
            self.stage = Usd.Stage.CreateNew(output_path)
        else:
            self.stage = Usd.Stage.CreateInMemory()

        self.output_path = output_path
        self._mesh_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self._setup_world_defaults()

    def _setup_world_defaults(self) -> None:
        stage = self.stage
        world_prim = stage.DefinePrim("/World", "Scope")
        stage.SetDefaultPrim(world_prim)

        physics_scene = UsdPhysics.Scene.Define(stage, Sdf.Path("/World/physicsScene"))
        physics_scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
        physics_scene.CreateGravityMagnitudeAttr().Set(981.0)

        self._add_default_camera_and_lighting()

    def _add_default_camera_and_lighting(self) -> None:
        stage = self.stage

        camera_prim = stage.DefinePrim("/World/mainCamera", "Camera")
        camera = UsdGeom.Camera(camera_prim)
        camera.CreateHorizontalApertureAttr().Set(20.0)
        camera.CreateVerticalApertureAttr().Set(11.25)
        camera.CreateHorizontalApertureOffsetAttr().Set(0.0)
        camera.CreateFocalLengthAttr().Set(50.0)
        camera.CreateClippingRangeAttr().Set(Gf.Vec2f(0.1, 10000.0))

        camera_xform = UsdGeom.Xformable(camera_prim)
        camera_xform.AddTranslateOp().Set(Gf.Vec3f(15.0, -15.0, 20.0))
        camera_xform.AddRotateXYZOp().Set(Gf.Vec3f(35.0, 45.0, 0.0))

        dome_light = UsdLux.DomeLight.Define(stage, Sdf.Path("/World/domeLight"))
        dome_light.CreateIntensityAttr().Set(2000.0)
        dome_light.CreateColorAttr().Set(Gf.Vec3f(0.9, 0.95, 1.0))
        dome_light.CreateDiffuseAttr().Set(0.5)

        dir_light = UsdLux.DistantLight.Define(stage, Sdf.Path("/World/sunLight"))
        dir_light.CreateIntensityAttr().Set(3.0)
        dir_light.CreateColorAttr().Set(Gf.Vec3f(1.0, 0.98, 0.9))
        sun_xform = UsdGeom.Xformable(stage.GetPrimAtPath("/World/sunLight"))
        sun_xform.AddRotateXYZOp().Set(Gf.Vec3f(-60.0, 30.0, 0.0))

        fill_light = UsdLux.DistantLight.Define(stage, Sdf.Path("/World/fillLight"))
        fill_light.CreateIntensityAttr().Set(0.8)
        fill_light.CreateColorAttr().Set(Gf.Vec3f(0.7, 0.8, 1.0))
        fill_xform = UsdGeom.Xformable(stage.GetPrimAtPath("/World/fillLight"))
        fill_xform.AddRotateXYZOp().Set(Gf.Vec3f(-30.0, -120.0, 0.0))

    def define_terrain(
        self,
        path: str,
        vertices: np.ndarray,
        triangles: np.ndarray,
        position: Optional[Sequence[float]] = None,
        orientation: Optional[Sequence[float]] = None,
    ) -> UsdGeom.Mesh:
        stage = self.stage
        prim = stage.DefinePrim(f"/World/{path}", "Mesh")
        mesh = UsdGeom.Mesh(prim)

        mesh.GetPointsAttr().Set(vertices)
        mesh.GetFaceVertexIndicesAttr().Set(triangles.flatten())
        mesh.GetFaceVertexCountsAttr().Set(np.asarray([3] * len(triangles)))

        xformable = UsdGeom.Xformable(prim)
        if position is not None:
            xformable.AddTranslateOp().Set(Gf.Vec3f(*position))
        if orientation is not None:
            xformable.AddOrientOp().Set(Gf.Quatf(*orientation))

        self._add_terrain_collision(prim)
        return mesh

    def _add_terrain_collision(self, prim: Usd.Prim) -> None:
        UsdPhysics.CollisionAPI.Apply(prim)
        collision_api = UsdPhysics.MeshCollisionAPI.Apply(prim)
        collision_api.CreateApproximationAttr().Set("triangleMesh")
        if PhysxSchema is not None:
            physx_collision_api = PhysxSchema.PhysxCollisionAPI.Apply(prim)
            physx_collision_api.GetContactOffsetAttr().Set(0.001)
            physx_collision_api.GetRestOffsetAttr().Set(0.00)

    def add_tree(
        self,
        prim_name: str,
        usd_path: str,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float, float],
        scale: tuple[float, float, float],
        parent: str = "/World/Tree_parent",
        display_color: tuple[float, float, float] = (0.13, 0.36, 0.13),
    ) -> None:
        self._add_asset_prim(
            prim_name=prim_name,
            usd_path=usd_path,
            position=position,
            rotation=rotation,
            scale=scale,
            parent=parent,
            kind="Mesh",
            display_color=display_color,
        )

    def add_rock(
        self,
        prim_name: str,
        usd_path: str,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float, float],
        scale: tuple[float, float, float],
        parent: str = "/World/Rock_parent",
        display_color: tuple[float, float, float] = (0.4, 0.35, 0.3),
    ) -> None:
        self._add_asset_prim(
            prim_name=prim_name,
            usd_path=usd_path,
            position=position,
            rotation=rotation,
            scale=scale,
            parent=parent,
            kind="Mesh",
            display_color=display_color,
        )

    def add_vegetation(
        self,
        prim_name: str,
        usd_path: str,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float, float],
        scale: tuple[float, float, float],
        parent: str = "/World/Bush_parent",
        display_color: tuple[float, float, float] = (0.15, 0.35, 0.1),
    ) -> None:
        self._add_asset_prim(
            prim_name=prim_name,
            usd_path=usd_path,
            position=position,
            rotation=rotation,
            scale=scale,
            parent=parent,
            kind="Mesh",
            display_color=display_color,
        )

    def _get_mesh_geometry(self, file_path: str) -> tuple[np.ndarray, np.ndarray]:
        if file_path not in self._mesh_cache:
            self._mesh_cache[file_path] = _load_mesh_geometry(file_path)
        return self._mesh_cache[file_path]

    def _add_asset_prim(
        self,
        prim_name: str,
        usd_path: str,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float, float],
        scale: tuple[float, float, float],
        parent: str,
        kind: str = "Mesh",
        display_color: tuple[float, float, float] = (0.5, 0.5, 0.5),
    ) -> None:
        stage = self.stage

        parent_prim = stage.GetPrimAtPath(parent)
        if not parent_prim:
            parent_prim = stage.DefinePrim(parent, "Scope")

        full_path = f"{parent}/{prim_name}"
        mesh_prim = stage.DefinePrim(full_path, kind)

        try:
            verts, tris = self._get_mesh_geometry(usd_path)
            mesh_api = UsdGeom.Mesh(mesh_prim)
            mesh_api.GetPointsAttr().Set(verts)
            mesh_api.GetFaceVertexIndicesAttr().Set(tris.flatten())
            mesh_api.GetFaceVertexCountsAttr().Set(np.asarray([3] * len(tris)))

            color = Gf.Vec3f(*display_color)
            mesh_api.GetDisplayColorAttr().Set([color])
        except Exception:
            pass

        xformable = UsdGeom.Xformable(mesh_prim)
        xformable.AddTranslateOp().Set(Gf.Vec3f(*position))
        xformable.AddOrientOp().Set(Gf.Quatf(*rotation))
        xformable.AddScaleOp().Set(Gf.Vec3f(*scale))
        xformable.SetResetXformStack(True)

    def set_camera(
        self,
        position: tuple[float, float, float],
        look_at: tuple[float, float, float],
        focal_length: float = 50.0,
    ) -> None:
        camera_prim = self.stage.GetPrimAtPath("/World/mainCamera")
        if not camera_prim:
            camera_prim = self.stage.DefinePrim("/World/mainCamera", "Camera")
        camera = UsdGeom.Camera(camera_prim)
        camera.CreateHorizontalApertureAttr().Set(20.0)
        camera.CreateVerticalApertureAttr().Set(11.25)
        camera.CreateFocalLengthAttr().Set(focal_length)
        camera.CreateClippingRangeAttr().Set(Gf.Vec2f(0.1, 10000.0))

        dx = look_at[0] - position[0]
        dy = look_at[1] - position[1]
        dz = look_at[2] - position[2]
        import math
        horiz = math.sqrt(dx * dx + dy * dy)
        yaw = math.degrees(math.atan2(dx, -dy)) if horiz > 0 else 0.0
        pitch = math.degrees(math.atan2(dz, horiz))

        camera_xform = UsdGeom.Xformable(camera_prim)
        existing_order = camera_prim.GetAttribute("xformOpOrder")
        if existing_order:
            existing_order.Clear()
        camera_xform.SetResetXformStack(True)
        camera_xform.AddTranslateOp().Set(Gf.Vec3f(*position))
        camera_xform.AddRotateXYZOp().Set(Gf.Vec3f(pitch, yaw, 0.0))

    def render_to_image(
        self,
        output_path: str,
        width: int = 1920,
        renderer: str = "Metal",
        camera_path: str = "/World/mainCamera",
    ) -> str:
        import subprocess
        usd_path = self.output_path
        if not usd_path:
            usd_path = "/tmp/temp_render.usdc"
            self.save_usdc(usd_path)

        cmd = [
            "usdrecord",
            usd_path,
            output_path,
            "--imageWidth", str(width),
            "--renderer", renderer,
            "--cam", camera_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"usdrecord failed: {result.stderr}")
        return output_path

    def remove_prim(self, path: str) -> bool:
        if self.stage.GetPrimAtPath(path):
            self.stage.RemovePrim(path)
            return True
        return False

    def clear_forest(self) -> None:
        self.remove_prim("/World/Tree_parent")
        self.remove_prim("/World/Bush_parent")

    def clear_rocks(self) -> None:
        self.remove_prim("/World/Rock_parent")

    def clear_terrain(self) -> None:
        self.remove_prim("/World/terrain")

    def save_usda(self, output_path: Optional[str] = None) -> str:
        path = output_path or self.output_path
        if not path:
            raise ValueError("No output path specified")
        if not path.endswith(".usda"):
            path = path.rsplit(".", 1)[0] + ".usda"
        self.stage.GetRootLayer().Export(path)
        return path

    def save_usdc(self, output_path: Optional[str] = None) -> str:
        path = output_path or self.output_path
        if not path:
            raise ValueError("No output path specified")
        if not path.endswith(".usdc"):
            path = path.rsplit(".", 1)[0] + ".usdc"
        self.stage.GetRootLayer().Export(path)
        return path

    def save(self, output_path: Optional[str] = None) -> str:
        return self.save_usda(output_path)

    def get_root_layer(self) -> Sdf.Layer:
        return self.stage.GetRootLayer()

    def get_stage(self) -> Usd.Stage:
        return self.stage
