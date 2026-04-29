from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Tuple
import noise


@dataclass
class SubTerrain:
    width: int = 256
    length: int = 256
    vertical_scale: float = 1.0
    horizontal_scale: float = 1.0
    height_field_raw: np.ndarray = field(default_factory=lambda: np.zeros((256, 256), dtype=np.int16))

    def __post_init__(self):
        self.height_field_raw = np.zeros((self.width, self.length), dtype=np.int16)


def random_uniform_terrain(
    terrain: SubTerrain,
    min_height: float,
    max_height: float,
    step: float = 1.0,
    downsampled_scale: Optional[float] = None,
    seed: Optional[int] = None,
) -> SubTerrain:
    if downsampled_scale is None:
        downsampled_scale = terrain.horizontal_scale

    min_h = int(min_height / terrain.vertical_scale)
    max_h = int(max_height / terrain.vertical_scale)

    if seed is None:
        seed = np.random.randint(0, 1000)

    num_rows = int(terrain.width * terrain.horizontal_scale / downsampled_scale)
    num_cols = int(terrain.length * terrain.horizontal_scale / downsampled_scale)
    height_field_down = np.zeros((num_rows, num_cols))

    for i in range(num_rows):
        for j in range(num_cols):
            x = i * downsampled_scale / (terrain.width * terrain.horizontal_scale)
            y = j * downsampled_scale / (terrain.length * terrain.horizontal_scale)
            height_field_down[i, j] = noise.pnoise2(x, y, octaves=6, base=seed)

    min_val = np.min(height_field_down)
    max_val = np.max(height_field_down)
    height_field_down = np.interp(height_field_down, (min_val, max_val), (min_h, max_h))

    height_field_extracted = height_field_down[:terrain.width, :terrain.length]

    x = np.linspace(0, terrain.width * terrain.horizontal_scale, height_field_extracted.shape[0])
    y = np.linspace(0, terrain.length * terrain.horizontal_scale, height_field_extracted.shape[1])

    from scipy.interpolate import RegularGridInterpolator
    f = RegularGridInterpolator((y, x), height_field_extracted, method="cubic", bounds_error=False, fill_value=None)

    x_up = np.linspace(0, terrain.width * terrain.horizontal_scale, terrain.width)
    y_up = np.linspace(0, terrain.length * terrain.horizontal_scale, terrain.length)
    z_up = f((y_up[:, None], x_up[None, :]))

    terrain.height_field_raw += z_up.astype(np.int16)
    return terrain


def convert_heightfield_to_trimesh(
    height_field_raw: np.ndarray,
    horizontal_scale: float,
    vertical_scale: float,
    slope_threshold: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    hf = height_field_raw
    num_rows = hf.shape[0]
    num_cols = hf.shape[1]

    y = np.linspace(0, (num_cols - 1) * horizontal_scale, num_cols)
    x = np.linspace(0, (num_rows - 1) * horizontal_scale, num_rows)
    yy, xx = np.meshgrid(y, x)

    if slope_threshold is not None:
        slope_threshold_scaled = slope_threshold * horizontal_scale / vertical_scale
        move_x = np.zeros((num_rows, num_cols))
        move_y = np.zeros((num_rows, num_cols))
        move_corners = np.zeros((num_rows, num_cols))

        move_x[:num_rows - 1, :] += (hf[1:num_rows, :] - hf[:num_rows - 1, :] > slope_threshold_scaled)
        move_x[1:num_rows, :] -= (hf[:num_rows - 1, :] - hf[1:num_rows, :] > slope_threshold_scaled)
        move_y[:, :num_cols - 1] += (hf[:, 1:num_cols] - hf[:, :num_cols - 1] > slope_threshold_scaled)
        move_y[:, 1:num_cols] -= (hf[:, :num_cols - 1] - hf[:, 1:num_cols] > slope_threshold_scaled)
        move_corners[:num_rows - 1, :num_cols - 1] += (
            hf[1:num_rows, 1:num_cols] - hf[:num_rows - 1, :num_cols - 1] > slope_threshold_scaled
        )
        move_corners[1:num_rows, 1:num_cols] -= (
            hf[:num_rows - 1, :num_cols - 1] - hf[1:num_rows, 1:num_cols] > slope_threshold_scaled
        )
        xx += (move_x + move_corners * (move_x == 0)) * horizontal_scale
        yy += (move_y + move_corners * (move_y == 0)) * horizontal_scale

    vertices = np.zeros((num_rows * num_cols, 3), dtype=np.float32)
    vertices[:, 0] = xx.flatten()
    vertices[:, 1] = yy.flatten()
    vertices[:, 2] = hf.flatten() * vertical_scale

    triangles = -np.ones((2 * (num_rows - 1) * (num_cols - 1), 3), dtype=np.uint32)
    for i in range(num_rows - 1):
        ind0 = np.arange(0, num_cols - 1) + i * num_cols
        ind1 = ind0 + 1
        ind2 = ind0 + num_cols
        ind3 = ind2 + 1
        start = 2 * i * (num_cols - 1)
        stop = start + 2 * (num_cols - 1)
        triangles[start:stop:2, 0] = ind0
        triangles[start:stop:2, 1] = ind3
        triangles[start:stop:2, 2] = ind1
        triangles[start + 1:stop:2, 0] = ind0
        triangles[start + 1:stop:2, 1] = ind2
        triangles[start + 1:stop:2, 2] = ind3

    return vertices, triangles


def generate_terrain(
    width: int,
    length: int,
    horizontal_scale: float = 0.25,
    vertical_scale: float = 0.005,
    roughness: float = 1.0,
    slope_threshold: float = 1.5,
    seed: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Generate terrain vertices, triangles, and world transform.

    Returns:
        vertices: LOCAL mesh coords (for Genesis mesh_to_heightfield)
        triangles: face indices
        position: world position offset (for USD stage)
        orientation: world orientation (quaternion, for USD stage)

    Note: position/orientation are for USD prim placement.
    Vertices are returned in LOCAL space (origin at 0,0,0).
    mesh_to_heightfield should receive LOCAL vertices + Genesis pos=(0,0,0).
    """
    num_rows = int(width / horizontal_scale)
    num_cols = int(length / horizontal_scale)
    heightfield = np.zeros((num_rows, num_cols), dtype=np.int16)

    terrain = SubTerrain(
        width=num_rows,
        length=num_cols,
        vertical_scale=vertical_scale,
        horizontal_scale=horizontal_scale,
    )

    half_roughness = roughness / 2.0
    terrain = random_uniform_terrain(
        terrain,
        min_height=-half_roughness,
        max_height=half_roughness,
        step=0.01,
        downsampled_scale=0.5,
        seed=seed,
    )

    heightfield[0:num_rows, :] = terrain.height_field_raw[0:num_rows, 0:num_cols]

    vertices, triangles = convert_heightfield_to_trimesh(
        heightfield,
        horizontal_scale=horizontal_scale,
        vertical_scale=vertical_scale,
        slope_threshold=slope_threshold,
    )

    position = np.array([-width / 2.0, length / 2.0, 0.0])
    orientation = np.array([0.70711, 0.0, 0.0, -0.70711])

    return vertices, triangles, position, orientation
