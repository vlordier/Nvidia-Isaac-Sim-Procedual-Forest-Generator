from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import numpy as np

import genesis as gs
from genesis.utils.terrain import mesh_to_heightfield

from .usd_stage import USDStage
from .terrain import generate_terrain
from .tree_placement import (
    generate_tree_placements,
    generate_rock_placements,
    generate_vegetation_placements,
    place_trees_with_raycast,
    TreePlacement,
)


ASSET_PATHS = {
    "Rock": "D:/temp_downloads/Rock_obj/Rock.usd",
    "Blueberry": "D:/temp_downloads/Blueberry_obj/Blueberry.usd",
    "Bush": "D:/temp_downloads/Bush_obj/Bush.usd",
    "Birch": "D:/temp_downloads/Birch_obj/Birch.usd",
    "Spruce": "D:/temp_downloads/Spruce_obj/Spruce.usd",
    "Pine": "D:/temp_downloads/Pine_obj/Pine.usd",
}


@dataclass
class ForestConfig:
    density: int = 10
    age_min: int = 50
    age_max: int = 100
    birch_p: float = 33.33
    spruce_p: float = 33.33
    pine_p: float = 33.34
    area_x: int = 100
    area_y: int = 100
    roughness: float = 1.0
    rockiness: int = 5
    vegetation_enabled: bool = True
    vegetation_density: int = 5
    asset_base_path: str = "D:/temp_downloads"
    usd_output_path: str = "./forest_output.usda"


@dataclass
class ForestState:
    tree_placements: list[TreePlacement] = field(default_factory=list)
    rock_placements: list[TreePlacement] = field(default_factory=list)
    vegetation_placements: list[TreePlacement] = field(default_factory=list)
    terrain_vertices: Optional[np.ndarray] = None
    terrain_triangles: Optional[np.ndarray] = None
    terrain_position: Optional[np.ndarray] = None
    terrain_orientation: Optional[np.ndarray] = None


class ForestGenerator:
    def __init__(self, config: Optional[ForestConfig] = None):
        self.config = config or ForestConfig()
        self._update_asset_paths()
        self.state = ForestState()
        self._genesis_scene: Optional[gs.Scene] = None
        self._terrain_entity: Optional[gs.Entity] = None

    def _update_asset_paths(self) -> None:
        base = self.config.asset_base_path
        self._asset_paths = {
            "Rock": f"{base}/Rock_obj/Rock.usd",
            "Blueberry": f"{base}/Blueberry_obj/Blueberry.usd",
            "Bush": f"{base}/Bush_obj/Bush.usd",
            "Birch": f"{base}/Birch_obj/Birch.usd",
            "Spruce": f"{base}/Spruce_obj/Spruce.usd",
            "Pine": f"{base}/Pine_obj/Pine.usd",
        }

    def _init_genesis(self) -> gs.Scene:
        if self._genesis_scene is not None:
            return self._genesis_scene

        gs.init(backend=gs.cpu)

        scene = gs.Scene(
            rigid_options=gs.options.RigidOptions(
                enable_collision=True,
                enable_joint_limit=True,
                constraint_solver=gs.constraint_solver.Newton,
            ),
        )

        self._genesis_scene = scene
        return scene

    def generate_terrain_genesis(self) -> gs.Entity:
        cfg = self.config
        verts, tris, pos, orient = generate_terrain(
            width=cfg.area_x,
            length=cfg.area_y,
            horizontal_scale=0.25,
            vertical_scale=0.005,
            roughness=cfg.roughness,
            slope_threshold=1.5,
        )

        self.state.terrain_vertices = verts
        self.state.terrain_triangles = tris
        self.state.terrain_position = pos
        self.state.terrain_orientation = orient

        heightfield, xs, ys = mesh_to_heightfield(
            verts,
            tris,
            horizontal_scale=0.25,
            vertical_scale=0.005,
            vertical_bounds=(verts[:, 2].min(), verts[:, 2].max()),
        )

        scene = self._init_genesis()

        terrain_entity = scene.add_entity(
            gs.morphs.Terrain(
                height_field=heightfield,
                horizontal_scale=0.25,
                vertical_scale=0.005,
                pos=(pos[0], pos[1], pos[2]),
            ),
        )

        self._terrain_entity = terrain_entity
        scene.build()

        return terrain_entity

    def generate_tree_placements(self) -> list[TreePlacement]:
        cfg = self.config
        placements = generate_tree_placements(
            density=cfg.density,
            birch_p=cfg.birch_p,
            spruce_p=cfg.spruce_p,
            pine_p=cfg.pine_p,
            area_x=float(cfg.area_x),
            area_y=float(cfg.area_y),
            age_min=cfg.age_min,
            age_max=cfg.age_max,
        )
        self.state.tree_placements = placements
        return placements

    def generate_rock_placements(self) -> list[TreePlacement]:
        cfg = self.config
        placements = generate_rock_placements(
            rockiness=float(cfg.rockiness),
            area_x=float(cfg.area_x),
            area_y=float(cfg.area_y),
        )
        self.state.rock_placements = placements
        return placements

    def generate_vegetation_placements(self) -> list[TreePlacement]:
        cfg = self.config
        if not cfg.vegetation_enabled:
            self.state.vegetation_placements = []
            return []
        placements = generate_vegetation_placements(
            density=cfg.vegetation_density,
            area_x=float(cfg.area_x),
            area_y=float(cfg.area_y),
        )
        self.state.vegetation_placements = placements
        return placements

    def raycast_placements(self) -> None:
        scene = self._genesis_scene
        if scene is None:
            return

        if self.state.tree_placements:
            self.state.tree_placements = place_trees_with_raycast(
                scene, self.state.tree_placements, max_distance=200.0
            )
        if self.state.rock_placements:
            self.state.rock_placements = place_trees_with_raycast(
                scene, self.state.rock_placements, max_distance=200.0
            )
        if self.state.vegetation_placements:
            self.state.vegetation_placements = place_trees_with_raycast(
                scene, self.state.vegetation_placements, max_distance=200.0
            )

    def generate_usd_stage(self) -> USDStage:
        stage = USDStage()

        if (
            self.state.terrain_vertices is not None
            and self.state.terrain_triangles is not None
            and self.state.terrain_position is not None
            and self.state.terrain_orientation is not None
        ):
            stage.define_terrain(
                "terrain",
                self.state.terrain_vertices,
                self.state.terrain_triangles,
                position=self.state.terrain_position,
                orientation=self.state.terrain_orientation,
            )

        for i, placement in enumerate(self.state.tree_placements):
            path = f"Tree_{str(i).rjust(4, '0')}"
            asset_path = self._asset_paths.get(placement.tree_type, self._asset_paths["Birch"])
            stage.add_tree(
                path,
                asset_path,
                position=tuple(placement.position),
                rotation=tuple(placement.rotation),
                scale=tuple(placement.scale),
            )

        for i, placement in enumerate(self.state.rock_placements):
            path = f"Rock_{str(i).rjust(4, '0')}"
            stage.add_rock(
                path,
                self._asset_paths["Rock"],
                position=tuple(placement.position),
                rotation=tuple(placement.rotation),
                scale=tuple(placement.scale),
            )

        for i, placement in enumerate(self.state.vegetation_placements):
            path = f"Plant_{str(i).rjust(4, '0')}"
            asset_path = self._asset_paths.get(placement.tree_type, self._asset_paths["Bush"])
            stage.add_vegetation(
                path,
                asset_path,
                position=tuple(placement.position),
                rotation=tuple(placement.rotation),
                scale=tuple(placement.scale),
            )

        return stage

    def generate_full(self) -> USDStage:
        self.generate_terrain_genesis()
        self.generate_tree_placements()
        self.generate_rock_placements()
        self.generate_vegetation_placements()
        self.raycast_placements()
        stage = self.generate_usd_stage()
        return stage

    def generate_to_file(self, output_path: Optional[str] = None) -> str:
        stage = self.generate_full()
        path = output_path or self.config.usd_output_path
        stage.save(path)
        return path

    def shutdown(self) -> None:
        if self._genesis_scene is not None:
            del self._genesis_scene
            self._genesis_scene = None
            self._terrain_entity = None
