"""
Unit tests for Pydantic models and schema validation.
"""

import pytest
from pydantic import ValidationError

from agent.models import (
    ConfidenceLevel,
    ExecutionTrace,
    ExecutionTraceStep,
    PlanStep,
    ResearchPlan,
    ResearchReport,
    SourceReference,
    ToolCall,
    ToolResult,
)


def test_source_reference_valid():
    src = SourceReference(
        source_id="S1",
        title="Test Source",
        url="https://example.com/test",
        snippet="This is a test snippet.",
        relevance_score=0.85
    )
    assert src.source_id == "S1"
    assert src.relevance_score == 0.85


def test_source_reference_invalid_score():
    with pytest.raises(ValidationError):
        SourceReference(
            source_id="S1",
            title="Test",
            url="https://example.com",
            snippet="Snippet",
            relevance_score=1.5  # Must be <= 1.0
        )


def test_plan_step_and_research_plan():
    step = PlanStep(
        step_number=1,
        goal="Discover candidate databases",
        tool_to_use="web_search",
        tool_query="vector database",
        expected_output="List of DBs"
    )
    plan = ResearchPlan(
        user_question="Compare vector DBs",
        intent_summary="Evaluate vector databases",
        sub_questions=["Which DBs exist?"],
        steps=[step],
        hypotheses_or_assumptions=["Open source options are best"]
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_to_use == "web_search"


def test_research_report_valid():
    report = ResearchReport(
        user_question="Compare vector DBs",
        short_answer="Chroma and Qdrant are leaders.",
        key_findings=["Qdrant is fast [S1]", "Chroma is simple [S2]"],
        sources_used=[
            SourceReference(source_id="S1", title="Qdrant", url="https://qdrant.tech", snippet="Fast Rust vector DB"),
            SourceReference(source_id="S2", title="Chroma", url="https://trychroma.com", snippet="Simple Python vector DB")
        ],
        confidence_level=ConfidenceLevel.HIGH,
        confidence_rationale="Thoroughly verified across official docs",
        limitations_or_assumptions=["Assumes self-hosted deployment"],
        suggested_next_steps=["Run latency benchmark on target dataset"]
    )
    assert report.confidence_level == ConfidenceLevel.HIGH
    assert len(report.key_findings) == 2
    assert len(report.sources_used) == 2


def test_research_report_missing_fields_raises_validation_error():
    with pytest.raises(ValidationError):
        ResearchReport(
            user_question="Test question",
            # Missing short_answer, key_findings, sources_used, etc.
        )
