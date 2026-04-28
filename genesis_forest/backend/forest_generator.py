from __future__ import annotations

import numpy as np
from typing import Optional, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import genesis as gs
from genesis.utils.terrain import mesh_to_heightfield

from pathlib import Path
from .terrain import generate_terrain as _generate_terrain
from .tree_placement import (
    TreePlacement,
    generate_tree_placements,
    generate_rock_placements,
    generate_vegetation_placements,
)
from .usd_stage import USDStage


def _detect_genesis_backend() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return gs.cuda
    except Exception:
        pass
    try:
        if os.environ.get("RADEON_BACKEND", "").lower() in ("1", "true", "yes"):
            return gs.amdgpu
        if os.path.exists("/dev/kfd"):
            return gs.amdgpu
    except Exception:
        pass
    return gs.cpu


import os


ASSET_PATHS = {
    "Rock": "Rock_obj/Rock.usd",
    "Blueberry": "Blueberry_obj/Blueberry.usd",
    "Bush": "Bush_obj/Bush.usd",
    "Birch": "Birch_obj/Birch.usd",
    "Spruce": "Spruce_obj/Spruce.usd",
    "Pine": "Pine_obj/Pine.usd",
}


class HeightSampler:
    """
    Heightfield sampler for terrain.

    Provides O(1) height lookup at any world (x, y) position by sampling
    the Genesis-compatible heightfield array directly.

    The heightfield coordinate system:
    - hf[gj, gi] is the height at local position (gi * hs, gj * hs)
    - where gj = row index (Y direction), gi = col index (X direction)
    """

    def __init__(
        self,
        height_field: np.ndarray,
        horizontal_scale: float,
        vertical_scale: float,
        world_pos: tuple[float, float, float],
    ):
        self.height_field = height_field
        self.horizontal_scale = horizontal_scale
        self.vertical_scale = vertical_scale
        self.world_pos = world_pos
        self.n_rows, self.n_cols = height_field.shape

    def sample(self, world_x: float, world_y: float) -> float:
        """
        Get terrain height at world (x, y) position.
        Returns height in world units (meters).
        """
        local_x = world_x - self.world_pos[0]
        local_y = world_y - self.world_pos[1]

        gi = int(round(local_x / self.horizontal_scale))
        gj = int(round(local_y / self.horizontal_scale))

        gi = max(0, min(gi, self.n_cols - 1))
        gj = max(0, min(gj, self.n_rows - 1))

        return float(self.height_field[gj, gi] * self.vertical_scale)

    def sample_batch(self, points: np.ndarray) -> np.ndarray:
        """
        Batch height sampling for multiple (x, y) world positions.

        Args:
            points: array of shape (N, 2) with [x, y] world positions

        Returns:
            array of shape (N,) with heights in meters
        """
        n = points.shape[0]
        heights = np.empty(n, dtype=np.float32)

        for i in range(n):
            heights[i] = self.sample(points[i, 0], points[i, 1])

        return heights

    def sample_parallel(
        self,
        points: np.ndarray,
        max_workers: int = 32,
        callback: Optional[Callable[[int, int], None]] = None,
    ) -> np.ndarray:
        """
        Parallel batch height sampling.

        Genesis heightfield sampling is numpy-based (no GIL held during
        array ops), so ThreadPoolExecutor is effective for large point sets.
        """
        n = points.shape[0]
        if n == 0:
            return np.array([], dtype=np.float32)

        chunk_size = max(1, n // max_workers)
        results = np.empty(n, dtype=np.float32)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for start in range(0, n, chunk_size):
                end = min(start + chunk_size, n)
                chunk = points[start:end]
                future = executor.submit(self.sample_batch, chunk)
                futures[future] = (start, end)

            for i, future in enumerate(as_completed(futures)):
                start, end = futures[future]
                results[start:end] = future.result()
                if callback:
                    callback(i + 1, max_workers)

        return results


class USDStageBuilder:
    """Builds OpenUSD stage from Genesis entities after placement."""

    def __init__(self):
        self.stage = USDStage()

    def add_terrain(
        self,
        vertices: np.ndarray,
        triangles: np.ndarray,
        position: np.ndarray,
        orientation: np.ndarray,
    ) -> None:
        self.stage.define_terrain(
            "terrain",
            vertices,
            triangles,
            position=position.tolist(),
            orientation=orientation.tolist(),
        )
        self._terrain_verts = vertices
        self._terrain_tris = triangles
        self._terrain_pos = position
        self._terrain_orient = orientation

    def add_entity(
        self,
        prim_name: str,
        usd_path: str,
        world_pos: tuple[float, float, float],
        quat: tuple[float, float, float, float],
        scale: tuple[float, float, float],
        entity_type: str,
    ) -> None:
        parent = "/World/Tree_parent"
        if entity_type == "Rock":
            parent = "/World/Rock_parent"
        elif entity_type in ("Bush", "Blueberry"):
            parent = "/World/Bush_parent"

        self.stage._add_asset_prim(
            prim_name=prim_name,
            usd_path=usd_path,
            position=world_pos,
            rotation=quat,
            scale=scale,
            parent=parent,
        )

    def save_usda(self, path: str) -> str:
        return self.stage.save_usda(path)

    def save_usdc(self, path: str) -> str:
        return self.stage.save_usdc(path)


class ForestGenerator:
    """
    Genesis-authoritative procedural forest generator.

    Pipeline:
      1. Build Genesis terrain from heightfield (LOCAL coords to mesh_to_heightfield)
      2. Create HeightSampler from the same heightfield data
      3. Generate tree/rock/vegetation placements at Z=0 (terrain surface height)
         by sampling the HeightSampler
      4. Place entities in Genesis scene at correct Z (no raycasting needed)
      5. Query final world transforms from Genesis entities
      6. Write corrected prims to OpenUSD stage

    Key insight: Genesis terrain is a heightfield. We sample it directly
    (O(1) per point) instead of raycasting. This is both faster and
    the correct API for heightfield terrains.
    """

    def __init__(self, config: Optional["ForestConfig"] = None):
        from dataclasses import dataclass
        @dataclass
        class DefaultConfig:
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
            use_binary_usd: bool = True
            n_workers: int = 32

        self.config = config or DefaultConfig()
        self._backend = _detect_genesis_backend()
        self._scene: Optional[gs.Scene] = None
        self._height_sampler: Optional[HeightSampler] = None
        self._entities: list = []
        self._usd_builder: Optional[USDStageBuilder] = None
        self._closed = False

    def _init_scene(self) -> gs.Scene:
        if self._scene is not None:
            return self._scene
        gs.init(backend=self._backend)
        self._scene = gs.Scene(
            rigid_options=gs.options.RigidOptions(
                enable_collision=True,
                enable_joint_limit=False,
                constraint_solver=gs.constraint_solver.Newton,
            ),
        )
        return self._scene

    def _asset_path(self, key: str) -> str:
        base = self.config.asset_base_path
        return str(Path(base) / ASSET_PATHS.get(key, ASSET_PATHS["Birch"]))

    def build_terrain(self) -> HeightSampler:
        """
        Build Genesis terrain from LOCAL mesh coordinates.

        We generate vertices/triangles in local Genesis coords (origin at terrain corner),
        pass to mesh_to_heightfield, then create Terrain morph with world pos offset.

        Returns a HeightSampler so we can query terrain height at any (x, y)
        without needing to raycast.
        """
        cfg = self.config
        verts, tris, world_pos, world_orient = _generate_terrain(
            width=cfg.area_x,
            length=cfg.area_y,
            horizontal_scale=0.25,
            vertical_scale=0.005,
            roughness=cfg.roughness,
            slope_threshold=1.5,
        )

        hf, xs, ys = mesh_to_heightfield(
            verts,
            tris,
            horizontal_scale=0.25,
            vertical_scale=0.005,
            vertical_bounds=(verts[:, 2].min(), verts[:, 2].max()),
        )

        scene = self._init_scene()
        terrain_entity = scene.add_entity(
            gs.morphs.Terrain(
                height_field=hf,
                horizontal_scale=0.25,
                vertical_scale=0.005,
                pos=(float(world_pos[0]), float(world_pos[1]), float(world_pos[2])),
            ),
        )

        scene.build()

        self._terrain_entity = terrain_entity
        self._terrain_verts = verts
        self._terrain_tris = tris
        self._terrain_world_pos = world_pos
        self._terrain_world_orient = world_orient

        self._height_sampler = HeightSampler(
            height_field=hf,
            horizontal_scale=0.25,
            vertical_scale=0.005,
            world_pos=(float(world_pos[0]), float(world_pos[1]), float(world_pos[2])),
        )

        return self._height_sampler

    def place_entities(
        self,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        """
        Place tree/rock/vegetation entities in Genesis at correct Z heights.

        Heights come from HeightSampler.sample() — direct heightfield lookup,
        not raycasting. This is O(1) per entity.
        """
        cfg = self.config
        sampler = self._height_sampler
        scene = self._scene

        if progress_callback:
            progress_callback(0.05, "Generating placement data...")

        tree_placements = generate_tree_placements(
            density=cfg.density,
            birch_p=cfg.birch_p,
            spruce_p=cfg.spruce_p,
            pine_p=cfg.pine_p,
            area_x=float(cfg.area_x),
            area_y=float(cfg.area_y),
            age_min=cfg.age_min,
            age_max=cfg.age_max,
        )

        rock_placements = generate_rock_placements(
            rockiness=float(cfg.rockiness),
            area_x=float(cfg.area_x),
            area_y=float(cfg.area_y),
        )

        veg_placements = []
        if cfg.vegetation_enabled:
            veg_placements = generate_vegetation_placements(
                density=cfg.vegetation_density,
                area_x=float(cfg.area_x),
                area_y=float(cfg.area_y),
            )

        all_placements = tree_placements + rock_placements + veg_placements
        n_total = len(all_placements)

        if progress_callback and n_total > 0:
            progress_callback(0.1, f"Computing terrain heights for {n_total} objects...")

        points_xy = np.array([[p.position[0], p.position[1]] for p in all_placements], dtype=np.float32)

        if n_total > 500:
            heights = sampler.sample_parallel(points_xy, max_workers=cfg.n_workers)
        else:
            heights = sampler.sample_batch(points_xy)

        for placement, ground_z in zip(all_placements, heights):
            placement.position[2] = ground_z

        if progress_callback:
            progress_callback(0.3, f"Placing {n_total} entities in Genesis...")

        for i, placement in enumerate(all_placements):
            p = placement
            asset_path = self._asset_path(p.tree_type)

            entity = scene.add_entity(
                gs.morphs.Mesh(
                    file=asset_path,
                    pos=(float(p.position[0]), float(p.position[1]), float(p.position[2])),
                    quat=(float(p.rotation[0]), float(p.rotation[1]), float(p.rotation[2]), float(p.rotation[3])),
                    scale=(float(p.scale[0]), float(p.scale[1]), float(p.scale[2])),
                    collision=True,
                    visualization=True,
                ),
            )

            self._entities.append((entity, placement))

            if progress_callback and i % 200 == 0:
                progress_callback(0.3 + 0.4 * i / n_total, f"Placing entity {i}/{n_total}")

        self._all_placements = all_placements

    def build_usd_stage(
        self,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> USDStageBuilder:
        """
        Query final world transforms from Genesis entities and write to USD.

        Genesis is authoritative — we read back entity poses after any
        physics settling to get the true world transforms.
        """
        builder = USDStageBuilder()

        builder.add_terrain(
            self._terrain_verts,
            self._terrain_tris,
            self._terrain_world_pos,
            self._terrain_world_orient,
        )

        n = len(self._entities)
        for i, (entity, placement) in enumerate(self._entities):
            pos = entity.get_pos()
            quat = entity.get_quat()

            builder.add_entity(
                prim_name=f"{placement.tree_type}_{i:06d}",
                usd_path=self._asset_path(placement.tree_type),
                world_pos=(float(pos[0]), float(pos[1]), float(pos[2])),
                quat=(float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])),
                scale=(float(placement.scale[0]), float(placement.scale[1]), float(placement.scale[2])),
                entity_type=placement.tree_type,
            )

            if progress_callback and i % 200 == 0:
                progress_callback(0.75 + 0.2 * i / n, f"Writing USD prim {i}/{n}")

        self._usd_builder = builder
        return builder

    def generate(
        self,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> "GenerationResult":
        """
        Full pipeline: terrain → height sampling → entity placement → USD stage.
        """
        if progress_callback:
            progress_callback(0.0, "Building Genesis terrain + height sampler...")

        self.build_terrain()

        if progress_callback:
            progress_callback(0.05, "Placing entities at terrain heights...")

        self.place_entities(progress_callback)

        if progress_callback:
            progress_callback(0.75, "Writing OpenUSD stage...")

        builder = self.build_usd_stage(progress_callback)

        output_path = self.config.usd_output_path
        if self.config.use_binary_usd:
            final_path = builder.save_usdc(output_path)
        else:
            final_path = builder.save_usda(output_path)

        if progress_callback:
            progress_callback(1.0, "Done!")

        all_p = getattr(self, "_all_placements", [])
        tree_count = sum(1 for p in all_p if p.tree_type in ("Birch", "Spruce", "Pine"))
        rock_count = sum(1 for p in all_p if p.tree_type == "Rock")
        veg_count = sum(1 for p in all_p if p.tree_type in ("Bush", "Blueberry"))

        return GenerationResult(
            usd_path=final_path,
            n_trees=tree_count,
            n_rocks=rock_count,
            n_vegetation=veg_count,
            terrain_area=(self.config.area_x, self.config.area_y),
            roughness=self.config.roughness,
        )

    def shutdown(self) -> None:
        if self._scene is not None:
            del self._scene
            self._scene = None
            self._terrain_entity = None
            self._entities.clear()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.shutdown()


class GenerationResult:
    __slots__ = ("usd_path", "n_trees", "n_rocks", "n_vegetation", "terrain_area", "roughness")

    def __init__(
        self,
        usd_path: str,
        n_trees: int,
        n_rocks: int,
        n_vegetation: int,
        terrain_area: tuple[int, int],
        roughness: float,
    ):
        self.usd_path = usd_path
        self.n_trees = n_trees
        self.n_rocks = n_rocks
        self.n_vegetation = n_vegetation
        self.terrain_area = terrain_area
        self.roughness = roughness


class ForestConfig:
    __slots__ = (
        "density", "age_min", "age_max", "birch_p", "spruce_p", "pine_p",
        "area_x", "area_y", "roughness", "rockiness",
        "vegetation_enabled", "vegetation_density",
        "asset_base_path", "usd_output_path", "use_binary_usd", "n_workers",
    )

    def __init__(
        self,
        density: int = 10,
        age_min: int = 50,
        age_max: int = 100,
        birch_p: float = 33.33,
        spruce_p: float = 33.33,
        pine_p: float = 33.34,
        area_x: int = 100,
        area_y: int = 100,
        roughness: float = 1.0,
        rockiness: int = 5,
        vegetation_enabled: bool = True,
        vegetation_density: int = 5,
        asset_base_path: str = "D:/temp_downloads",
        usd_output_path: str = "./forest_output.usda",
        use_binary_usd: bool = True,
        n_workers: int = 32,
    ):
        self.density = density
        self.age_min = age_min
        self.age_max = age_max
        self.birch_p = birch_p
        self.spruce_p = spruce_p
        self.pine_p = pine_p
        self.area_x = area_x
        self.area_y = area_y
        self.roughness = roughness
        self.rockiness = rockiness
        self.vegetation_enabled = vegetation_enabled
        self.vegetation_density = vegetation_density
        self.asset_base_path = asset_base_path
        self.usd_output_path = usd_output_path
        self.use_binary_usd = use_binary_usd
        self.n_workers = n_workers
