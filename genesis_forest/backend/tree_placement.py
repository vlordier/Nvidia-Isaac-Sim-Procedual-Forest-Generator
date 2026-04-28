from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, Literal, List, Tuple

import numpy as np


@dataclass
class TreePlacement:
    tree_type: Literal["Birch", "Spruce", "Pine", "Rock", "Blueberry", "Bush"]
    position: np.ndarray
    rotation: np.ndarray
    scale: np.ndarray


def euler_to_quaternion(roll: float, pitch: float, yaw: float) -> Tuple[float, float, float, float]:
    roll_rad = np.radians(roll)
    pitch_rad = np.radians(pitch)
    yaw_rad = np.radians(yaw)

    qx = np.sin(roll_rad / 2) * np.cos(pitch_rad / 2) * np.cos(yaw_rad / 2) - np.cos(roll_rad / 2) * np.sin(pitch_rad / 2) * np.sin(yaw_rad / 2)
    qy = np.cos(roll_rad / 2) * np.sin(pitch_rad / 2) * np.cos(yaw_rad / 2) + np.sin(roll_rad / 2) * np.cos(pitch_rad / 2) * np.sin(yaw_rad / 2)
    qz = np.cos(roll_rad / 2) * np.cos(pitch_rad / 2) * np.sin(yaw_rad / 2) - np.sin(roll_rad / 2) * np.sin(pitch_rad / 2) * np.cos(yaw_rad / 2)
    qw = np.cos(roll_rad / 2) * np.cos(pitch_rad / 2) * np.cos(yaw_rad / 2) + np.sin(roll_rad / 2) * np.sin(pitch_rad / 2) * np.sin(yaw_rad / 2)

    return qw, qx, qy, qz


def random_yaw_rotation() -> np.ndarray:
    yaw = random.uniform(-180, 180)
    qw, qx, qy, qz = euler_to_quaternion(0, 0, yaw)
    return np.array([qw, qx, qy, qz])


def calculate_growth_multiplier(age_min: int, age_max: int) -> float:
    age = random.randint(age_min, age_max)
    return age / 100.0


def generate_tree_placements(
    density: int,
    birch_p: float,
    spruce_p: float,
    pine_p: float,
    area_x: float,
    area_y: float,
    age_min: int,
    age_max: int,
) -> List[TreePlacement]:
    total_trees = int(density * (area_x * area_y) / 100.0)
    area_x_half = (area_x / 2.0) - 0.4
    area_y_half = (area_y / 2.0) - 0.4

    placements: List[TreePlacement] = []
    n_birch = int(total_trees * birch_p / 100)
    n_spruce = int(total_trees * spruce_p / 100)
    n_pine = total_trees - n_birch - n_spruce

    for _ in range(n_birch):
        placements.append(_make_tree_placement("Birch", 1.35, area_x_half, area_y_half, age_min, age_max))
    for _ in range(n_spruce):
        placements.append(_make_tree_placement("Spruce", 1.25, area_x_half, area_y_half, age_min, age_max))
    for _ in range(n_pine):
        placements.append(_make_tree_placement("Pine", 1.35, area_x_half, area_y_half, age_min, age_max))

    return placements


def _make_tree_placement(
    tree_type: str,
    height_mult: float,
    area_x_half: float,
    area_y_half: float,
    age_min: int,
    age_max: int,
) -> TreePlacement:
    overall_scale = 1.0
    growth_mult = calculate_growth_multiplier(age_min, age_max)

    scale = random.uniform(0.9, 1.1) * growth_mult * overall_scale
    height = random.uniform(0.9, 1.1) * height_mult * growth_mult * overall_scale

    x = random.uniform(-area_x_half, area_x_half)
    y = random.uniform(-area_y_half, area_y_half)
    position = np.array([x, y, 0.0])
    rotation = random_yaw_rotation()
    scale_vec = np.array([scale, scale, height])

    return TreePlacement(tree_type=tree_type, position=position, rotation=rotation, scale=scale_vec)


def generate_rock_placements(rockiness: float, area_x: float, area_y: float) -> List[TreePlacement]:
    total_rocks = int(rockiness * (area_x * area_y) / 100.0)
    area_x_half = (area_x / 2.0) - 0.3
    area_y_half = (area_y / 2.0) - 0.3

    placements: List[TreePlacement] = []
    for _ in range(total_rocks):
        x = random.uniform(-area_x_half, area_x_half)
        y = random.uniform(-area_y_half, area_y_half)
        position = np.array([x, y, 0.0])
        rotation = random_yaw_rotation()
        scale = np.array([
            random.uniform(0.2, 0.3),
            random.uniform(0.2, 0.3),
            random.uniform(0.2, 0.3),
        ])
        placements.append(TreePlacement(tree_type="Rock", position=position, rotation=rotation, scale=scale))

    return placements


def generate_vegetation_placements(density: int, area_x: float, area_y: float) -> List[TreePlacement]:
    total_bushes = int(density * (area_x * area_y) / 100.0)
    area_x_half = (area_x / 2.0) - 0.5
    area_y_half = (area_y / 2.0) - 0.5

    placements: List[TreePlacement] = []
    for _ in range(total_bushes):
        if random.randint(0, 1) == 1:
            center_x = random.uniform(-area_x_half, area_x_half)
            center_y = random.uniform(-area_y_half, area_y_half)

            for _ in range(10):
                ranges_x = [(-0.4, -0.2), (0.2, 0.4)]
                selected_range_x = random.choice(ranges_x)
                random_float_x = random.uniform(selected_range_x[0], selected_range_x[1])
                ranges_y = [(-0.4, -0.2), (0.2, 0.4)]
                selected_range_y = random.choice(ranges_y)
                random_float_y = random.uniform(selected_range_y[0], selected_range_y[1])

                sigma = 0.09
                temp_x = center_x + random.gauss(0, sigma) + random_float_x
                temp_y = center_y + random.gauss(0, sigma) + random_float_y

                plant_type = "Blueberry" if random.randint(0, 1) == 1 else "Bush"
                position = np.array([temp_x, temp_y, 0.0])
                rotation = random_yaw_rotation()
                scale = np.array([
                    random.uniform(0.8, 1.2),
                    random.uniform(0.8, 1.2),
                    random.uniform(0.8, 1.0),
                ])
                placements.append(TreePlacement(tree_type=plant_type, position=position, rotation=rotation, scale=scale))
        else:
            x = random.uniform(-area_x_half, area_x_half)
            y = random.uniform(-area_y_half, area_y_half)
            position = np.array([x, y, 0.0])
            rotation = random_yaw_rotation()
            scale = np.array([
                random.uniform(0.4, 1.0),
                random.uniform(0.4, 1.0),
                random.uniform(0.4, 1.0),
            ])
            placements.append(TreePlacement(tree_type="Bush", position=position, rotation=rotation, scale=scale))

    return placements
