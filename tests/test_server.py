"""
tests/test_server.py

Tests for the backend REST API server:
- Health check endpoint
- Example queries endpoint
- Successful query execution (Reference query, simple scan, single filter)
- Stage-by-stage data integrity (Lexer tokens, AST, Semantic checks, Logical IR, Plans, Costs, Selector, Execution, Feedback, Result)
- Error handling (Lexer error, Parser error, Semantic error)
- Adaptive reset endpoint
"""

from __future__ import annotations

import pytest

from backend.server import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestServerEndpoints:
    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["dataset"] == "students"
        assert data["dataset_rows"] == 200

    def test_get_examples(self, client):
        resp = client.get("/api/examples")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "examples" in data
        assert len(data["examples"]) >= 3
        # Reference query is first
        assert "department = 'CSE'" in data["examples"][0]["query"]

    def test_reference_query_execution_all_stages(self, client):
        query = (
            "SELECT name, marks "
            "FROM students "
            "WHERE department = 'CSE' "
            "AND marks > 80 "
            "ORDER BY marks DESC;"
        )
        resp = client.post("/api/query/execute", json={"query": query})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["error"] is None

        stages = data["stages"]

        # 1. Lexer
        assert stages["lexer"]["status"] == "PASSED"
        assert stages["lexer"]["token_count"] > 0
        first_token = stages["lexer"]["tokens"][0]
        assert first_token["type"] == "KEYWORD"
        assert first_token["value"] == "SELECT"

        # 2. Parser
        assert stages["parser"]["status"] == "PASSED"
        assert "QUERY" in stages["parser"]["ast_tree_text"]
        assert stages["parser"]["ast"]["type"] == "Query"

        # 3. Semantic
        assert stages["semantic"]["status"] == "PASSED"
        assert stages["semantic"]["valid"] is True
        assert stages["semantic"]["table"] == "students"
        assert len(stages["semantic"]["checks"]) >= 2

        # 4. Logical IR
        assert stages["logical_ir"]["status"] == "PASSED"
        assert len(stages["logical_ir"]["operations"]) == 4

        # 5. Planner
        assert stages["planner"]["status"] == "PASSED"
        assert stages["planner"]["candidate_count"] == 2
        # Plan A and Plan B
        plan_ids = [p["plan_id"] for p in stages["planner"]["plans"]]
        assert "plan_A" in plan_ids
        assert "plan_B" in plan_ids

        # 6. Cost
        assert stages["cost"]["status"] == "PASSED"
        assert stages["cost"]["plan_costs"]["plan_A"] < stages["cost"]["plan_costs"]["plan_B"]

        # 7. Selector
        assert stages["selector"]["status"] == "PASSED"
        assert stages["selector"]["selected_plan_id"] == "plan_A"

        # 8. Execution
        assert stages["execution"]["status"] == "PASSED"
        assert stages["execution"]["rows_returned"] == 13
        assert len(stages["execution"]["statistics"]) == 5

        # 9. Feedback
        assert stages["feedback"]["status"] == "PASSED"
        assert stages["feedback"]["total_absolute_error"] == 3

        # 10. Result
        assert stages["result"]["status"] == "PASSED"
        assert stages["result"]["columns"] == ["name", "marks"]
        assert len(stages["result"]["rows"]) == 13

    def test_semantic_error_reporting(self, client):
        query = "SELECT name, salary FROM students;"
        resp = client.post("/api/query/execute", json={"query": query})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is False
        assert data["error"]["stage"] == "semantic"
        assert "salary" in data["error"]["message"]
        assert data["stages"]["lexer"]["status"] == "PASSED"
        assert data["stages"]["parser"]["status"] == "PASSED"
        assert data["stages"]["semantic"]["status"] == "ERROR"
        assert data["stages"]["logical_ir"]["status"] == "NOT_RUN"

    def test_parser_syntax_error_reporting(self, client):
        query = "SELECT FROM students;"
        resp = client.post("/api/query/execute", json={"query": query})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is False
        assert data["error"]["stage"] == "parser"
        assert data["stages"]["lexer"]["status"] == "PASSED"
        assert data["stages"]["parser"]["status"] == "ERROR"
        assert data["stages"]["semantic"]["status"] == "NOT_RUN"

    def test_adaptive_reset_endpoint(self, client):
        resp = client.post("/api/adaptive/reset")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "reset"
        assert data["stored_profiles"] == 0
