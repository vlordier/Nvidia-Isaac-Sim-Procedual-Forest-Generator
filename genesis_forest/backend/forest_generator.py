from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Optional, Callable

import numpy as np

import genesis as gs
from genesis.utils.terrain import mesh_to_heightfield

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


def _get_genesis_version() -> tuple[int, ...]:
    try:
        import genesis
        v = getattr(genesis, "__version__", None)
        if v is None:
            v = getattr(genesis, "version", None)
        if isinstance(v, str):
            return tuple(int(x) for x in v.split(".")[:2])
    except Exception:
        pass
    return (0, 0)


def _check_usd_support() -> bool:
    try:
        import usd
        return True
    except ImportError:
        return False


SUPPORTED_MESH_EXTENSIONS = {".usd", ".usda", ".usdc", ".obj", ".glb", ".gltf", ".stl", ".ply"}


def _find_asset(path: str) -> Optional[str]:
    p = Path(path)
    if p.exists():
        return str(p.resolve())
    for ext in SUPPORTED_MESH_EXTENSIONS:
        alt = p.with_suffix(ext)
        if alt.exists():
            return str(alt.resolve())
    return None


class AssetLoader:
    """
    Resolves and validates mesh assets for Genesis.

    Genesis Mesh morph supports: USD (with [usd] extras), GLB, OBJ, STL, PLY.
    We try to find the asset with any supported extension, then load with
    appropriate options for each format.
    """

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.usd_available = _check_usd_support()
        self.genesis_version = _get_genesis_version()

    def resolve(self, key: str) -> tuple[Optional[str], Optional[str]]:
        """
        Resolve an asset key to a file path.

        Returns:
            (resolved_path, format_hint) or (None, None) if not found

        format_hint is 'usd', 'glb', or 'obj' for Genesis loader selection.
        """
        candidate = self.base_path / key
        found = _find_asset(str(candidate))
        if found is None:
            return None, None

        ext = Path(found).suffix.lower()
        if ext in (".usd", ".usda", ".usdc"):
            if not self.usd_available:
                warnings.warn(
                    f"USD asset {found} requires 'pip install -e .[usd]' + omniverse-kit. "
                    f"Skipping. Convert to .glb or .obj for fallback.",
                    UserWarning,
                )
                return None, None
            return found, "usd"
        elif ext in (".glb", ".gltf"):
            return found, "glb"
        elif ext in (".obj", ".stl", ".ply"):
            return found, "obj"
        return found, "obj"

    def mesh_options(
        self,
        resolved_path: str,
        format_hint: str,
        pos: tuple,
        quat: tuple,
        scale: tuple,
        for_visualization: bool = True,
    ) -> dict:
        """
        Build gs.morphs.Mesh kwargs for a resolved asset.

        Key settings:
        - fixed=True: no physics DOFs, entity is static
        - collision=False: no convex hull collision (trees are static)
        - decimate=False: preserve visual quality (decimation is for physics speed)
        - parse_glb_with_trimesh=True: use trimesh parser for GLB (better material support)
        """
        kwargs = dict(
            file=resolved_path,
            pos=pos,
            quat=quat,
            scale=scale,
            fixed=True,
            collision=False,
            visualization=for_visualization,
            decimate=False,
            convexify=False,
        )
        if format_hint == "glb":
            kwargs["parse_glb_with_trimesh"] = True
        return kwargs


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

    Provides O(1) height lookup at any world (x, y) via bilinear interpolation
    of the underlying heightfield grid.
    """

    def __init__(
        self,
        height_field: np.ndarray,
        horizontal_scale: float,
        vertical_scale: float,
        world_pos: tuple[float, float, float],
    ):
        self.height_field = height_field.astype(np.float64)
        self.horizontal_scale = horizontal_scale
        self.vertical_scale = vertical_scale
        self.world_pos = world_pos
        self.n_rows, self.n_cols = height_field.shape

    def sample(self, world_x: float, world_y: float) -> float:
        local_x = world_x - self.world_pos[0]
        local_y = world_y - self.world_pos[1]

        gi = local_x / self.horizontal_scale
        gj = local_y / self.horizontal_scale

        gi0, gj0 = int(np.floor(gi)), int(np.floor(gj))
        gi1, gj1 = gi0 + 1, gj0 + 1

        w00 = (gi1 - gi) * (gj1 - gj)
        w01 = (gi1 - gi) * (gj - gj0)
        w10 = (gi - gi0) * (gj1 - gj)
        w11 = (gi - gi0) * (gj - gj0)

        gi0_c = max(0, min(gi0, self.n_cols - 1))
        gj0_c = max(0, min(gj0, self.n_rows - 1))
        gi1_c = max(0, min(gi1, self.n_cols - 1))
        gj1_c = max(0, min(gj1, self.n_rows - 1))

        h00 = float(self.height_field[gj0_c, gi0_c])
        h01 = float(self.height_field[gj1_c, gi0_c])
        h10 = float(self.height_field[gj0_c, gi1_c])
        h11 = float(self.height_field[gj1_c, gi1_c])

        h = w00 * h00 + w01 * h01 + w10 * h10 + w11 * h11
        return h * self.vertical_scale

    def sample_batch(self, points: np.ndarray) -> np.ndarray:
        n = points.shape[0]
        heights = np.empty(n, dtype=np.float64)
        for i in range(n):
            heights[i] = self.sample(points[i, 0], points[i, 1])
        return heights


class ForestGenerator:
    """
    Genesis-authoritative procedural forest generator.

    Pipeline:
      1. Validate all asset paths exist
      2. Build Genesis terrain from heightfield (local coords)
      3. HeightSampler: O(1) bilinear height lookup at any (x, y)
      4. Place tree/rock/vegetation entities at correct Z
         - fixed=True (static, no physics DOFs)
         - collision=False (no convex hull overhead)
      5. scene.build() + scene.step() — let physics settle
      6. Query final transforms from Genesis → write to OpenUSD
    """

    def __init__(self, config: Optional["ForestConfig"] = None):
        self.config = config or ForestConfig()
        self._backend = _detect_genesis_backend()
        self._scene: Optional[gs.Scene] = None
        self._height_sampler: Optional[HeightSampler] = None
        self._entities: list = []
        self._closed = False
        self._genesis_version = _get_genesis_version()

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

    def _validate_assets(self) -> dict[str, tuple[str, str]]:
        """
        Validate all required assets exist and can be loaded.

        Returns:
            dict mapping asset key -> (resolved_path, format_hint)

        Raises:
            FileNotFoundError if any required asset is missing
        """
        base = self.config.asset_base_path
        loader = AssetLoader(base)
        resolved = {}

        for key, rel_path in ASSET_PATHS.items():
            found, fmt = loader.resolve(rel_path)
            if found is None:
                raise FileNotFoundError(
                    f"Asset not found: {rel_path} (searched in {base}). "
                    f"Install USD support: pip install -e .[usd] or convert to .glb/.obj"
                )
            resolved[key] = (found, fmt)

        return resolved

    def build_terrain(self) -> HeightSampler:
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
                pos=(0.0, 0.0, 0.0),
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
        resolved_assets: dict,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> None:
        cfg = self.config
        sampler = self._height_sampler
        scene = self._scene
        loader = AssetLoader(cfg.asset_base_path)

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

        points_xy = np.array(
            [[p.position[0], p.position[1]] for p in all_placements], dtype=np.float64
        )
        heights = sampler.sample_batch(points_xy)

        for placement, ground_z in zip(all_placements, heights):
            placement.position[2] = ground_z

        if progress_callback:
            progress_callback(0.3, f"Placing {n_total} entities in Genesis...")

        for i, placement in enumerate(all_placements):
            p = placement
            resolved_path, fmt = resolved_assets.get(p.tree_type, resolved_assets["Birch"])

            mesh_kwargs = loader.mesh_options(
                resolved_path=resolved_path,
                format_hint=fmt,
                pos=(float(p.position[0]), float(p.position[1]), float(p.position[2])),
                quat=(float(p.rotation[0]), float(p.rotation[1]), float(p.rotation[2]), float(p.rotation[3])),
                scale=(float(p.scale[0]), float(p.scale[1]), float(p.scale[2])),
            )

            entity = scene.add_entity(gs.morphs.Mesh(**mesh_kwargs))
            self._entities.append((entity, placement))

            if progress_callback and i % 200 == 0:
                progress_callback(0.3 + 0.3 * i / n_total, f"Placing entity {i}/{n_total}")

        self._all_placements = all_placements

    def _settle_physics(self, n_steps: int = 10) -> None:
        """
        Run scene.step() to let physics settle.

        Even though trees are fixed (no DOFs), this ensures the terrain
        collision is properly resolved and Genesis world is consistent.

        With fixed=True entities, scene.step() is essentially free (no joint solving).
        """
        if self._scene is None:
            return
        for _ in range(n_steps):
            self._scene.step()

    def build_usd_stage(
        self,
        resolved_assets: dict,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> USDStage:
        from .usd_stage import USDStage

        output_path = self.config.usd_output_path
        usd_path = output_path.rsplit(".", 1)[0] + (".usdc" if self.config.use_binary_usd else ".usda")

        stage = USDStage(output_path=usd_path)

        stage.define_terrain(
            path="terrain",
            vertices=self._terrain_verts,
            triangles=self._terrain_tris,
            position=[float(self._terrain_world_pos[0]), float(self._terrain_world_pos[1]), float(self._terrain_world_pos[2])],
            orientation=[float(self._terrain_world_orient[0]), float(self._terrain_world_orient[1]), float(self._terrain_world_orient[2]), float(self._terrain_world_orient[3])],
        )

        n = len(self._entities)
        for i, (entity, placement) in enumerate(self._entities):
            pos = entity.get_pos()
            quat = entity.get_quat()
            resolved_path, _ = resolved_assets.get(placement.tree_type, resolved_assets["Birch"])

            pos_tuple = (float(pos[0]), float(pos[1]), float(pos[2]))
            quat_tuple = (float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3]))
            scale_tuple = (float(placement.scale[0]), float(placement.scale[1]), float(placement.scale[2]))

            prim_name = f"{placement.tree_type}_{i:06d}"

            if placement.tree_type == "Rock":
                stage.add_rock(
                    prim_name=prim_name,
                    usd_path=resolved_path,
                    position=pos_tuple,
                    rotation=quat_tuple,
                    scale=scale_tuple,
                )
            elif placement.tree_type in ("Bush", "Blueberry"):
                stage.add_vegetation(
                    prim_name=prim_name,
                    usd_path=resolved_path,
                    position=pos_tuple,
                    rotation=quat_tuple,
                    scale=scale_tuple,
                )
            else:
                stage.add_tree(
                    prim_name=prim_name,
                    usd_path=resolved_path,
                    position=pos_tuple,
                    rotation=quat_tuple,
                    scale=scale_tuple,
                )

            if progress_callback and i % 200 == 0:
                progress_callback(0.75 + 0.2 * i / n, f"Writing USD prim {i}/{n}")

        return stage

    def generate(
        self,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> "GenerationResult":
        if progress_callback:
            progress_callback(0.0, "Validating assets...")

        resolved_assets = self._validate_assets()

        if progress_callback:
            progress_callback(0.01, "Building Genesis terrain + height sampler...")

        self.build_terrain()

        if progress_callback:
            progress_callback(0.05, "Placing entities at terrain heights...")

        self.place_entities(resolved_assets, progress_callback)

        if progress_callback:
            progress_callback(0.65, "Settling physics (scene.step())...")

        self._settle_physics(n_steps=10)

        if progress_callback:
            progress_callback(0.75, "Writing OpenUSD stage...")

        builder = self.build_usd_stage(resolved_assets, progress_callback)

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
            genesis_version=self._genesis_version,
            usd_support=self.config.asset_base_path,
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


class GenerationResult:
    __slots__ = (
        "usd_path", "n_trees", "n_rocks", "n_vegetation",
        "terrain_area", "roughness", "genesis_version", "usd_support",
    )

    def __init__(
        self,
        usd_path: str,
        n_trees: int,
        n_rocks: int,
        n_vegetation: int,
        terrain_area: tuple[int, int],
        roughness: float,
        genesis_version: tuple[int, ...],
        usd_support: str,
    ):
        self.usd_path = usd_path
        self.n_trees = n_trees
        self.n_rocks = n_rocks
        self.n_vegetation = n_vegetation
        self.terrain_area = terrain_area
        self.roughness = roughness
        self.genesis_version = genesis_version
        self.usd_support = usd_support
