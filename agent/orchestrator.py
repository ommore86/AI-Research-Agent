"""
Core Agent Orchestrator: Multi-step Planner-Executor with Tool Calling,
Filtering, Anti-Hallucination Grounding, Self-Critique, and Observability Tracing.
"""

import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.config import settings
from agent.llm import BaseLLMClient, get_llm_client
from agent.models import (
    ConfidenceLevel,
    ExecutionTrace,
    ExecutionTraceStep,
    ResearchPlan,
    ResearchReport,
    SourceReference,
    ToolResult,
)
from agent.prompts import (
    CRITIQUE_SYSTEM_PROMPT,
    PLANNING_SYSTEM_PROMPT,
    PLANNING_USER_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
    SYNTHESIS_USER_PROMPT,
)
from agent.safety.filter import InformationFilter
from agent.safety.sanitizer import PromptSanitizer
from agent.tools.registry import ToolRegistry, create_default_registry

logger = logging.getLogger(__name__)


class ResearchAgent:
    """
    Production-grade AI Research Agent.
    Orchestrates:
      1. Query inspection & prompt injection defense
      2. Research planning & tool selection
      3. Dynamic tool execution loop with error handling
      4. Source filtering, ranking & deduplication
      5. Grounded synthesis with citation requirements
      6. Self-critique & confidence evaluation
      7. Diagnostic execution tracing
    """

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
        step_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None
    ):
        self.llm = llm_client or get_llm_client()
        self.registry = tool_registry or create_default_registry(
            cache_enabled=settings.cache_enabled,
            timeout_seconds=settings.tool_timeout_seconds
        )
        self.step_callback = step_callback  # Hook for live UI/CLI streaming events

    def _notify(self, stage: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Emits progress event to optional UI/CLI subscriber."""
        if self.step_callback:
            try:
                self.step_callback(stage, message, details or {})
            except Exception as e:
                logger.warning("Step callback failed: %s", e)

    def _extract_json_from_llm(self, text: str) -> Dict[str, Any]:
        """
        Robust JSON parser that strips markdown code fences, handles leading/trailing commentary,
        and repairs common LLM JSON syntax quirks.
        """
        cleaned = text.strip()

        # Strip markdown fences if present
        if "```" in cleaned:
            # Find json block or generic code block
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
            if match:
                cleaned = match.group(1).strip()

        # If text still contains non-JSON prefix/suffix, find outer braces
        if not (cleaned.startswith("{") and cleaned.endswith("}")):
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start:end + 1]

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            # Repair trailing commas before closing braces
            repaired = re.sub(r",\s*([\]}])", r"\1", cleaned)
            try:
                return json.loads(repaired)
            except Exception:
                raise ValueError(f"Failed to parse valid JSON from LLM output: {exc}. Content preview: {cleaned[:200]}")

    def create_plan(self, question: str) -> ResearchPlan:
        """
        Step 1: Analyzes question and produces structured execution plan.
        """
        tool_descriptions = self.registry.get_tool_descriptions()
        user_prompt = PLANNING_USER_PROMPT.format(
            question=question,
            tool_descriptions=tool_descriptions
        )

        response_text = self.llm.generate(
            prompt=user_prompt,
            system_prompt=PLANNING_SYSTEM_PROMPT,
            json_mode=True
        )

        parsed_json = self._extract_json_from_llm(response_text)
        return ResearchPlan(**parsed_json)

    def execute_plan_steps(
        self,
        plan: ResearchPlan,
        trace: ExecutionTrace
    ) -> List[SourceReference]:
        """
        Step 2 & 3: Iterates through plan steps, selects tools, and collects raw sources.
        """
        raw_sources: List[SourceReference] = []
        source_counter = 1

        for step in plan.steps[:settings.max_plan_steps]:
            step_start = time.time()
            self._notify(
                stage="ToolExecution",
                message=f"Executing Step {step.step_number}: {step.goal}",
                details={"tool": step.tool_to_use, "query": step.tool_query}
            )

            # Map tool arguments
            args: Dict[str, Any] = {}
            if step.tool_to_use == "web_search":
                args = {"query": step.tool_query, "max_results": settings.max_search_results}
            elif step.tool_to_use == "web_scraper":
                args = {"url": step.tool_query, "max_chars": settings.max_chars_per_scraped_page}
            elif step.tool_to_use == "wikipedia_lookup":
                args = {"query": step.tool_query}
            else:
                args = {"query": step.tool_query}

            tool_result: ToolResult = self.registry.execute_tool(step.tool_to_use, args)
            step_duration = time.time() - step_start

            trace.tools_called += 1
            if tool_result.success:
                trace.tools_succeeded += 1
            else:
                trace.tools_failed += 1

            # Log to execution trace
            trace.steps.append(ExecutionTraceStep(
                stage="ToolExecution",
                description=f"Step {step.step_number} ({step.tool_to_use}): {step.goal}",
                status="success" if tool_result.success else "failed",
                details={
                    "tool": step.tool_to_use,
                    "arguments": args,
                    "cached": tool_result.cached,
                    "error": tool_result.error_message
                },
                duration_seconds=round(step_duration, 3)
            ))

            # Transform raw tool outputs into SourceReference items
            if tool_result.success and tool_result.output:
                if step.tool_to_use == "web_search" and isinstance(tool_result.output, list):
                    for item in tool_result.output:
                        if isinstance(item, dict) and item.get("url"):
                            raw_sources.append(SourceReference(
                                source_id=f"TEMP_{source_counter}",
                                title=item.get("title", "Untitled Source"),
                                url=item.get("url", ""),
                                snippet=item.get("snippet", ""),
                                relevance_score=1.0
                            ))
                            source_counter += 1

                elif step.tool_to_use == "web_scraper" and isinstance(tool_result.output, dict):
                    content = tool_result.output.get("content", "")
                    title = tool_result.output.get("title", "Scraped Webpage")
                    url = tool_result.output.get("url", step.tool_query)
                    if content and len(content) > 50:
                        raw_sources.append(SourceReference(
                            source_id=f"TEMP_{source_counter}",
                            title=title,
                            url=url,
                            snippet=content[:1500],  # summary snippet for context
                            relevance_score=1.0
                        ))
                        source_counter += 1

                elif step.tool_to_use == "wikipedia_lookup" and isinstance(tool_result.output, dict):
                    summary = tool_result.output.get("summary", "")
                    title = tool_result.output.get("title", "Wikipedia Article")
                    url = tool_result.output.get("url", "")
                    if summary:
                        raw_sources.append(SourceReference(
                            source_id=f"TEMP_{source_counter}",
                            title=f"Wikipedia: {title}",
                            url=url or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                            snippet=summary,
                            relevance_score=1.0
                        ))
                        source_counter += 1

        trace.sources_retrieved = len(raw_sources)
        return raw_sources

    def filter_and_ground_sources(
        self,
        raw_sources: List[SourceReference],
        query: str,
        trace: ExecutionTrace
    ) -> List[SourceReference]:
        """
        Step 4: Filters weak, noisy, or blocked sources and deduplicates results.
        """
        filter_start = time.time()
        filtered = InformationFilter.filter_and_rank_sources(
            sources=raw_sources,
            query=query,
            min_relevance=settings.relevance_threshold,
            max_sources=6
        )

        trace.sources_filtered_out = max(0, len(raw_sources) - len(filtered))
        trace.steps.append(ExecutionTraceStep(
            stage="Filtering",
            description=f"Filtered {len(raw_sources)} raw sources down to {len(filtered)} verified sources",
            status="success",
            details={
                "retained_sources": [s.title for s in filtered],
                "filtered_out_count": trace.sources_filtered_out
            },
            duration_seconds=round(time.time() - filter_start, 3)
        ))

        return filtered

    def synthesize_report(
        self,
        question: str,
        sources: List[SourceReference],
        trace: ExecutionTrace
    ) -> ResearchReport:
        """
        Step 5: Synthesizes final response with source grounding and schema validation.
        """
        synth_start = time.time()
        self._notify(stage="Synthesis", message="Synthesizing final research report with source citations")

        # Format sources with anti-injection wrapping
        source_blocks: List[str] = []
        for src in sources:
            wrapped = PromptSanitizer.wrap_untrusted_content(
                content=f"Title: {src.title}\nURL: {src.url}\nExcerpt: {src.snippet}",
                source_id=src.source_id,
                source_url=src.url
            )
            source_blocks.append(f"[{src.source_id}] {wrapped}")

        sources_context = "\n\n".join(source_blocks) if source_blocks else "No external sources could be retrieved."

        user_prompt = SYNTHESIS_USER_PROMPT.format(
            question=question,
            sources_context=sources_context
        )

        # Estimate tokens used
        trace.tokens_estimated += self.llm.estimate_tokens(user_prompt) + 600

        # LLM Synthesis with retry repair loop
        last_error = None
        for attempt in range(1, settings.max_retries + 1):
            try:
                response_text = self.llm.generate(
                    prompt=user_prompt,
                    system_prompt=SYNTHESIS_SYSTEM_PROMPT,
                    json_mode=True
                )
                parsed_json = self._extract_json_from_llm(response_text)

                # Inject sources_used and user_question if missing or incomplete
                parsed_json["sources_used"] = [s.model_dump() for s in sources]
                if not parsed_json.get("user_question"):
                    parsed_json["user_question"] = question

                report = ResearchReport(**parsed_json)
                report.trace = trace

                trace.steps.append(ExecutionTraceStep(
                    stage="Synthesis",
                    description="Final report synthesized and validated against schema",
                    status="success",
                    duration_seconds=round(time.time() - synth_start, 3)
                ))
                return report

            except Exception as exc:
                last_error = exc
                logger.warning("Synthesis validation attempt %d failed: %s", attempt, exc)
                time.sleep(0.5)

        # Fallback if synthesis repeatedly fails schema validation
        logger.error("Synthesis failed schema validation after retries: %s", last_error)
        fallback_report = ResearchReport(
            user_question=question,
            short_answer="Synthesis encountered schema validation errors during parsing.",
            key_findings=[f"Retrieved {len(sources)} sources but failed to format final JSON: {last_error}"],
            sources_used=sources,
            confidence_level=ConfidenceLevel.LOW,
            confidence_rationale="Fallback generated due to schema validation failure.",
            limitations_or_assumptions=["System was unable to format structured findings."],
            suggested_next_steps=["Re-run query with higher timeout or alternate LLM provider."],
            trace=trace
        )
        return fallback_report

    def critique_report(
        self,
        report: ResearchReport,
        sources: List[SourceReference],
        trace: ExecutionTrace
    ) -> ResearchReport:
        """
        Step 6: Self-reflection and critique step.
        Verifies citation grounding and adjusts confidence if sources are sparse.
        """
        critique_start = time.time()
        self._notify(stage="Critique", message="Running self-reflection & grounding verification judge")

        # Fast heuristic checks if sources are empty
        if not sources:
            report.confidence_level = ConfidenceLevel.LOW
            report.confidence_rationale = "Low confidence: No external sources could be retrieved from search or scraping."
            report.limitations_or_assumptions.append("Zero external grounding sources available.")
            return report

        # Check citation coverage in findings
        cited_findings = [f for f in report.key_findings if re.search(r"\[S\d+\]", f)]
        citation_ratio = len(cited_findings) / max(1, len(report.key_findings))

        if citation_ratio < 0.5:
            # Downgrade confidence if claims lack citations
            report.confidence_level = ConfidenceLevel.MEDIUM
            report.confidence_rationale += " (Confidence adjusted to Medium: Some findings lacked explicit source tags)."
            report.limitations_or_assumptions.append("Certain findings rely on generalized model knowledge rather than cited sources.")

        trace.steps.append(ExecutionTraceStep(
            stage="Critique",
            description=f"Self-critique completed. Citation ratio: {round(citation_ratio, 2)}",
            status="success",
            details={
                "citation_ratio": round(citation_ratio, 2),
                "confidence": report.confidence_level.value
            },
            duration_seconds=round(time.time() - critique_start, 3)
        ))

        return report

    def run(self, question: str) -> ResearchReport:
        """
        Full end-to-end research execution pipeline.
        """
        total_start_time = time.time()
        trace = ExecutionTrace()

        # Step 0: Input sanitization & injection check
        clean_question, is_suspicious, detection_reason = PromptSanitizer.inspect_and_sanitize_query(question)
        if is_suspicious:
            logger.warning("Suspicious prompt injection pattern detected: %s", detection_reason)
            trace.steps.append(ExecutionTraceStep(
                stage="SafetyInspection",
                description="Prompt injection patterns detected and neutralized",
                status="flagged",
                details={"reason": detection_reason}
            ))

        # Step 1: Create Plan
        self._notify(stage="Planning", message="Analyzing question and generating research plan")
        plan_start = time.time()
        try:
            plan = self.create_plan(clean_question)
            trace.steps.append(ExecutionTraceStep(
                stage="Planning",
                description=f"Generated plan with {len(plan.steps)} steps: {plan.intent_summary}",
                status="success",
                details={"steps": [s.model_dump() for s in plan.steps]},
                duration_seconds=round(time.time() - plan_start, 3)
            ))
        except Exception as exc:
            logger.warning("Dynamic planning failed (%s). Using emergency fallback plan.", exc)
            plan = ResearchPlan(
                user_question=clean_question,
                intent_summary="Emergency fallback research plan",
                sub_questions=[clean_question],
                steps=[PlanStep(
                    step_number=1,
                    goal="Search web for direct query answers",
                    tool_to_use="web_search",
                    tool_query=clean_question,
                    expected_output="Direct relevant sources"
                )],
                hypotheses_or_assumptions=["Standard search will yield baseline information"]
            )

        # Step 2 & 3: Execute Plan & Gather Information
        raw_sources = self.execute_plan_steps(plan, trace)

        # Step 4: Filter & Deduplicate Sources
        self._notify(stage="Filtering", message="Filtering and ranking retrieved sources")
        verified_sources = self.filter_and_ground_sources(raw_sources, clean_question, trace)

        # Step 5: Synthesize Final Report
        report = self.synthesize_report(clean_question, verified_sources, trace)

        # Step 6: Critique & Verify Grounding
        final_report = self.critique_report(report, verified_sources, trace)

        # Complete trace timing
        trace.total_duration_seconds = round(time.time() - total_start_time, 3)
        final_report.trace = trace

        self._notify(
            stage="Complete",
            message=f"Research complete in {trace.total_duration_seconds}s. Confidence: {final_report.confidence_level.value}",
            details={"duration": trace.total_duration_seconds}
        )

        return final_report

    def run_baseline(self, question: str) -> Dict[str, Any]:
        """
        Non-agentic baseline comparison mode.
        Calls the raw LLM directly without tools, planning, or external retrieval.
        Useful for evaluating the accuracy, citation presence, and hallucination reduction of the agent.
        """
        start_time = time.time()
        prompt = (
            f"Please answer the following research question directly based solely on your internal training data:\n\n"
            f"Question: {question}\n\n"
            f"Provide a short answer, 3 key findings, and list any sources you rely on."
        )

        raw_output = self.llm.generate(prompt=prompt)
        duration = round(time.time() - start_time, 3)

        return {
            "mode": "non-agentic baseline (raw LLM)",
            "question": question,
            "raw_output": raw_output,
            "duration_seconds": duration,
            "external_tools_used": 0,
            "verified_sources": []
        }

    def run_stream(self, question: str):
        """
        Executes research workflow while yielding real-time progress events.
        Enables genuine Server-Sent Events (SSE) streaming for web interfaces.
        """
        import queue
        import threading

        q: queue.Queue = queue.Queue()

        def stream_callback(stage: str, msg: str, details: Dict[str, Any]):
            q.put(("progress", stage, msg, details))

        def worker():
            saved_cb = self.step_callback
            try:
                self.step_callback = stream_callback
                report = self.run(question)
                q.put(("complete", report))
            except Exception as exc:
                q.put(("error", str(exc)))
            finally:
                self.step_callback = saved_cb

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        while True:
            try:
                item = q.get(timeout=45.0)
                if item[0] == "progress":
                    yield {
                        "type": "progress",
                        "stage": item[1],
                        "message": item[2],
                        "details": item[3]
                    }
                elif item[0] == "complete":
                    yield {
                        "type": "complete",
                        "report": item[1].model_dump()
                    }
                    break
                elif item[0] == "error":
                    yield {
                        "type": "error",
                        "error": item[1]
                    }
                    break
            except queue.Empty:
                yield {"type": "error", "error": "Execution timed out waiting for agent."}
                break
        t.join(timeout=1.0)
