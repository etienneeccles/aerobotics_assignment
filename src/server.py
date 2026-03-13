"""FastAPI REST server exposing missing tree detection for orchards."""

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

try:
    from src.api_client import AeroboticsClient, AeroboticsAPIError
    from src.main import fetch_orchard_data
except ImportError:
    from api_client import AeroboticsClient, AeroboticsAPIError
    from main import fetch_orchard_data

app = FastAPI(title="Aerobotics Missing Tree API")


class Coordinate(BaseModel):
    lat: float
    lng: float


@app.get("/orchards/{orchard_id}/missing-trees", response_model=list[Coordinate])
def get_missing_trees(orchard_id: int) -> list[Coordinate]:
    """Return missing tree coordinates for the given orchard."""
    token = os.environ.get("AEROBOTICS_API_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="AEROBOTICS_API_TOKEN not configured")

    client = AeroboticsClient(token)

    try:
        result = fetch_orchard_data(client, orchard_id)
    except AeroboticsAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream API error: {exc}") from exc

    # No surveys found
    if not result.get("survey"):
        raise HTTPException(status_code=404, detail=f"No surveys found for orchard {orchard_id}")

    missing = result.get("missing_trees", [])
    return [Coordinate(lat=lat, lng=lng) for lat, lng in missing]
