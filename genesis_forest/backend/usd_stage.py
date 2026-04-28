from __future__ import annotations

import os
import numpy as np
from pathlib import Path
from typing import Optional, Sequence

from pxr import Gf, Usd, UsdGeom, Sdf, UsdPhysics, PhysxSchema


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
        self._setup_world_defaults()

    def _setup_world_defaults(self) -> None:
        stage = self.stage
        world_prim = stage.DefinePrim("/World", "Scope")
        stage.SetDefaultPrim(world_prim)

        physics_scene = UsdPhysics.Scene.Define(stage, Sdf.Path("/World/physicsScene"))
        physics_scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
        physics_scene.CreateGravityMagnitudeAttr().Set(981.0)

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
            xformable.AddTranslateOp().Set(Gf.Vec3d(*position))
        if orientation is not None:
            xformable.AddOrientOp().Set(Gf.Quatd(*orientation))

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
        prim_name: str,
        usd_path: str,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float, float],
        scale: tuple[float, float, float],
        parent: str = "/World/Tree_parent",
    ) -> None:
        self._add_asset_prim(
            prim_name=prim_name,
            usd_path=usd_path,
            position=position,
            rotation=rotation,
            scale=scale,
            parent=parent,
            kind="Xform",
        )

    def add_rock(
        self,
        prim_name: str,
        usd_path: str,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float, float],
        scale: tuple[float, float, float],
        parent: str = "/World/Rock_parent",
    ) -> None:
        self._add_asset_prim(
            prim_name=prim_name,
            usd_path=usd_path,
            position=position,
            rotation=rotation,
            scale=scale,
            parent=parent,
            kind="Xform",
        )

    def add_vegetation(
        self,
        prim_name: str,
        usd_path: str,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float, float],
        scale: tuple[float, float, float],
        parent: str = "/World/Bush_parent",
    ) -> None:
        self._add_asset_prim(
            prim_name=prim_name,
            usd_path=usd_path,
            position=position,
            rotation=rotation,
            scale=scale,
            parent=parent,
            kind="Xform",
        )

    def _add_asset_prim(
        self,
        prim_name: str,
        usd_path: str,
        position: tuple[float, float, float],
        rotation: tuple[float, float, float, float],
        scale: tuple[float, float, float],
        parent: str,
        kind: str = "Xform",
    ) -> None:
        stage = self.stage

        parent_prim = stage.GetPrimAtPath(parent)
        if not parent_prim:
            parent_prim = stage.DefinePrim(parent, "Scope")

        full_path = f"{parent}/{prim_name}"
        xform_prim = stage.DefinePrim(full_path, kind)

        refs = xform_prim.GetReferences()
        refs.AddReference(usd_path)

        xformable = UsdGeom.Xformable(xform_prim)
        xformable.AddTranslateOp().Set(Gf.Vec3d(*position))
        xformable.AddOrientOp().Set(Gf.Quatd(*rotation))
        xformable.AddScaleOp().Set(Gf.Vec3d(*scale))

        xformable.SetResetXformStack(True)

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
