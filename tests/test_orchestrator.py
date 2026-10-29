"""
Unit and integration tests for the ResearchAgent orchestrator.
"""

from agent.llm import MockLLMClient
from agent.models import ConfidenceLevel, ResearchReport
from agent.orchestrator import ResearchAgent


def test_research_agent_end_to_end_run():
    events = []

    def callback(stage, msg, details):
        events.append((stage, msg))

    agent = ResearchAgent(llm_client=MockLLMClient(), step_callback=callback)
    report = agent.run("Compare the top 3 open-source vector databases for a startup building RAG products.")

    assert isinstance(report, ResearchReport)
    assert len(report.short_answer) > 20
    assert len(report.key_findings) >= 3
    assert len(report.sources_used) >= 1
    assert report.confidence_level in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW)
    assert len(report.limitations_or_assumptions) >= 1
    assert len(report.suggested_next_steps) >= 1

    # Check trace
    assert report.trace is not None
    assert report.trace.tools_called > 0
    assert report.trace.total_duration_seconds > 0.0

    # Check callback received events
    stages = [e[0] for e in events]
    assert "Planning" in stages
    assert "Synthesis" in stages
    assert "Complete" in stages


def test_research_agent_baseline_mode():
    agent = ResearchAgent(llm_client=MockLLMClient())
    baseline = agent.run_baseline("Compare the top 3 open-source vector databases")
    assert "non-agentic baseline" in baseline["mode"]
    assert len(baseline["raw_output"]) > 0
    assert baseline["external_tools_used"] == 0
