import requests, time, logging
from datetime import datetime
from typing import Iterator

logger = logging.getLogger(__name__)
BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

def fetch_trials_incremental(
    condition: str,
    since_date: datetime,
    batch_size: int = 100,
) -> Iterator[list[dict]]:
    """
    Fetch trials incrementally using the ClinicalTrials.gov API.
    """
    params = { "format": "json", "query.cond": f"{condition}", "pageSize": batch_size,}

    if since_date:
        params["query.term"] = (
            f"AREA[LastUpdatePostDate]RANGE[{since_date.strftime('%Y-%m-%d')},MAX]"
        )
    page_token = ""
    while True:
        if page_token:
            params["pageToken"] = page_token
        
        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            print(data)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching trials: {e}")
            time.sleep(10)
            continue
        studies = data.get("studies", [])
        print(studies)
        if not studies:
            break
        yield studies
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.5)