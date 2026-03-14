import os
import sys

from rich.console import Console
from rich.table import Table
try:
    from src.api_client import AeroboticsClient, AeroboticsAPIError
    from src.processing import detect_missing_trees
except ImportError:
    from api_client import AeroboticsClient, AeroboticsAPIError
    from processing import detect_missing_trees

console = Console()

ORCHARD_ID = 216269


def select_latest_survey(surveys: list[dict]) -> dict:
    """Return the survey with the most recent date field."""
    return max(surveys, key=lambda s: s.get("date", ""))


def extract_tree_points(tree_records: list[dict]) -> list[tuple[float, float]]:
    """Extract (lng, lat) tuples from tree records, preserving order."""
    return [(r["lng"], r["lat"]) for r in tree_records]


def parse_boundary_polygon(raw) -> list[tuple[float, float]]:
    """Convert a polygon string into [(lng, lat), ...] tuples.
    
    The API returns the polygon as space-separated "lng,lat" pairs,
    e.g. "18.825,−32.327 18.827,−32.328 ...".
    """
    result = []
    for pair in str(raw).strip().split():
        lng_s, lat_s = pair.split(",")
        result.append((float(lng_s), float(lat_s)))
    return result


def fetch_orchard_data(client: AeroboticsClient, orchard_id: int) -> dict:
    """Execute the complete 3-step data-fetching workflow for an orchard.

    Steps:
        1. Fetch all surveys for the orchard
        2. Select the most recent survey by date
        3. Fetch tree summary for the selected survey
        4. Fetch all tree records for the selected survey
        5. Extract tree_points from tree records

    Returns a structured dict with orchard_id, selected survey, tree_summary,
    tree_records, and tree_points.
    """
    result: dict = {
        "orchard_id": orchard_id,
        "survey": {},
        "tree_summary": {},
        "tree_records": [],
        "tree_points": [],
        "missing_trees": [],
    }

    # Step 1: Fetch surveys
    console.log(f"[bold]Fetching surveys for orchard {orchard_id}...[/bold]")
    try:
        surveys = client.get_surveys(orchard_id)
    except AeroboticsAPIError as exc:
        console.log(f"[red]Failed at step 1 (fetch surveys): {exc}[/red]")
        raise AeroboticsAPIError(
            f"Workflow failed at step 1 (fetch surveys for orchard {orchard_id}): {exc}",
            status_code=exc.status_code,
            endpoint=exc.endpoint,
            response_body=exc.response_body,
        ) from exc

    console.log(f"Found [green]{len(surveys)}[/green] survey(s)")

    if not surveys:
        console.log("[yellow]No surveys found, returning empty result.[/yellow]")
        return result

    # Step 2: Select the most recent survey
    survey = select_latest_survey(surveys)
    survey_id = survey["id"]
    result["survey"] = survey
    console.log(f"Selected latest survey: ID [cyan]{survey_id}[/cyan], date [cyan]{survey.get('date')}[/cyan]")

    # Step 3: Fetch tree summary
    console.log(f"[bold]Fetching tree summary for survey {survey_id}...[/bold]")
    try:
        result["tree_summary"] = client.get_tree_summary(survey_id)
    except AeroboticsAPIError as exc:
        console.log(f"[red]Failed at step 2 (tree summary for survey {survey_id}): {exc}[/red]")
        raise AeroboticsAPIError(
            f"Workflow failed at step 2 (tree summary for survey {survey_id}): {exc}",
            status_code=exc.status_code,
            endpoint=exc.endpoint,
            response_body=exc.response_body,
        ) from exc

    summary = result["tree_summary"]
    console.log(
        f"  Tree count: [green]{summary.get('tree_count', 'N/A')}[/green], "
        f"Missing: [yellow]{summary.get('missing_tree_count', 'N/A')}[/yellow]"
    )

    # Step 4: Fetch tree records
    console.log(f"[bold]Fetching tree records for survey {survey_id}...[/bold]")
    try:
        result["tree_records"] = client.get_tree_records(survey_id)
    except AeroboticsAPIError as exc:
        console.log(f"[red]Failed at step 3 (tree records for survey {survey_id}): {exc}[/red]")
        raise AeroboticsAPIError(
            f"Workflow failed at step 3 (tree records for survey {survey_id}): {exc}",
            status_code=exc.status_code,
            endpoint=exc.endpoint,
            response_body=exc.response_body,
        ) from exc

    console.log(f"  Fetched [green]{len(result['tree_records'])}[/green] tree record(s)")

    # Step 5: Extract tree_points
    result["tree_points"] = extract_tree_points(result["tree_records"])
    console.log(f"  Extracted [green]{len(result['tree_points'])}[/green] tree point(s)")

    # Step 6: Detect missing trees
    console.log("[bold]Running missing tree detection...[/bold]")
    boundary_polygon = survey.get("polygon")
    if boundary_polygon:
        boundary_polygon = parse_boundary_polygon(boundary_polygon)
        console.log(f"  Using survey boundary polygon ({len(boundary_polygon)} vertices)")
    else:
        console.log("  [yellow]No polygon in survey, falling back to convex hull[/yellow]")
    result["boundary_polygon"] = boundary_polygon
    result["missing_trees"] = detect_missing_trees(result["tree_points"], boundary_polygon=boundary_polygon)
    console.log(f"  Detected [yellow]{len(result['missing_trees'])}[/yellow] missing tree(s)")

    console.log(f"[bold green]Workflow complete for orchard {orchard_id}[/bold green]")
    return result


def print_results(results: dict) -> None:
    """Print formatted summary of orchard data using Rich."""
    orchard_id = results.get("orchard_id")
    survey = results.get("survey", {})
    summary = results.get("tree_summary", {})
    tree_records = results.get("tree_records", [])
    tree_points = results.get("tree_points", [])
    missing_trees = results.get("missing_trees", [])

    console.rule(f"[bold]Orchard {orchard_id} — Results Summary[/bold]")

    if not survey:
        console.print("[yellow]No survey data to display.[/yellow]")
        return

    table = Table(title="Selected Survey (Most Recent)")
    table.add_column("Survey ID", style="cyan", justify="right")
    table.add_column("Date", style="white")
    table.add_column("Tree Count", style="green", justify="right")
    table.add_column("Missing Trees", style="yellow", justify="right")
    table.add_column("Tree Records", style="blue", justify="right")
    table.add_column("Tree Points", style="magenta", justify="right")
    table.add_column("Detected Gaps", style="red", justify="right")

    table.add_row(
        str(survey.get("id", "N/A")),
        str(survey.get("date", "N/A")),
        str(summary.get("tree_count", "N/A")),
        str(summary.get("missing_tree_count", "N/A")),
        str(len(tree_records)),
        str(len(tree_points)),
        str(len(missing_trees)),
    )

    console.print(table)
    console.print(f"\nTotal tree records fetched: [bold green]{len(tree_records)}[/bold green]")
    console.print(f"Total tree points extracted: [bold magenta]{len(tree_points)}[/bold magenta]")
    console.print(f"Missing trees detected: [bold red]{len(missing_trees)}[/bold red]")


def main() -> None:
    """Entry point: read token, create client, run workflow, print results."""
    api_token = os.environ.get("AEROBOTICS_API_TOKEN")
    if not api_token:
        console.print("[bold red]Error:[/bold red] AEROBOTICS_API_TOKEN environment variable is not set.")
        sys.exit(1)

    client = AeroboticsClient(api_token)

    try:
        results = fetch_orchard_data(client, ORCHARD_ID)
        print_results(results)
    except AeroboticsAPIError as exc:
        console.print(f"[bold red]API Error:[/bold red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()