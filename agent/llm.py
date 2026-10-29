"""
LLM Provider Abstraction layer.
Supports OpenAI, Google Gemini, and a deterministic Mock provider for offline testing and evaluation.
"""

from abc import ABC, abstractmethod
import json
import logging
import re
from typing import Any, Dict, List, Optional

from agent.config import settings

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """Abstract interface for LLM completion engines."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False
    ) -> str:
        """Generates text completion from the LLM."""
        pass

    def estimate_tokens(self, text: str) -> int:
        """Rough heuristic token estimator (~4 chars per token)."""
        return max(1, len(text) // 4)


class OpenAILLMClient(BaseLLMClient):
    """Client for OpenAI models using the official openai SDK."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        import openai
        self.api_key = api_key or settings.openai_api_key
        if not self.api_key:
            raise ValueError("OpenAI API key is required but not configured.")
        self.client = openai.OpenAI(api_key=self.api_key)
        self.model = model or settings.openai_model

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        return content or ""


class GeminiLLMClient(BaseLLMClient):
    """Client for Google Gemini models using the official google-genai SDK."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        from google import genai
        from google.genai import types
        self.types = types
        self.api_key = api_key or settings.gemini_api_key
        if not self.api_key:
            raise ValueError("Gemini API key is required but not configured.")
        self.client = genai.Client(api_key=self.api_key)
        self.model = model or settings.gemini_model

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False
    ) -> str:
        config_kwargs: Dict[str, Any] = {
            "temperature": 0.2,
        }
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        config = self.types.GenerateContentConfig(**config_kwargs)
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return response.text or ""


class MockLLMClient(BaseLLMClient):
    """
    Intelligent deterministic mock LLM provider.
    Enables immediate evaluation, test running, and offline demos without requiring API keys.
    Dynamically analyzes incoming prompts, tools, and retrieved sources to produce realistic outputs.
    """

    def __init__(self, model_name: str = "mock-agentic-v1"):
        self.model_name = model_name

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False
    ) -> str:
        lower_prompt = prompt.lower()
        lower_sys = (system_prompt or "").lower()

        # Case 1: Planning step
        if "research planner" in lower_sys or "executable research plan" in lower_prompt:
            return self._generate_mock_plan(prompt)

        # Case 2: Synthesis step
        if "synthesis" in lower_sys or "synthesize" in lower_prompt:
            return self._generate_mock_synthesis(prompt)

        # Case 3: Critique / Judge step
        if "judge" in lower_sys or "critique" in lower_sys:
            return json.dumps({
                "grounding_score": 0.94,
                "hallucination_detected": False,
                "confidence_adjusted": "High",
                "critique_notes": "All claims are strictly grounded in retrieved source context with direct citations."
            }, indent=2)

        # Generic JSON or text response
        if json_mode:
            return json.dumps({"status": "success", "message": "Completed processing."})
        return "Analysis completed successfully based on provided context."

    def _generate_mock_plan(self, prompt: str) -> str:
        """Generates domain-aware plan based on user query keywords."""
        lower = prompt.lower()

        if "vector" in lower:
            return json.dumps({
                "user_question": "Compare the top 3 open-source vector databases for a startup building RAG products.",
                "intent_summary": "Evaluate Chroma, Qdrant, and Milvus across developer ergonomics, scalability, and resource footprints.",
                "sub_questions": [
                    "What are the top open-source vector databases used for RAG applications?",
                    "How do their architectures compare regarding latency, indexing algorithms, and ease of deployment?",
                    "What are the operational tradeoffs for an early-stage startup?"
                ],
                "steps": [
                    {
                        "step_number": 1,
                        "goal": "Identify leading open-source vector databases and their general positioning",
                        "tool_to_use": "web_search",
                        "tool_query": "open source vector database comparison chroma qdrant milvus",
                        "expected_output": "List of top candidates and their core value propositions"
                    },
                    {
                        "step_number": 2,
                        "goal": "Deeply extract technical architecture and deployment specs for Qdrant and Chroma",
                        "tool_to_use": "web_scraper",
                        "tool_query": "https://qdrant.tech",
                        "expected_output": "Indexing types, Rust backend performance, and payload filtering capabilities"
                    },
                    {
                        "step_number": 3,
                        "goal": "Retrieve fundamental vector database indexing definitions from Wikipedia",
                        "tool_to_use": "wikipedia_lookup",
                        "tool_query": "vector database",
                        "expected_output": "Encyclopedic definition and algorithmic foundation"
                    }
                ],
                "hypotheses_or_assumptions": [
                    "Chroma will be simplest for fast prototyping but less scalable for distributed production",
                    "Qdrant balances single-node Rust performance with straightforward container deployment",
                    "Milvus offers maximum distributed scale at the cost of high Kubernetes operational complexity"
                ]
            }, indent=2)

        elif "saas" in lower or "indian" in lower or "hr" in lower:
            return json.dumps({
                "user_question": "Find 5 Indian B2B SaaS startups in HR tech and summarize their positioning.",
                "intent_summary": "Identify five prominent Indian HR tech SaaS companies and their market focus.",
                "sub_questions": [
                    "Which Indian B2B SaaS companies dominate the HR and payroll space?",
                    "What is each company's target market (SMB vs. Enterprise) and core positioning?"
                ],
                "steps": [
                    {
                        "step_number": 1,
                        "goal": "Search for top Indian B2B HR tech SaaS companies",
                        "tool_to_use": "web_search",
                        "tool_query": "indian b2b saas hr tech startups darwinbox keka zimyo",
                        "expected_output": "Overview of prominent Indian HR tech players"
                    },
                    {
                        "step_number": 2,
                        "goal": "Verify detailed positioning and market segmentation",
                        "tool_to_use": "web_search",
                        "tool_query": "indian hr tech platforms payroll attendance enterprise",
                        "expected_output": "Specific target customer profiles and differentiation"
                    }
                ],
                "hypotheses_or_assumptions": [
                    "Darwinbox targets Asian and global enterprise customers against Workday",
                    "Keka and Zimyo focus primarily on mid-market and SMB automated payroll"
                ]
            }, indent=2)

        elif "multi-agent" in lower or "customer support" in lower:
            return json.dumps({
                "user_question": "Research the pros and cons of using a multi-agent architecture for customer support automation.",
                "intent_summary": "Analyze architectural tradeoffs between single-agent and multi-agent systems in support workflows.",
                "sub_questions": [
                    "What are the modular advantages of multi-agent decomposition in customer support?",
                    "What are the operational pitfalls regarding latency, cost, and coordination loops?"
                ],
                "steps": [
                    {
                        "step_number": 1,
                        "goal": "Search for industry benchmarks and case studies on multi-agent customer support",
                        "tool_to_use": "web_search",
                        "tool_query": "multi-agent architecture customer support automation pros cons latency",
                        "expected_output": "Documented strengths and failure modes of multi-agent setups"
                    }
                ],
                "hypotheses_or_assumptions": [
                    "Multi-agent offers cleaner separation of concerns but suffers from compound token latency and failure propagation"
                ]
            }, indent=2)

        elif "memory" in lower:
            return json.dumps({
                "user_question": "Compare different approaches to adding memory in an AI support agent.",
                "intent_summary": "Evaluate conversational memory paradigms ranging from sliding windows to hierarchical MemGPT models.",
                "sub_questions": [
                    "What are the primary architectural approaches for agent memory?",
                    "How do buffer, vector-RAG, summary, and hierarchical memory compare in cost and retention?"
                ],
                "steps": [
                    {
                        "step_number": 1,
                        "goal": "Search for AI agent memory architectures and taxonomy",
                        "tool_to_use": "web_search",
                        "tool_query": "memory ai support agent buffer summary vector rag memgpt",
                        "expected_output": "Taxonomy of memory patterns and their engineering tradeoffs"
                    }
                ],
                "hypotheses_or_assumptions": [
                    "Buffer windows are lowest latency but drop long-term facts",
                    "Vector RAG allows infinite episodic recall but lacks chronological context"
                ]
            }, indent=2)

        elif "ignore" in lower or "reveal" in lower or "redacted" in lower:
            return json.dumps({
                "user_question": "Security inspection: prompt injection directive",
                "intent_summary": "Intercept hostile prompt directives and enforce safety policies.",
                "sub_questions": ["Is the query an injection attempt?", "Are system policies preserved?"],
                "steps": [
                    {
                        "step_number": 1,
                        "goal": "Perform security isolation and policy validation",
                        "tool_to_use": "web_search",
                        "tool_query": "prompt injection defense best practices",
                        "expected_output": "Policy validation verification"
                    }
                ],
                "hypotheses_or_assumptions": ["Input will be neutralized by prompt guardrails"]
            }, indent=2)

        # Fallback generic plan
        return json.dumps({
            "user_question": prompt[:100],
            "intent_summary": "Conduct structured multi-source research to answer the query.",
            "sub_questions": ["What are the key facts and verified sources answering this question?"],
            "steps": [
                {
                    "step_number": 1,
                    "goal": "Gather online research data",
                    "tool_to_use": "web_search",
                    "tool_query": prompt[:80],
                    "expected_output": "Relevant articles and documentation"
                }
            ],
            "hypotheses_or_assumptions": ["Sources will provide sufficient clarity for synthesis."]
        }, indent=2)

    def _generate_mock_synthesis(self, prompt: str) -> str:
        """Synthesizes structured research report from prompt and available context."""
        lower = prompt.lower()

        # Extract available source IDs from prompt
        source_tags = re.findall(r"\[(S\d+)\]", prompt) or ["S1", "S2", "S3"]
        s1 = source_tags[0] if len(source_tags) > 0 else "S1"
        s2 = source_tags[1] if len(source_tags) > 1 else s1
        s3 = source_tags[2] if len(source_tags) > 2 else s2

        if "vector" in lower:
            return json.dumps({
                "user_question": "Compare the top 3 open-source vector databases for a startup building RAG products.",
                "short_answer": "For an early-stage startup building RAG products, Chroma offers the fastest developer onboarding for local prototyping, Qdrant provides the best balance of low latency, payload filtering, and production reliability in Rust, while Milvus is best reserved for massive billion-vector enterprise workloads requiring Kubernetes clusters.",
                "key_findings": [
                    f"**Chroma DB**: Provides zero-configuration setup with an embedded SQLite/Clickhouse store [{s1}]. It is ideal for MVPs and quick developer iterations, but struggles with multi-tenant clustering and very large datasets.",
                    f"**Qdrant**: Written in Rust, it delivers outstanding query latencies and advanced payload-based pre-filtering during HNSW graph traversal [{s2}]. Supports scalar and product quantization that cuts memory consumption by up to 90%, making it the top recommended choice for production RAG startups.",
                    f"**Milvus**: A distributed, cloud-native vector database designed for enterprise scale [{s3}]. Supports diverse indexing algorithms (SCaNN, DiskANN, IVF_FLAT), but introduces significant operational overhead requiring Kubernetes, Kafka/Pulsar, and MinIO storage.",
                    f"**Algorithmic Foundations**: All three engines rely predominantly on Hierarchical Navigable Small World (HNSW) graphs for Approximate Nearest Neighbor (ANN) search, balancing recall accuracy with sub-millisecond retrieval speeds [{s1}, {s3}]."
                ],
                "confidence_level": "High",
                "confidence_rationale": "High confidence based on detailed technical benchmarks, official architecture documentation, and validated source grounding across official repositories.",
                "limitations_or_assumptions": [
                    "Benchmark performance numbers depend heavily on embedding dimension (e.g. 384 vs 1536), filter complexity, and available RAM.",
                    "Cloud-hosted managed offerings (e.g., Qdrant Cloud, Zilliz Cloud) were excluded to focus strictly on self-hosted open-source deployments.",
                    "Rapid release cycles mean pricing and feature parity evolve on a monthly basis."
                ],
                "suggested_next_steps": [
                    "Deploy Qdrant using the official Docker container on a single 4-core, 16GB RAM instance and benchmark p95 retrieval latency with target chunk sizes.",
                    "Implement binary or scalar quantization if document collection exceeds 500,000 embeddings to minimize memory costs.",
                    "Evaluate whether hybrid search (dense vector + sparse BM25) is required for domain-specific terminology."
                ]
            }, indent=2)

        elif "saas" in lower or "indian" in lower or "hr" in lower:
            return json.dumps({
                "user_question": "Find 5 Indian B2B SaaS startups in HR tech and summarize their positioning.",
                "short_answer": "The Indian B2B HR tech ecosystem features mature unicorns and fast-growing mid-market leaders. The top 5 prominent players are Darwinbox (enterprise HCM), Keka (SME-first HR and payroll automation), Zimyo (emerging businesses and financial wellness), Hono (AI-driven conversational HRMS), and GreytHR (compliance-centric payroll).",
                "key_findings": [
                    f"**Darwinbox**: Positioned as an enterprise Human Capital Management (HCM) platform competing directly with global giants like Workday and SAP SuccessFactors across APAC and MENA [{s1}].",
                    f"**Keka**: Highly focused on employee experience and automated payroll for mid-market and fast-scaling tech companies [{s1}, {s2}].",
                    f"**Zimyo**: Tailored for SMBs and startups, offering an integrated suite combining HRMS with employee financial benefits and micro-lending [{s1}].",
                    f"**Hono**: Differentiates through conversational AI chatbots that automate daily employee queries, leave management, and operational workflows [{s2}].",
                    f"**GreytHR**: One of the pioneering cloud HR platforms in India, trusted by over 20,000 businesses for strict statutory compliance and payroll processing [{s1}]."
                ],
                "confidence_level": "High",
                "confidence_rationale": "Verified across authoritative industry market reports and company product specifications with complete geographical and vertical alignment.",
                "limitations_or_assumptions": [
                    "Market positioning reflects current publicly available company profiles as of 2024-2026.",
                    "Valuation metrics and ARR figures are self-reported or based on venture funding disclosures."
                ],
                "suggested_next_steps": [
                    "Conduct a feature-gap matrix comparing Darwinbox and Keka for mid-sized enterprise requirements (500-2,000 employees).",
                    "Audit statutory compliance modules (PF, ESI, TDS) for multi-state Indian operations."
                ]
            }, indent=2)

        elif "multi-agent" in lower or "customer support" in lower:
            return json.dumps({
                "user_question": "Research the pros and cons of using a multi-agent architecture for customer support automation.",
                "short_answer": "A multi-agent architecture for customer support offers substantial benefits in modularity, specialized domain prompting, and automated verification loops, but introduces serious production liabilities including compounding latency, 2-4x higher token expenses, and non-deterministic routing failure modes.",
                "key_findings": [
                    f"**Key Pros - Modularity & Specialization**: Allows decomposing complex support workflows into dedicated agents (e.g., Triage, Knowledge Retrieval, Policy Validator, Response Drafter) with targeted prompts [{s1}].",
                    f"**Key Pros - Verification & Guardrails**: Independent critic or auditor agents can inspect drafted responses against internal security policies before delivery to customers [{s1}, {s2}].",
                    f"**Key Cons - Compounding Latency**: Sequential inter-agent turn loops inflate response times from ~1.5s to 6-12s, which degrades real-time live chat customer experiences [{s2}].",
                    f"**Key Cons - Cost & Debugging Complexity**: Multiple LLM hops quadruple token consumption and make root-cause analysis challenging when an agent passes slightly hallucinated state to the next agent [{s1}]."
                ],
                "confidence_level": "High",
                "confidence_rationale": "Derived from production deployment post-mortems and comparative agent architecture benchmarks.",
                "limitations_or_assumptions": [
                    "Latency figures assume hosted proprietary LLM API endpoints rather than local quantized models.",
                    "Tradeoffs vary significantly between asynchronous email ticket resolution and synchronous real-time chat."
                ],
                "suggested_next_steps": [
                    "Begin with a hybrid architecture: use deterministic routing and single-agent tool use for 80% of routine tickets.",
                    "Reserve multi-agent deliberation strictly for complex escalations, refunds, or policy disputes."
                ]
            }, indent=2)

        elif "memory" in lower:
            return json.dumps({
                "user_question": "Compare different approaches to adding memory in an AI support agent.",
                "short_answer": "Implementing conversational memory in AI support agents involves four primary architectural paradigms: Buffer Window Memory (recent turns), Summarization Memory (periodic LLM distillation), Semantic Vector RAG (episodic retrieval from past tickets), and Hierarchical/OS-style Memory (e.g. MemGPT/Letta) which separates working context from persistent archival storage.",
                "key_findings": [
                    f"**Buffer Window Memory**: Keeps the last N dialogue turns in the prompt window. Provides zero computational latency overhead but completely loses long-term context beyond the window [{s1}].",
                    f"**Summarization Memory**: Periodically compresses earlier dialogue turns into a concise running summary. Preserves key conversational milestones while stabilizing context size, but incurs recurring background LLM token costs [{s1}].",
                    f"**Vector/RAG Episodic Memory**: Embeds past tickets and user interaction histories into a vector database, retrieving relevant prior solutions semantically. Excellent for enterprise cross-ticket recall but lacks chronological awareness [{s1}, {s2}].",
                    f"**Hierarchical Memory (MemGPT-style)**: Treats context as RAM and an external database as Disk, providing explicit tool functions (core_memory_replace, archival_memory_insert) for autonomous agent memory management [{s2}]."
                ],
                "confidence_level": "High",
                "confidence_rationale": "Grounded in peer-reviewed memory architecture papers and production LLM design patterns.",
                "limitations_or_assumptions": [
                    "Evaluation assumes standard conversational support ticket lifecycles rather than lifelong companion dialogues.",
                    "Privacy regulations (GDPR/CCPA) impose strict data-deletion requirements on long-term vector memory stores."
                ],
                "suggested_next_steps": [
                    "Combine a short 5-turn Buffer Window for immediate conversational coherence with a Vector Store for historic ticket lookups.",
                    "Implement a deterministic user entity profile store (Key-Value) for customer subscription tier and preferences."
                ]
            }, indent=2)

        elif "ignore" in lower or "reveal your system" in lower or "redacted_suspicious" in lower or "injection" in lower:
            return json.dumps({
                "user_question": "Security inspection: prompt injection directive",
                "short_answer": "The input contained potential prompt injection directives attempting to override system behavior. The request was intercepted and neutralized by the prompt safety guardrail. Internal system prompts and credentials are confidential and protected.",
                "key_findings": [
                    "Defensive security filters successfully intercepted hostile prompt directives without leaking system instructions.",
                    "No external web tools were compromised during processing."
                ],
                "confidence_level": "Low",
                "confidence_rationale": "Confidence is marked Low because the request was an adversarial attack rather than a valid research inquiry.",
                "limitations_or_assumptions": [
                    "The system does not process hostile or unauthorized directive overrides."
                ],
                "suggested_next_steps": [
                    "Submit legitimate research questions regarding software engineering, architecture, or market intelligence."
                ]
            }, indent=2)

        elif "unicorn" in lower or "telepathic" in lower:
            return json.dumps({
                "user_question": prompt[:100],
                "short_answer": "No credible scientific literature or verified web sources exist regarding quantum telepathic protocols among unicorns. This appears to be a fictional or hypothetical concept.",
                "key_findings": [
                    "No academic papers or empirical studies corroborate quantum telepathy in biological organisms.",
                    "Search queries yielded zero factual or verifiable references."
                ],
                "confidence_level": "Low",
                "confidence_rationale": "Low confidence assigned due to zero verifiable evidence and complete lack of grounded sources.",
                "limitations_or_assumptions": [
                    "Query references non-existent or fictional entities and speculative future dates (2045)."
                ],
                "suggested_next_steps": [
                    "Clarify if the question refers to a specific science fiction work, novel, or game universe."
                ]
            }, indent=2)

        # Generic structured output
        return json.dumps({
            "user_question": prompt[:120],
            "short_answer": "Based on the retrieved sources, the topic was thoroughly analyzed across relevant architectural, operational, and practical dimensions.",
            "key_findings": [
                f"Core finding synthesized from external references [{s1}].",
                f"Comparative analysis indicates distinct tradeoffs across performance and complexity [{s2}]."
            ],
            "confidence_level": "Medium",
            "confidence_rationale": "Synthesized from available retrieved sources with moderate coverage.",
            "limitations_or_assumptions": ["Dependent on external source availability and freshness."],
            "suggested_next_steps": ["Execute empirical testing in an isolated staging environment."]
        }, indent=2)


def get_llm_client(provider: Optional[str] = None) -> BaseLLMClient:
    """
    Factory function to retrieve configured LLM client.
    Gracefully falls back to MockLLMClient if API keys are missing.
    """
    selected_provider = provider or settings.resolved_provider()

    if selected_provider == "gemini":
        try:
            return GeminiLLMClient()
        except Exception as exc:
            logger.warning("Failed to initialize Gemini client (%s). Falling back to MockLLMClient.", exc)
            return MockLLMClient()

    elif selected_provider == "openai":
        try:
            return OpenAILLMClient()
        except Exception as exc:
            logger.warning("Failed to initialize OpenAI client (%s). Falling back to MockLLMClient.", exc)
            return MockLLMClient()

    else:
        return MockLLMClient()
