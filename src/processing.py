"""Missing Tree Detector — raster-based gap detection.

Uses nearest-neighbour median separation, Gaussian-smoothed density raster,
and thresholding to find gaps.  Coordinate conversion helpers preserved.
"""

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree as KDTree
from scipy.ndimage import gaussian_filter, label as ndimage_label
import alphashape
from shapely.geometry import MultiPoint, Point


# ---------------------------------------------------------------------------
# Coordinate conversion (kept from previous version)
# ---------------------------------------------------------------------------

def _to_local_meters(points: NDArray) -> tuple[NDArray, NDArray, float]:
    """Convert (lng, lat) points to local meter offsets from centroid.

    Returns (meters_array, centroid, cos_lat_scale).
    """
    centroid = points.mean(axis=0)
    centered = points - centroid
    cos_lat = np.abs(np.cos(np.radians(centroid[1])))
    meters = np.column_stack([
        centered[:, 0] * 111_111 * cos_lat,  # lng to meters
        centered[:, 1] * 111_111,              # lat to meters
    ])
    return meters, centroid, cos_lat
from dataclasses import dataclass


@dataclass
class PipelineConfig:
    """Shared configuration for the raster-based missing tree detection pipeline."""
    sigma_factor: float = 0.45
    threshold: float = 0.35
    density_factor: int = 8
    pad_factor: float = 1.0


DEFAULT_CONFIG = PipelineConfig()





def _from_local_meters(meters: NDArray, centroid: NDArray, cos_lat: float) -> NDArray:
    """Convert local meter offsets back to (lng, lat)."""
    return np.column_stack([
        meters[:, 0] / (111_111 * cos_lat) + centroid[0],
        meters[:, 1] / 111_111 + centroid[1],
    ])


# ---------------------------------------------------------------------------
# Step 1: Median nearest-neighbour separation
# ---------------------------------------------------------------------------

def median_nn_separation(meters: NDArray) -> float:
    """Return the median nearest-neighbour distance for an Nx2 point set."""
    tree = KDTree(meters)
    dists, _ = tree.query(meters, k=2)  # k=2: self + nearest
    nn_dists = dists[:, 1]
    return float(np.median(nn_dists))


# ---------------------------------------------------------------------------
# Step 2: Build density raster
# ---------------------------------------------------------------------------

def build_density_raster(
    meters: NDArray,
    separation: float,
    pad_factor: float = 1.0,
    density_factor: int = 4,
) -> tuple[NDArray, float, float, float]:
    """Bin tree positions into a 2-D density raster.

    Parameters
    ----------
    meters : NDArray
        Nx2 array of (x, y) positions in metres.
    separation : float
        Median nearest-neighbour separation.
    pad_factor : float
        Extra padding around the bounding box, as a multiple of *separation*.
    density_factor : int
        Pixel density relative to separation (4 → pixel size = separation/4).

    Returns
    -------
    tuple[NDArray, float, float, float]
        (raster, x_origin, y_origin, pixel_size)
        *raster* is a 2-D float array of tree counts per pixel.
        *x_origin* / *y_origin* are the lower-left corner coordinates.
        *pixel_size* is the side length of each pixel in metres.
    """
    pixel_size = separation / density_factor
    pad = separation * pad_factor

    x_min, y_min = meters.min(axis=0) - pad
    x_max, y_max = meters.max(axis=0) + pad

    nx = int(np.ceil((x_max - x_min) / pixel_size))
    ny = int(np.ceil((y_max - y_min) / pixel_size))

    raster = np.zeros((ny, nx), dtype=np.float64)

    # Bin each tree into the nearest pixel
    col_idx = np.clip(((meters[:, 0] - x_min) / pixel_size).astype(int), 0, nx - 1)
    row_idx = np.clip(((meters[:, 1] - y_min) / pixel_size).astype(int), 0, ny - 1)
    np.add.at(raster, (row_idx, col_idx), 1)

    return raster, x_min, y_min, pixel_size


# ---------------------------------------------------------------------------
# Step 3: Gaussian smoothing
# ---------------------------------------------------------------------------

def smooth_raster(
    raster: NDArray,
    pixel_size: float,
    separation: float,
    sigma_factor: float = 0.45,
) -> NDArray:
    """Apply Gaussian smoothing to the density raster.

    Parameters
    ----------
    raster : NDArray
        2-D density raster (counts per pixel).
    pixel_size : float
        Pixel side length in metres.
    separation : float
        Median nearest-neighbour separation.
    sigma_factor : float
        Gaussian sigma as a multiple of *separation*.

    Returns
    -------
    NDArray
        Smoothed raster (same shape).
    """
    sigma_pixels = (separation * sigma_factor) / pixel_size
    smoothed = gaussian_filter(raster, sigma=sigma_pixels)
    peak = smoothed.max()
    if peak > 0:
        smoothed = smoothed / peak
    return smoothed


# ---------------------------------------------------------------------------
# Step 4: Threshold to find gaps
# ---------------------------------------------------------------------------

def compute_boundary(meters: NDArray, separation: float):
    """Compute a tight concave hull around the tree points.

    Uses alphashape with optimized alpha. Falls back to convex hull
    if the alpha shape is empty or a MultiPolygon. Applies a small
    buffer of 0.5 × separation so edge trees aren't excluded.

    Returns a shapely geometry.
    """
    try:
        alpha = alphashape.optimizealpha(meters)
        boundary = alphashape.alphashape(meters, alpha)
    except Exception:
        boundary = MultiPoint(meters).convex_hull

    if boundary.is_empty or boundary.geom_type == "MultiPolygon":
        boundary = MultiPoint(meters).convex_hull

    return boundary.buffer(separation * 1.5)


def compute_occupancy_mask(
    boundary,
    x_origin: float,
    y_origin: float,
    pixel_size: float,
    shape: tuple[int, int],
) -> NDArray:
    """Rasterize the hull boundary into a boolean pixel mask.

    Parameters
    ----------
    boundary : shapely geometry
        Buffered hull polygon around the tree points.
    x_origin, y_origin : float
        Lower-left corner of the raster.
    pixel_size : float
        Pixel side length in metres.
    shape : tuple[int, int]
        (ny, nx) shape of the raster.

    Returns
    -------
    NDArray
        Boolean mask, True for pixels whose centre is inside the boundary.
    """
    ny, nx = shape
    cols = np.arange(nx)
    rows = np.arange(ny)
    cx = x_origin + (cols + 0.5) * pixel_size
    cy = y_origin + (rows + 0.5) * pixel_size
    gx, gy = np.meshgrid(cx, cy)
    flat_x = gx.ravel()
    flat_y = gy.ravel()

    # Vectorised containment check via prepared geometry
    from shapely.prepared import prep
    prepared = prep(boundary)
    mask = np.array([prepared.contains(Point(x, y))
                     for x, y in zip(flat_x, flat_y)])
    return mask.reshape(shape)


def find_gaps(
    smoothed: NDArray,
    occupancy: NDArray,
    threshold: float = 0.35,
) -> NDArray:
    """Threshold the smoothed raster to identify gap pixels.

    A pixel is a gap if it is inside the occupancy mask AND its
    smoothed density is below *threshold*.

    Parameters
    ----------
    smoothed : NDArray
        Gaussian-smoothed density raster (0–1 normalised).
    occupancy : NDArray
        Boolean mask, True for pixels inside the orchard.
    threshold : float
        Pixels below this density are considered gaps.

    Returns
    -------
    NDArray
        Boolean mask (same shape as *smoothed*), True where gaps are.
    """
    if smoothed.max() == 0:
        return np.zeros_like(smoothed, dtype=bool)
    return occupancy & (smoothed < threshold)


def gap_pixels_to_coords(
    gap_mask: NDArray,
    x_origin: float,
    y_origin: float,
    pixel_size: float,
    occupancy: NDArray,
) -> NDArray:
    """Run connected-component analysis on the gap mask and return
    the centroid of each component in (x, y) metre coordinates.

    Components that touch the edge of the occupancy mask are discarded
    (they are boundary artifacts, not real interior gaps).
    """
    labeled, num_features = ndimage_label(gap_mask)
    if num_features == 0:
        return np.empty((0, 2))

    # Build a 1-pixel-wide border mask of the occupancy region
    # A pixel is on the occupancy edge if it's occupied and has at
    # least one non-occupied neighbour (4-connected).
    from scipy.ndimage import binary_erosion
    eroded = binary_erosion(occupancy, structure=np.ones((3, 3)))
    edge_mask = occupancy & ~eroded

    centroids = []
    for i in range(1, num_features + 1):
        component = labeled == i
        # Skip if any pixel in this component touches the occupancy edge
        if np.any(component & edge_mask):
            continue
        rows, cols = np.where(component)
        cy = y_origin + (rows.mean() + 0.5) * pixel_size
        cx = x_origin + (cols.mean() + 0.5) * pixel_size
        centroids.append([cx, cy])

    if not centroids:
        return np.empty((0, 2))
    return np.array(centroids)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def detect_missing_trees(
    tree_points: list[tuple[float, float]],
    config: PipelineConfig | None = None,
) -> list[tuple[float, float]]:
    """Run the raster-based missing-tree detection pipeline.

    1. Convert to local metres
    2. Compute median nearest-neighbour separation
    3. Build density raster (pixel_size = separation / density_factor)
    4. Gaussian smooth (sigma = sigma_factor * separation)
    5. Threshold to find gap pixels
    6. Filter gap pixels to those near actual trees (inside orchard)
    7. Convert back to (lng, lat)

    Returns gap locations as (lng, lat) tuples.
    Returns empty list if fewer than 3 points.
    """
    if config is None:
        config = DEFAULT_CONFIG

    if len(tree_points) < 3:
        return []

    points = np.array(tree_points)
    meters, centroid, cos_lat = _to_local_meters(points)

    # Step 1
    separation = median_nn_separation(meters)

    # Step 2
    raster, x_origin, y_origin, pixel_size = build_density_raster(
        meters, separation, pad_factor=config.pad_factor, density_factor=config.density_factor,
    )

    # Step 3
    smoothed = smooth_raster(raster, pixel_size, separation, sigma_factor=config.sigma_factor)

    # Step 4: hull-based occupancy mask + threshold
    boundary = compute_boundary(meters, separation)
    occupancy = compute_occupancy_mask(boundary, x_origin, y_origin, pixel_size, raster.shape)
    gap_mask = find_gaps(smoothed, occupancy, threshold=config.threshold)

    # Step 5: connected-component centroids in metres
    gap_meters = gap_pixels_to_coords(gap_mask, x_origin, y_origin, pixel_size, occupancy)

    if len(gap_meters) == 0:
        print("Found 0 gaps")
        return []

    # Step 6: filter to gaps that are actually inside the orchard
    # (within 1.5 * separation of any real tree)
    tree_kd = KDTree(meters)
    dists, _ = tree_kd.query(gap_meters)
    inside = dists < (separation * 1.5)
    gap_meters = gap_meters[inside]

    if len(gap_meters) == 0:
        print("Found 0 gaps (after proximity filter)")
        return []

    # Step 7: back to lng/lat
    gaps_latlng = _from_local_meters(gap_meters, centroid, cos_lat)
    print(f"Found {len(gaps_latlng)} gaps")

    return [(float(row[0]), float(row[1])) for row in gaps_latlng]

