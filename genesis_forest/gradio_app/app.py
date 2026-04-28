from __future__ import annotations

import threading
from typing import Optional

import gradio as gr


def normalize_proportions(birch: float, spruce: float, pine: float) -> tuple[float, float, float]:
    total = birch + spruce + pine
    if total == 0:
        return 33.33, 33.33, 33.34
    return birch / total * 100, spruce / total * 100, pine / total * 100


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Procedural Forest Generator") as app:
        gr.Markdown("# Procedural Forest Generator")
        gr.Markdown(
            "**Stack**: Gradio + Genesis Physics + OpenUSD + UE5 Rendering\n\n"
            "Configure forest parameters and generate. Large forests may take a moment."
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("## Tree Parameters")

                density = gr.Slider(
                    minimum=1, maximum=100, value=10, step=1,
                    label="Density (trees per 10×10m)",
                    info="Higher = more trees",
                )

                with gr.Row():
                    age_min = gr.Number(label="Min Age", value=50, precision=0)
                    age_max = gr.Number(label="Max Age", value=100, precision=0)

                gr.Markdown("**Tree Proportions (%)**")

                with gr.Row():
                    birch_p = gr.Number(label="Birch %", value=33.33, precision=2)
                    spruce_p = gr.Number(label="Spruce %", value=33.33, precision=2)
                    pine_p = gr.Number(label="Pine %", value=33.34, precision=2)

                normalise_btn = gr.Button("Normalize to 100%")

                def on_normalise(b, s, p):
                    nb, ns, np_ = normalize_proportions(b, s, p)
                    return (
                        gr.update(value=round(nb, 2)),
                        gr.update(value=round(ns, 2)),
                        gr.update(value=round(np_, 2)),
                    )

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

                gr.Markdown("## Terrain")

                roughness = gr.Slider(
                    minimum=0.0, maximum=10.0, value=1.0, step=0.1,
                    label="Elevation Range (m)",
                    info="Peak-to-valley height difference",
                )

                rockiness = gr.Slider(
                    minimum=0, maximum=50, value=5, step=1,
                    label="Rock Density",
                    info="Rocks per 100m²",
                )

                gr.Markdown("## Undergrowth")

                vegetation_enabled = gr.Checkbox(label="Generate Undergrowth", value=True)

                density_veg = gr.Slider(
                    minimum=1, maximum=50, value=5, step=1,
                    label="Vegetation Density",
                    info="Bushes/berry plants per 100m²",
                    visible=True,
                )

                def toggle_veg(enabled):
                    return gr.update(visible=enabled)

                vegetation_enabled.change(toggle_veg, inputs=[vegetation_enabled], outputs=[density_veg])

        gr.Markdown("## Output")

        with gr.Row():
            output_path = gr.Textbox(
                label="USD Output Path",
                value="./forest_output",
                info="Extension (.usda/.usdc) added automatically",
            )
            use_binary = gr.Checkbox(label="Binary USD (.usdc)", value=True)

        generate_btn = gr.Button("Generate Forest", variant="primary", size="lg")

        status = gr.Textbox(label="Status", lines=6, interactive=False)

        with gr.Row():
            gr.Markdown("* UE5 Import: File → Import into Level → select .usda/.usdc *")

        generate_btn.click(
            _generate_forest,
            inputs=[
                density, age_min, age_max,
                birch_p, spruce_p, pine_p,
                area_x, area_y,
                roughness, rockiness,
                vegetation_enabled, density_veg,
                output_path, use_binary,
                gr.Progress(),
            ],
            outputs=[status],
        )

        gr.Markdown("---")
        gr.Markdown(
            "**Architecture**: Gradio → Python/Genesis (heightfield sampling + Mesh placement) → OpenUSD → UE5\n\n"
            "Genesis backend: auto-detected (CPU / AMD GPU / NVIDIA CUDA)\n\n"
            "Note: Heights are sampled from Genesis terrain heightfield — no raycasting needed."
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
    use_binary: bool,
    progress: gr.Progress,
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
        use_binary_usd=use_binary,
    )

    def progress_cb(p: float, msg: str):
        progress(p, desc=msg)

    try:
        with ForestGenerator(config) as generator:
            result = generator.generate(progress_cb)
        return (
            f"Forest generated successfully!\n\n"
            f"Output: {result.usd_path}\n\n"
            f"Trees: {result.n_trees}\n"
            f"Rocks: {result.n_rocks}\n"
            f"Vegetation: {result.n_vegetation}\n\n"
            f"Terrain: {result.terrain_area[0]}m x {result.terrain_area[1]}m "
            f"(roughness={result.roughness})\n\n"
            f"Open in UE5: File → Import into Level → {result.usd_path}"
        )
    except Exception as e:
        import traceback
        return f"Error: {str(e)}\n\n{traceback.format_exc()}"


demo = build_ui()

if __name__ == "__main__":
    demo.launch()
