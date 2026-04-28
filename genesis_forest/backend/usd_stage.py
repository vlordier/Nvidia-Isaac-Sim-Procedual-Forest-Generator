from __future__ import annotations

import numpy as np
from pathlib import Path
from typing import Optional

from pxr import Gf, Usd, UsdGeom, Sdf, UsdPhysics, PhysxSchema


class USDStage:
    def __init__(
        self,
        output_path: Optional[str] = None,
        stage_options: Optional[Usd.StagePopulationMask] = None,
    ):
        if output_path:
            self.stage = Usd.Stage.CreateNew(output_path)
        else:
            self.stage = Usd.Stage.CreateInMemory()

        self.output_path = output_path
        self._setup_world_defaults()

    def _setup_world_defaults(self) -> None:
        stage = self.stage
        stage.SetDefaultPrim(stage.DefinePrim("/World", "Scope"))

        physics_scene = UsdPhysics.Scene.Define(stage, Sdf.Path("/World/physicsScene"))
        physics_scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
        physics_scene.CreateGravityMagnitudeAttr().Set(981.0)

    def define_terrain(
        self,
        path: str,
        vertices: np.ndarray,
        triangles: np.ndarray,
        position: Optional[np.ndarray] = None,
        orientation: Optional[np.ndarray] = None,
    ) -> UsdGeom.Mesh:
        stage = self.stage
        prim = stage.DefinePrim(f"/World/{path}", "Mesh")
        mesh = UsdGeom.Mesh(prim)

        mesh.GetPointsAttr().Set(vertices)
        mesh.GetFaceVertexIndicesAttr().Set(triangles.flatten())
        mesh.GetFaceVertexCountsAttr().Set(np.asarray([3] * len(triangles)))

        if position is not None:
            xform = UsdGeom.Xformable(prim)
            xform.AddTranslateOp().Set(Gf.Vec3d(*position))
        if orientation is not None:
            xform = UsdGeom.Xformable(prim)
            xform.AddOrientOp().Set(Gf.Quatd(*orientation))

        self._add_terrain_collision(prim)
        return mesh

    def _add_terrain_collision(self, prim: Usd.Prim) -> None:
        UsdPhysics.CollisionAPI.Apply(prim)
        collision_api = UsdPhysics.MeshCollisionAPI.Apply(prim)
        collision_api.CreateApproximationAttr().Set("triangleMesh")
        physx_collision_api = PhysxSchema.PhysxCollisionAPI.Apply(prim)
        physx_collision_api.GetContactOffsetAttr().Set(0.001)
        physx_collision_api.GetRestOffsetAttr().Set(0.00)

    def add_tree(
        self,
        tree_path: str,
        usd_path: str,
        position: tuple[float, float, float],
        rotation: Optional[tuple[float, float, float, float]] = None,
        scale: Optional[tuple[float, float, float]] = None,
        parent: str = "/World/Tree_parent",
    ) -> None:
        stage = self.stage

        parent_prim = stage.GetPrimAtPath(parent)
        if not parent_prim:
            stage.DefinePrim(parent, "Scope")

        full_path = f"{parent}/{tree_path}"
        xform = stage.DefinePrim(full_path, "Xform")

        stage.DefinePrim(f"{full_path}/Geometry", "Scope")
        stage.GetRootLayer().Import(usd_path, prim_path=f"{full_path}/Geometry")

        xformable = UsdGeom.Xformable(xform)
        xformable.AddTranslateOp().Set(Gf.Vec3d(*position))

        if rotation:
            xformable.AddOrientOp().Set(Gf.Quatd(*rotation))
        else:
            xformable.AddOrientOp().Set(Gf.Quatd(1, 0, 0, 0))

        if scale:
            xformable.AddScaleOp().Set(Gf.Vec3d(*scale))
        else:
            xformable.AddScaleOp().Set(Gf.Vec3d(1, 1, 1))

    def add_rock(
        self,
        rock_path: str,
        usd_path: str,
        position: tuple[float, float, float],
        rotation: Optional[tuple[float, float, float, float]] = None,
        scale: Optional[tuple[float, float, float]] = None,
        parent: str = "/World/Rock_parent",
    ) -> None:
        self.add_tree(rock_path, usd_path, position, rotation, scale, parent)

    def add_vegetation(
        self,
        plant_path: str,
        usd_path: str,
        position: tuple[float, float, float],
        rotation: Optional[tuple[float, float, float, float]] = None,
        scale: Optional[tuple[float, float, float]] = None,
        parent: str = "/World/Bush_parent",
    ) -> None:
        self.add_tree(plant_path, usd_path, position, rotation, scale, parent)

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

    def save(self, output_path: Optional[str] = None) -> str:
        path = output_path or self.output_path
        if not path:
            raise ValueError("No output path specified")
        self.stage.GetRootLayer().Export(path)
        return path

    def get_root_layer(self) -> Sdf.Layer:
        return self.stage.GetRootLayer()
