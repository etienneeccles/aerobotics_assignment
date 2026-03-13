# aerobotics_assignment
Interview assignment for Aerobotics  

## Quick start

```bash
# 1. Clone & enter folder
git clone https://github.com/etienneeccles/aerobotics_assignment.git
cd aerobotics_assignment

# 2. Install dependencies (recommended: use venv/pipx/uv)
pip install -r requirements.txt

# 3. Run demo
python src/main.py
```

step 1: get multiple survey IDs from orchard_Id https://api.aerobotics.com/farming/surveys/ (there is only 1 for orchardId 216269)

{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 25319,
      "orchard_id": 216269,
      "date": "2019-05-03",
      "hectares": 2.242,
      "polygon": "18.825688993836707,-32.32741477565738 18.82707301368839,-32.32771395090236 18.82696840753681,-32.32805392157161 18.826920127774542,-32.32810831676022 18.82668945779926,-32.328899309768175 18.82535103550083,-32.32913728625483 18.825165963078803,-32.32913048693532 18.825688993836707,-32.32741477565738"
    }
  ]
}

step 2: Get tree summary for tree count  https://api.aerobotics.com/farming/surveys/{id}/tree_survey_summaries/

{
  "survey_id": 25319,
  "tree_count": 508,
  "missing_tree_count": 4,
  "average_area_m2": 21.212,
  "stddev_area_m2": 3.873,
  "average_ndre": 0.554,
  "stddev_ndre": 0.036
}

step 3: Get indiviual trees (paginated) https://api.aerobotics.com/farming/surveys/{id}/tree_surveys/

{
  "count": 508,
  "next": "https://api.aerobotics.com/farming/surveys/25319/tree_surveys/?limit=2&offset=2",
  "previous": null,
  "results": [
    {
      "id": 54733434,
      "lat": -32.3279643,
      "lng": 18.826872,
      "ndre": 0.557,
      "ndvi": 0.872,
      "volume": 50.558,
      "area": 22.667,
      "row_index": null,
      "tree_index": null,
      "survey_id": 25319
    },
    {
      "id": 54733276,
      "lat": -32.3281893,
      "lng": 18.8263421,
      "ndre": 0.559,
      "ndvi": 0.881,
      "volume": 31.297,
      "area": 22.662,
      "row_index": null,
      "tree_index": null,
      "survey_id": 25319
    }
  ]
}

step4: work out the missing trees from this. We already have the missing count for validation