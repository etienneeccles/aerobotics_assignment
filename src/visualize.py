"""Visualize the raster-based missing tree detection pipeline."""

import numpy as np
import matplotlib.pyplot as plt

try:
    from src.processing import (
        _to_local_meters, _from_local_meters,
        median_nn_separation, build_density_raster,
        smooth_raster, find_gaps, gap_pixels_to_coords,
        compute_boundary, compute_occupancy_mask,
        PipelineConfig, DEFAULT_CONFIG,
    )
except ImportError:
    from processing import (
        _to_local_meters, _from_local_meters,
        median_nn_separation, build_density_raster,
        smooth_raster, find_gaps, gap_pixels_to_coords,
        compute_boundary, compute_occupancy_mask,
        PipelineConfig, DEFAULT_CONFIG,
    )
from scipy.spatial import cKDTree as KDTree


def visualize_pipeline(
    tree_points: list[tuple[float, float]],
    config: PipelineConfig | None = None,
) -> None:
    """Run the raster pipeline step-by-step with plots at each stage."""
    if config is None:
        config = DEFAULT_CONFIG

    points = np.array(tree_points)
    meters, centroid, cos_lat = _to_local_meters(points)

    separation = median_nn_separation(meters)
    print(f"Median NN separation: {separation:.2f} m")

    raster, x_origin, y_origin, pixel_size = build_density_raster(
        meters, separation, pad_factor=config.pad_factor, density_factor=config.density_factor,
    )
    print(f"Raster shape: {raster.shape}, pixel size: {pixel_size:.2f} m")

    smoothed = smooth_raster(raster, pixel_size, separation, sigma_factor=config.sigma_factor)
    boundary = compute_boundary(meters, separation)
    occupancy = compute_occupancy_mask(boundary, x_origin, y_origin, pixel_size, raster.shape)
    gap_mask = find_gaps(smoothed, occupancy, threshold=config.threshold)
    gap_meters = gap_pixels_to_coords(gap_mask, x_origin, y_origin, pixel_size, occupancy)

    # Proximity filter
    if len(gap_meters) > 0:
        tree_kd = KDTree(meters)
        dists, _ = tree_kd.query(gap_meters)
        inside = dists < (separation * 1.5)
        gap_meters = gap_meters[inside]

    print(f"Gaps after proximity filter: {len(gap_meters)}")

    # Raster extent for imshow
    extent = [
        x_origin, x_origin + raster.shape[1] * pixel_size,
        y_origin, y_origin + raster.shape[0] * pixel_size,
    ]

    # Masked smoothed density (NaN outside hull for clean display)
    masked_smoothed = np.where(occupancy, smoothed, np.nan)

    # Hull outline coordinates
    hx, hy = boundary.exterior.xy

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))

    # 1) Hull boundary + occupancy mask
    ax = axes[0, 0]
    ax.set_title("Hull Boundary + Occupancy Mask")
    ax.imshow(occupancy.astype(float), origin="lower", extent=extent,
              cmap="Greens", aspect="equal", alpha=0.4, vmin=0, vmax=1)
    ax.plot(hx, hy, "g-", linewidth=1.5, label="Hull")
    ax.scatter(meters[:, 0], meters[:, 1], c="blue", s=4, alpha=0.6, label="Trees")
    ax.legend(fontsize=7)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")

    # 2) Smoothed density (masked by hull)
    ax = axes[0, 1]
    ax.set_title(f"Smoothed Density (σ={config.sigma_factor}×sep, inside hull)")
    im = ax.imshow(masked_smoothed, origin="lower", extent=extent,
                   cmap="hot", aspect="equal", vmin=0, vmax=1)
    ax.plot(hx, hy, "g-", linewidth=1, alpha=0.6)
    ax.scatter(meters[:, 0], meters[:, 1], c="cyan", s=4, alpha=0.4)
    plt.colorbar(im, ax=ax, label="Density (0–1)")

    # 3) Thresholded density + gaps
    ax = axes[1, 0]
    ax.set_title(f"Gaps (density < {config.threshold}, inside hull)")
    ax.imshow(gap_mask.astype(float), origin="lower", extent=extent,
              cmap="Reds", aspect="equal", vmin=0, vmax=1)
    ax.plot(hx, hy, "g-", linewidth=1, alpha=0.6)
    ax.scatter(meters[:, 0], meters[:, 1], c="blue", s=4, alpha=0.5, label="Trees")
    if len(gap_meters) > 0:
        ax.scatter(gap_meters[:, 0], gap_meters[:, 1], c="red", s=10,
                   marker="x", linewidths=1, label=f"Gaps ({len(gap_meters)})")
    ax.legend(fontsize=7)

    # 4) Original space with gaps
    ax = axes[1, 1]
    ax.set_title("Original Space (lng/lat)")
    ax.scatter(points[:, 0], points[:, 1], c="blue", s=8, alpha=0.7, label="Trees")
    if len(gap_meters) > 0:
        gaps_latlng = _from_local_meters(gap_meters, centroid, cos_lat)
        ax.scatter(gaps_latlng[:, 0], gaps_latlng[:, 1], c="red", s=20,
                   marker="x", linewidths=1.2, label=f"Gaps ({len(gaps_latlng)})")
    ax.legend(fontsize=7)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")

    plt.tight_layout()
    plt.savefig("tree_detection.png", dpi=150)
    print("Saved tree_detection.png")
    plt.show()


if __name__ == "__main__":
    import os, sys
    try:
        from src.api_client import AeroboticsClient, AeroboticsAPIError
        from src.main import fetch_orchard_data, ORCHARD_ID
    except ImportError:
        from api_client import AeroboticsClient, AeroboticsAPIError
        from main import fetch_orchard_data, ORCHARD_ID

    token = os.environ.get("AEROBOTICS_API_TOKEN")
    if not token:
        print("Set AEROBOTICS_API_TOKEN first")
        sys.exit(1)

    client = AeroboticsClient(token)
    results = fetch_orchard_data(client, ORCHARD_ID)
    tree_points = results["tree_points"]
    print(f"Got {len(tree_points)} tree points, running visualization...")
    visualize_pipeline(tree_points)
