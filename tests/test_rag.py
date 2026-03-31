from __future__ import annotations

from unittest.mock import patch
from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda


class TestRetriever:
    def test_retrieve_returns_documents(self):
        mock_rows = [
            {
                "nct_id": "NCT00000001",
                "chunk_text": "This is a test chunk.",
                "metadata": {'nct_id': 'NCT00000001', 'status': 'RECRUITING', 'phase': '3'},
                "similarity": 0.9,
            },
        ]
        with patch("src.rag.embeddings.embed_text", return_value=[0.1] * 1024), \
             patch("src.db.connection.execute_query", return_value=mock_rows):
            from src.rag.retriever import retrieve_relevant_chunks
            docs = retrieve_relevant_chunks("diabetes Phase 3 trials")
            assert len(docs) == 1
            assert isinstance(docs[0], Document)
            assert docs[0].metadata["nct_id"] == "NCT00000001"
            assert docs[0].metadata["status"] == "RECRUITING"
            assert docs[0].metadata["similarity"] == 0.9
    

    def test_retrieve_no_results(self):
        with patch("src.rag.embeddings.embed_text", return_value=[0.1] * 1024), \
             patch("src.db.connection.execute_query", return_value=[]):
            from src.rag.retriever import retrieve_relevant_chunks
            docs = retrieve_relevant_chunks("random query")
            assert docs == []

class TestRouter:
    def test_route_count_to_sql(self):
        from src.llm.router import route_query, QueryRoute
        assert route_query("count") == QueryRoute.SQL
        assert route_query("how many") == QueryRoute.SQL
    

    def test_route_explain_to_rag(self):
        from src.llm.router import route_query, QueryRoute
        assert route_query("describe") == QueryRoute.RAG
        assert route_query("what is ") == QueryRoute.RAG


    def test_route_oot_to_oot(self):
        from src.llm.router import route_query, QueryRoute
        assert route_query("weather") == QueryRoute.OOT
        assert route_query("bitcoin") == QueryRoute.OOT

class TestPromptRegistry:
    def test_get_prompt_return_table(self):
        from src.prompts.prompts_registry import get_prompt
        system, human = get_prompt("v4")
        assert isinstance(system, str) and len(system) > 10
        assert isinstance(human, str) and "{context}" in human

    def test_list_versions(self):
        from src.prompts.prompts_registry import list_versions
        versions = list_versions()
        assert len(versions) >= 4
        names = [v["version"] for v in versions]
        assert "v1" in names and "v2" in names and "v3" in names and "v4" in names
        
    def test_get_best_prompt(self):
        from src.prompts.prompts_registry import get_best_prompt
        assert get_best_prompt() == "v4"


class TestTextToSql:

    @patch("src.db.connection.execute_query")
    @patch("src.llm.text_to_sql.ChatBedrock")
    def test_generates_valid_sql(self, mock_bedrock, mock_execute_query):
        # Use RunnableLambda so LangChain's | chain works end-to-end
        sql_text = "SELECT COUNT(*) FROM gold.trials_enriched WHERE status = 'RECRUITING';"
        mock_bedrock.return_value = RunnableLambda(lambda _: AIMessage(content=sql_text))
        mock_execute_query.return_value = [{"count": 42}]

        from src.llm.text_to_sql import execute_text_to_sql
        result, sql = execute_text_to_sql("how many trials are recruiting?")

        assert "SELECT" in sql.upper()
        assert "RECRUITING" in sql.upper()
        assert "42" in result

    @patch("src.db.connection.execute_query")
    @patch("src.llm.text_to_sql.ChatBedrock")
    def test_returns_no_results_when_db_empty(self, mock_bedrock, mock_execute_query):
        sql_text = "SELECT * FROM gold.trials_enriched WHERE status = 'COMPLETED';"
        mock_bedrock.return_value = RunnableLambda(lambda _: AIMessage(content=sql_text))
        mock_execute_query.return_value = []
        
        from src.llm.text_to_sql import execute_text_to_sql
        result, sql = execute_text_to_sql("show completed trials")

        assert result == "No results found."
        assert "SELECT" in sql.upper()