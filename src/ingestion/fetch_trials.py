"""
fetch_trials.py — ClinicalTrials.gov API client.

Called by Airflow DAG 1 task function fetch_and_load().
Each call fetches one condition incrementally.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Iterator

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
MAX_PER_CONDITION = 500         # Hard cap per condition per run
DEFAULT_BATCH_SIZE = 100        # API page size
API_RATE_LIMIT_SLEEP = 0.5      # Seconds between pages (respectful)
API_RETRY_SLEEP = 10            # Seconds before retrying on error


def fetch_trials_incremental(
    condition: str,
    since_date: datetime | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_results: int = MAX_PER_CONDITION,
) -> Iterator[list[dict]]:
    """
    Generator that yields batches of raw trial dicts from ClinicalTrials.gov.

    Args:
        condition:   Medical condition to search (e.g. "diabetes")
        since_date:  Only fetch trials updated after this date (incremental mode).
                     When None, fetches all trials (full load).
        batch_size:  API page size (max 100)
        max_results: Safety cap — stop after this many total results

    Yields:
        List of raw trial dicts (each is protocolSection JSON from the API)

    Notes:
        - Airflow DAG 1 passes data_interval_start as since_date automatically
        - Handles pagination, rate limits, and transient API errors
        - The caller (Airflow task) provides retry logic via task retries
    """
    params: dict = {
        "query.cond": condition,
        "pageSize": min(batch_size, 100),   # API max is 100
        "format": "json",
        "fields": "protocolSection,hasResults",
    }

    if since_date:
        # Incremental: only trials updated after since_date
        date_str = since_date.strftime("%Y-%m-%d")
        params["filter.advanced"] = (
            f"AREA[LastUpdatePostDate]RANGE[{date_str},MAX]"
        )
        logger.info(f"Incremental fetch: condition='{condition}', since={date_str}")
    else:
        logger.info(f"Full fetch: condition='{condition}'")

    page_token: str | None = None
    total_yielded = 0

    while total_yielded < max_results:
        if page_token:
            params["pageToken"] = page_token
        elif "pageToken" in params:
            del params["pageToken"]

        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout fetching '{condition}'. Retrying in {API_RETRY_SLEEP}s...")
            time.sleep(API_RETRY_SLEEP)
            continue
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code} for '{condition}': {e}")
            if e.response.status_code == 429:
                # Rate limited — wait longer
                time.sleep(30)
                continue
            raise
        except requests.RequestException as e:
            logger.error(f"Request error for '{condition}': {e}")
            time.sleep(API_RETRY_SLEEP)
            continue

        studies = data.get("studies", [])
        if not studies:
            logger.info(f"No more results for '{condition}'. Total: {total_yielded}")
            break

        total_yielded += len(studies)
        logger.debug(f"Fetched {len(studies)} trials for '{condition}' (total: {total_yielded})")
        yield studies

        page_token = data.get("nextPageToken")
        if not page_token:
            logger.info(f"All pages fetched for '{condition}'. Total: {total_yielded}")
            break

        time.sleep(API_RATE_LIMIT_SLEEP)

    if total_yielded >= max_results:
        logger.info(f"Reached max_results={max_results} for '{condition}', stopping.")
