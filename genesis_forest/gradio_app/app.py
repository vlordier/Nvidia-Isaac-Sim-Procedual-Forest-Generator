from __future__ import annotations

import gradio as gr
from dataclasses import dataclass


@dataclass
class UIState:
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


def normalize_proportions(birch: float, spruce: float, pine: float) -> tuple[float, float, float]:
    total = birch + spruce + pine
    if total == 0:
        return 33.33, 33.33, 33.34
    return birch / total * 100, spruce / total * 100, pine / total * 100


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Forest Generator") as app:
        gr.Markdown("# Procedural Forest Generator")
        gr.Markdown(
            "OpenUSD + Genesis Physics + UE5 Rendering\n\n"
            "Configure your forest parameters below, then generate."
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("## Tree Parameters")

                density = gr.Slider(
                    minimum=1, maximum=100, value=10, step=1,
                    label="Density (trees per 10x10m area)",
                    info="Number of trees per 100 square meters",
                )

                with gr.Row():
                    age_min = gr.Number(label="Min Age", value=50, precision=0)
                    age_max = gr.Number(label="Max Age", value=100, precision=0)

                gr.Markdown("**Tree Proportions (%)**")

                with gr.Row():
                    birch_p = gr.Number(label="Birch %", value=33.33, precision=2)
                    spruce_p = gr.Number(label="Spruce %", value=33.33, precision=2)
                    pine_p = gr.Number(label="Pine %", value=33.34, precision=2)

                normalise_btn = gr.Button("Normalize Proportions")

                def on_normalise(b, s, p):
                    nb, ns, np_ = normalize_proportions(b, s, p)
                    return gr.update(value=round(nb, 2)), gr.update(value=round(ns, 2)), gr.update(value=round(np_, 2))

                normalise_btn.click(
                    on_normalise,
                    inputs=[birch_p, spruce_p, pine_p],
                    outputs=[birch_p, spruce_p, pine_p],
                )

            with gr.Column(scale=1):
                gr.Markdown("## Forest Size")

                with gr.Row():
                    area_x = gr.Number(label="Length (m)", value=100, precision=0)
                    area_y = gr.Number(label="Width (m)", value=100, precision=0)

                gr.Markdown("## Terrain Parameters")

                roughness = gr.Slider(
                    minimum=0.0, maximum=10.0, value=1.0, step=0.1,
                    label="Elevation Difference (m)",
                    info="Roughness / elevation range of terrain",
                )

                rockiness = gr.Slider(
                    minimum=0, maximum=50, value=5, step=1,
                    label="Rock Density",
                    info="Rocks per 10x10m area",
                )

                gr.Markdown("## Vegetation")

                vegetation_enabled = gr.Checkbox(label="Generate Undergrowth", value=True)

                density_veg = gr.Slider(
                    minimum=1, maximum=50, value=5, step=1,
                    label="Vegetation Density",
                    info="Bushes/berry plants per 10x10m area",
                    visible=True,
                )

                def toggle_veg(enabled):
                    return gr.update(visible=enabled)

                vegetation_enabled.change(toggle_veg, inputs=[vegetation_enabled], outputs=[density_veg])

        gr.Markdown("## Output")

        with gr.Row():
            output_path = gr.Textbox(
                label="USD Output Path",
                value="./forest_output.usda",
                info="Where to save the generated forest USD file",
            )

        generate_btn = gr.Button("Generate Forest", variant="primary", size="lg")

        status = gr.Textbox(label="Status", lines=5, interactive=False)

        generate_btn.click(
            _generate_forest,
            inputs=[
                density, age_min, age_max,
                birch_p, spruce_p, pine_p,
                area_x, area_y,
                roughness, rockiness,
                vegetation_enabled, density_veg,
                output_path,
            ],
            outputs=[status],
        )

        gr.Markdown("---")
        gr.Markdown(
            "**Architecture**: Gradio UI → Python Backend → OpenUSD (scene definition) + "
            "Genesis (physics/raycasting) → USD file → UE5 (rendering)"
        )

    return app


def _generate_forest(
    density: int,
    age_min: int,
    age_max: int,
    birch_p: float,
    spruce_p: float,
    pine_p: float,
    area_x: int,
    area_y: int,
    roughness: float,
    rockiness: int,
    vegetation_enabled: bool,
    density_veg: int,
    output_path: str,
) -> str:
    from backend.forest_generator import ForestGenerator, ForestConfig

    nb, ns, np_ = normalize_proportions(birch_p, spruce_p, pine_p)

    config = ForestConfig(
        density=density,
        age_min=age_min,
        age_max=age_max,
        birch_p=nb,
        spruce_p=ns,
        pine_p=np_,
        area_x=area_x,
        area_y=area_y,
        roughness=roughness,
        rockiness=rockiness,
        vegetation_enabled=vegetation_enabled,
        vegetation_density=density_veg,
        usd_output_path=output_path,
    )

    try:
        generator = ForestGenerator(config)
        path = generator.generate_to_file(output_path)
        generator.shutdown()
        return f"Forest generated successfully!\nOutput: {path}\n\nTrees: {len(generator.state.tree_placements)}\nRocks: {len(generator.state.rock_placements)}\nVegetation: {len(generator.state.vegetation_placements)}"
    except Exception as e:
        return f"Error: {str(e)}"


demo = build_ui()
