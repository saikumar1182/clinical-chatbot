from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


class TestFetchClinicalTrials:
    """Helper method to create a mock study. This is used to create mock data for testing
    It returns a dictionary that mimics the structure of a study from the ClinicalTrials.gov API"""

    def _make_study(self, nct_id: str) -> dict:
        return {
            "protocolSection":{
                "identificationModule":{
                    "nctId": nct_id,
                    "briefTitle": f"Trial study {nct_id}",
                    "statusModule":{"overallStatus": "RECRUITING"}
                }
            }
        }

    @patch("requests.get")
    def test_fetch_trials_incremental_success(self, mock_get):
        # Test successful fetching of trials
        # This test checks if the fetch_trials_incremental function can successfully fetch trials
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "studies": [self._make_study("NCT00000001"),
                            self._make_study("NCT00000002")]
            },
            raise_for_status=lambda: None
        )
        from src.ingestion.fetch_trials import fetch_trials_incremental
        
        batches = list(fetch_trials_incremental("diabetes", since_date=None, max_results=10))
        assert len(batches) == 1
        assert len(batches[0]) == 2
        

    @patch("requests.get")
    def test_fetch_trails_handles_empty_response(self, mock_get):
        # Test that the function handles empty responses correctly
        # This test checks if the fetch_trials_incremental function can successfully fetch trials
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"studies": []},
            raise_for_status=lambda: None
        )
        from src.ingestion.fetch_trials import fetch_trials_incremental

        batches = list(fetch_trials_incremental("diabetes"))
        assert batches == []
    
    @patch("requests.get")
    def test_fetch_respects_max_results(self, mock_get):
        # Test that the function respects the max_results parameter
        # This test checks if the fetch_trials_incremental function can successfully fetch trials
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "studies": [self._make_study(f"NCT{i:08d}") for i in range(5)]
            },
            raise_for_status=lambda: None
        )
        from src.ingestion.fetch_trials import fetch_trials_incremental

        batches = list(fetch_trials_incremental("diabetes", max_results=5))
        total = sum(len(b) for b in batches)
        assert total <= 5


class TestLoadToPostgres:
    # Test successful loading of trials to Postgres
    # This test checks if the load_to_postgres function can successfully load trials to Postgres
    def _make_trials(self, nct_id: str) -> dict:
        return {
            "protocolSection":{
                "identificationModule":{
                    "nctId": nct_id,
                    "briefTitle": "Test trial study"},
                    "statusModule":{"overallStatus": "RECRUITING"}
            }
        }
    
    def test_load_skips_missing_nct_id(self):
        # Test that the function skips trials with missing NCT IDs
        # This test checks if the load_to_postgres function can successfully load trials to Postgres
        from src.ingestion.load_to_postgres import load_trials_batch
        with patch("src.db.connection.get_db_session") as mock_get_db_connection:
            mock_engine = MagicMock()
            mock_conn = MagicMock()

            mock_get_db_connection.return_value = mock_engine
            mock_engine.begin.return_value.__enter__.return_value = mock_conn
            mock_engine.begin.return_value.__exit__.return_value = False

            result = load_trials_batch([{"no_protocol_section": True}], "test_batch")
            assert result == 0
    
    def test_load_empty_list(self):
        # Test that the function handles empty lists correctly
        # This test checks if the load_to_postgres function can successfully load trials to Postgres
        from src.ingestion.load_to_postgres import load_trials_batch
        result = load_trials_batch([], "test_batch")
        assert result == 0
            
        
