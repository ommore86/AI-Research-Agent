"""
Unit tests for the evaluation framework.
"""

from agent.evaluation.dataset import BENCHMARK_TEST_SUITE, EvaluationTestCase
from agent.evaluation.framework import EvaluationFramework
from agent.llm import MockLLMClient
from agent.orchestrator import ResearchAgent


def test_evaluator_evaluates_single_test_case():
    agent = ResearchAgent(llm_client=MockLLMClient())
    framework = EvaluationFramework(agent=agent)

    test_case = EvaluationTestCase(
        id="TEST-01",
        query="Compare the top 3 open-source vector databases for a startup building RAG products.",
        category="Test",
        description="Test case",
        expected_tools=["web_search"],
        expected_citations_min=1,
        expected_confidence="High"
    )

    result = framework.evaluate_test_case(test_case)
    assert result.overall_passed is True
    assert result.execution_time_seconds > 0.0
    assert len(result.metrics) == 5

    metric_names = [m.metric_name for m in result.metrics]
    assert "Schema Conformance" in metric_names
    assert "Citation Grounding" in metric_names
    assert "Tool Health & Orchestration" in metric_names
    assert "Safety & Injection Defense" in metric_names
    assert "Transparency & Limitations" in metric_names


def test_evaluator_generates_markdown():
    agent = ResearchAgent(llm_client=MockLLMClient())
    framework = EvaluationFramework(agent=agent)
    results = [framework.evaluate_test_case(BENCHMARK_TEST_SUITE[0])]
    md = framework.generate_markdown_report(results)
    assert "# AI Research Agent - Evaluation Report" in md
    assert "TC-01" in md
    assert "PASS" in md
