from __future__ import annotations

import gradio as gr


def normalize_proportions(birch: float, spruce: float, pine: float) -> tuple[float, float, float]:
    total = birch + spruce + pine
    if total == 0:
        return 33.33, 33.33, 33.34
    return birch / total * 100, spruce / total * 100, pine / total * 100


def _check_ue5_status(host: str, port: int) -> str:
    try:
        from ue5.client import check_ue5_status
        status = check_ue5_status(host=host, port=port)
        if status.get("ue5"):
            subsystems = status.get("subsystems", {})
            editor_scripts = subsystems.get("EditorScriptingUtilities", False)
            perf = subsystems.get("EditorPerformance", False)
            actors = status.get("actors_in_level", "unknown")
            return (
                f"**UE5 Connected**\n"
                f"- EditorScriptingUtilitiesSubsystem: {'OK' if editor_scripts else 'NOT AVAILABLE'}\n"
                f"- EditorPerformanceSubsystem: {'OK' if perf else 'NOT AVAILABLE'}\n"
                f"- Actors in level: {actors}\n\n"
                f"Ready to render. Set camera position and click **Render in UE5**."
            )
        else:
            return (
                f"**UE5 Not Reachable**\n\n"
                f"Make sure UE5 is running with the server script loaded:\n"
                f"1. Open UE5 with your project\n"
                f"2. Enable: Edit → Plugins → Python Editor Script Plugin\n"
                f"3. View → Developer Tools → Python Console\n"
                f"4. Run: `exec(open('genesis_forest/ue5/ue5_server.py').read())`\n\n"
                f"Error: {status.get('message', 'Connection failed')}"
            )
    except ImportError:
        return "**UE5 client not available** — make sure genesis_forest is installed."


def _render_in_ue5(
    usd_path: str,
    camera_x: float,
    camera_y: float,
    camera_z: float,
    look_at_x: float,
    look_at_y: float,
    look_at_z: float,
    resolution_w: int,
    resolution_h: int,
    sun_azimuth: float,
    sun_elevation: float,
    ue5_host: str,
    ue5_port: int,
) -> str:
    if not usd_path:
        return "Error: USD path is required. Generate a forest first or enter a path manually."

    from pathlib import Path
    p = Path(usd_path)
    if not p.exists():
        return f"Error: File not found: {usd_path}"

    try:
        from ue5.client import UE5RenderClient
        client = UE5RenderClient(host=ue5_host, port=ue5_port)

        health = client.health_check()
        if not health.get("ue5"):
            return (
                f"Error: Cannot reach UE5 at {ue5_host}:{ue5_port}.\n\n"
                f"Start the server in UE5 first (see instructions above)."
            )
    except Exception as e:
        return f"Error connecting to UE5 server: {e}\n\nMake sure UE5 is running with the server loaded."

    camera_location = (float(camera_x), float(camera_y), float(camera_z))
    camera_look_at = (float(look_at_x), float(look_at_y), float(look_at_z))
    resolution = (int(resolution_w), int(resolution_h))

    result = client.render_simple(
        usd_path=usd_path,
        camera_location=camera_location,
        camera_look_at=camera_look_at,
        resolution=resolution,
        sun_azimuth=sun_azimuth,
        sun_elevation=sun_elevation,
    )

    if result.get("success"):
        elapsed = result.get("elapsed_seconds", "unknown")
        output = result.get("output_path", "unknown")
        return (
            f"**Render Complete!** ({elapsed}s)\n\n"
            f"Output: `{output}`\n\n"
            f"Camera: {camera_location} → {camera_look_at}\n"
            f"Resolution: {resolution[0]}×{resolution[1]}\n\n"
            f"Open `{output}` in your image viewer to see the result."
        )
    else:
        error = result.get("error", "Unknown error")
        return f"**Render Failed**\n\nError: {error}"


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Procedural Forest Generator") as app:
        gr.Markdown("# Procedural Forest Generator")
        gr.Markdown(
            "**Stack**: Gradio + Genesis Physics + OpenUSD + UE5 Rendering\n\n"
            "Two steps: (1) Generate a forest → (2) Render it in UE5."
        )

        with gr.Tabs():
            with gr.TabItem("Generate Forest"):
                _build_generation_tab()
            with gr.TabItem("Render in UE5"):
                _build_ue5_tab()

        gr.Markdown("---")
        gr.Markdown(
            "**Architecture**: Gradio → Python/Genesis (heightfield + fixed static entities + physics settle) → OpenUSD → UE5\n\n"
            "Genesis backend: auto-detected (CPU / AMD GPU / NVIDIA CUDA)\n\n"
            "Note: Trees are `fixed=True` (no DOFs) and `collision=False` (static). "
            "Physics settling via scene.step() makes Genesis authoritative."
        )

    return app


def _build_generation_tab() -> None:
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
            value="./forest_output.usdc",
            info="Extension (.usda/.usdc) added automatically",
        )
        use_binary = gr.Checkbox(label="Binary USD (.usdc)", value=True)

    generate_btn = gr.Button("Generate Forest", variant="primary", size="lg")

    status = gr.Textbox(label="Status", lines=6, interactive=False)

    usd_result_path = gr.Textbox(label="Generated USD Path", interactive=False)

    generate_btn.click(
        _generate_forest,
        inputs=[
            density, age_min, age_max,
            birch_p, spruce_p, pine_p,
            area_x, area_y,
            roughness, rockiness,
            vegetation_enabled, density_veg,
            output_path, use_binary,
        ],
        outputs=[status, usd_result_path],
    )


def _build_ue5_tab() -> None:
    gr.Markdown("## UE5 Server Connection")

    with gr.Row():
        ue5_host = gr.Textbox(label="UE5 Host", value="localhost", scale=1)
        ue5_port = gr.Number(label="Port", value=8787, precision=0, scale=1)
        check_btn = gr.Button("Check UE5 Status", size="sm", scale=2)

    ue5_status = gr.Markdown("", elem_id="ue5_status")

    check_btn.click(
        _check_ue5_status,
        inputs=[ue5_host, ue5_port],
        outputs=[ue5_status],
    )

    gr.Markdown("---")
    gr.Markdown("## USD File")

    usd_path_input = gr.Textbox(
        label="USD File Path",
        placeholder="./forest_output.usdc",
        info="Path to the .usdc or .usda file from the Generate Forest tab",
    )

    gr.Markdown("## Camera")

    with gr.Row():
        camera_x = gr.Number(label="X (cm)", value=5000, precision=0)
        camera_y = gr.Number(label="Y (cm)", value=-5000, precision=0)
        camera_z = gr.Number(label="Z (cm)", value=2000, precision=0)

    gr.Markdown("**Look-at Point**")

    with gr.Row():
        look_at_x = gr.Number(label="X (cm)", value=0, precision=0)
        look_at_y = gr.Number(label="Y (cm)", value=0, precision=0)
        look_at_z = gr.Number(label="Z (cm)", value=500, precision=0)

    gr.Markdown("## Lighting")

    with gr.Row():
        sun_azimuth = gr.Slider(
            minimum=0, maximum=360, value=45, step=1,
            label="Sun Azimuth (°)",
            info="Horizontal angle of sun",
        )
        sun_elevation = gr.Slider(
            minimum=0, maximum=90, value=30, step=1,
            label="Sun Elevation (°)",
            info="Vertical angle of sun",
        )

    gr.Markdown("## Output Settings")

    with gr.Row():
        resolution_w = gr.Number(label="Width (px)", value=3840, precision=0)
        resolution_h = gr.Number(label="Height (px)", value=2160, precision=0)

    render_btn = gr.Button("Render in UE5", variant="primary", size="lg")
    render_status = gr.Textbox(label="Render Status", lines=5, interactive=False)

    gr.Markdown(
        "**Setup**: UE5 must be running with the server script loaded:\n"
        "1. Enable: Edit → Plugins → Python Editor Script Plugin\n"
        "2. View → Developer Tools → Python Console\n"
        "3. Run: `exec(open('genesis_forest/ue5/ue5_server.py').read())`\n"
        "4. Then click **Check UE5 Status** above"
    )

    render_btn.click(
        _render_in_ue5,
        inputs=[
            usd_path_input,
            camera_x, camera_y, camera_z,
            look_at_x, look_at_y, look_at_z,
            resolution_w, resolution_h,
            sun_azimuth, sun_elevation,
            ue5_host, ue5_port,
        ],
        outputs=[render_status],
    )


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
) -> tuple[str, str]:
    from pathlib import Path
    from backend.forest_generator import ForestGenerator, ForestConfig

    models_path = Path(__file__).parent.parent / "models"
    ext = ".usdc" if use_binary else ".usda"
    if not output_path.endswith(ext):
        output_path = output_path.rsplit(".", 1)[0] + ext

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
        asset_base_path=str(models_path),
        usd_output_path=output_path,
        use_binary_usd=use_binary,
    )

    try:
        with ForestGenerator(config) as generator:
            result = generator.generate()
        status_msg = (
            f"Forest generated successfully!\n\n"
            f"Trees: {result.n_trees}\n"
            f"Rocks: {result.n_rocks}\n"
            f"Vegetation: {result.n_vegetation}\n\n"
            f"Terrain: {result.terrain_area[0]}m x {result.terrain_area[1]}m "
            f"(roughness={result.roughness})\n"
            f"Genesis: v{result.genesis_version[0]}.{result.genesis_version[1]}\n\n"
            f"Go to the **Render in UE5** tab to render this forest."
        )
        return status_msg, result.usd_path
    except FileNotFoundError as e:
        return f"Asset not found: {e}\n\nEnsure tree assets exist at the configured path.", ""
    except Exception as e:
        import traceback
        return f"Error: {str(e)}\n\n{traceback.format_exc()}", ""


demo = build_ui()


def main():
    demo.launch()


if __name__ == "__main__":
    main()
