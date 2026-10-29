# AI Research Agent: Production-Oriented Agentic Research Engine

> A production-grade AI agent designed to perform reliable, grounded deep research by decomposing user questions, orchestrating dynamic tools, filtering noise, sanitizing against adversarial injections, and synthesizing structured outputs with verified source citations.

---

## Architecture Overview

```
                      +-----------------------------+
                      |     User Research Query     |
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |   Step 0: Safety & Defense  |  <--- Neutralizes Prompt Injections
                      |      (PromptSanitizer)      |       & Tags Untrusted Content
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |  Step 1: Strategic Planning |  <--- Decomposes into 2-4 atomic sub-goals
                      |     (ResearchPlan Engine)   |       Selects best tools & query params
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      | Step 2: Tool Orchestration  |  <--- WebSearchTool (DuckDuckGo/Live)
                      |     & Dynamic Execution     |  <--- WebScraperTool (Clean HTML/Token limit)
                      |   (ToolRegistry + Retries)  |  <--- WikipediaTool (Definitions/Concepts)
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |  Step 3: Noise Filtering &  |  <--- Deduplicates URLs, drops 403s/blocks
                      |      Relevance Scoring      |       Ranks sources above threshold
                      |    (InformationFilter)      |
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |  Step 4: Grounded Synthesis |  <--- Strict Citation Rules ([S1], [S2])
                      |     (Pydantic Schema)       |       Quarantined XML Context
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      | Step 5: Self-Critique Judge |  <--- Verifies Citation Ratio & Grounding
                      |   & Observability Tracing   |       Adjusts Confidence (High/Med/Low)
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |   Structured Final Report   |
                      |   (JSON / Markdown / Web)   |
                      +-----------------------------+
```

---

## Core Questions Answered

### 1. Why did you choose an agentic approach here?
Direct single-turn LLM generation fails at serious research tasks due to three fundamental flaws:
1. **Knowledge Cutoff & Stale Benchmarks**: A static LLM cannot provide up-to-date market positioning, recent startup funding, or newly released vector database benchmarks.
2. **Hallucinated Citations**: Standard LLMs routinely generate plausible-sounding URLs and academic papers that do not exist (404s).
3. **Monolithic Failure on Complex Queries**: When asked a multi-part comparative question (e.g., *"Compare Chroma, Qdrant, and Milvus for an early-stage startup"*), single-turn models attempt to answer everything in one broad pass without investigating specific architectural dimensions.

An **agentic workflow (Planner -> Dynamic Multi-Tool Execution -> Re-ranking -> Synthesis -> Self-Reflective Judge)** transforms research from probabilistic text generation into a verifiable engineering pipeline:
- It **deconstructs ambiguous questions** into atomic search and scraping targets.
- It **selects specialized tools** suited for each task (broad web discovery vs. deep technical scraping vs. encyclopedic definitions).
- It **filters and verifies information** before feeding it into the synthesis context.
- It provides **deterministic structure, explicit source citations, and empirical confidence ratings**.

---

### 2. What tools did you use, and why?

The system integrates four distinct tools via a centralized `ToolRegistry`:

| Tool | Implementation | Primary Purpose | Why Chosen |
|:---|:---|:---|:---|
| **`WebSearchTool`** | DuckDuckGo HTML scraping + Curated Fallback Engine | Broad online discovery of articles, startups, and comparative benchmarks. | Operates out of the box without requiring paid proprietary search API keys (Tavily/Serper), while offering automatic retries and query sanitization. |
| **`WebScraperTool`** | `httpx` + `BeautifulSoup4` with token budgeting | Deep content extraction from specific documentation pages and technical whitepapers. | Search snippets often lack technical depth (e.g., Rust memory models or quantization algorithms). The scraper fetches full pages, strips non-content DOM nodes (`nav`, `script`, `style`), truncates to a token budget (8,000 chars), and isolates text in safe XML blocks. |
| **`WikipediaTool`** | MediaWiki API with custom User-Agent | Authoritative retrieval of foundational definitions, algorithms, and technical concepts. | Delivers noise-free, encyclopedic descriptions of core algorithms (e.g. HNSW indexing, RAG, vector quantization) without marketing fluff or paywalls. |
| **`ToolCache`** | In-memory key-value store with TTL hashing | Deduplicating identical queries and repeated page scrapes. | Cuts latency from seconds to under 1 millisecond on repeated runs and slashes outbound bandwidth and LLM token costs. |

---

### 3. How does the system handle bad tool results?

In production, external network interactions are inherently unreliable. The agent employs defensive failure isolation at every stage:

1. **Network Timeouts & Connection Failures**:
   - Every tool call is governed by a strict timeout (default: 12.0s) and wrapped in a retry loop with exponential backoff.
   - If an endpoint times out, the `BaseTool` catches the exception and returns a structured `ToolResult(success=False, error_message=...)` rather than crashing the orchestrator.
2. **HTTP 403 / 404 / Cloudflare Anti-Bot Walls**:
   - The `WebScraperTool` inspects HTTP response status codes. Blocked or broken URLs return clear error tokens.
   - The `InformationFilter` scans retrieved snippets against signature error phrases (`"403 Forbidden"`, `"Cloudflare Ray ID"`, `"Verify you are human"`). Detected error pages are discarded before synthesis.
3. **Malformed or Empty Tool Output**:
   - If a search query yields zero results or empty text, the agent detects the information gap, notes the deficiency, and falls back to secondary query formulations.
4. **Low-Quality / Irrelevant Noise**:
   - `InformationFilter.filter_and_rank_sources` calculates normalized keyword overlap and relevance scores between the user's intent and each candidate source. Sources scoring below `0.25` are pruned, and results are deduplicated by canonical URL.

---

### 4. How do you reduce hallucinations?

1. **Strict Context Isolation via Prompt Sandboxing**:
   - External web text is wrapped in defensive structural XML tags: `<external_untrusted_data id="S1" source="...">`.
   - The synthesis system prompt explicitly commands the model: *"Ground every substantive claim strictly in the provided sources. Do NOT invent facts or benchmark statistics."*
2. **Mandatory Source Attribution**:
   - Every finding generated in `key_findings` must contain an explicit citation tag (e.g., `[S1]`, `[S2]`) pointing to a real URL recorded in `sources_used`.
3. **Automated Self-Critique / Judge Step**:
   - Before returning the final report, a reflection stage inspects the synthesized claims against the retrieved sources.
   - It computes the **citation density ratio**. If fewer than 50% of the findings are cited, the system automatically downgrades the confidence rating to `Medium` or `Low` and appends an explicit warning to `limitations_or_assumptions`.
4. **Deterministic Pydantic Schema Enforcement**:
   - Output generation uses structured JSON mode validated against `ResearchReport`. If validation fails, an automatic repair retry loop is triggered.

---

### 5. How would you make this production-ready?

To scale this system to an enterprise-grade high-throughput production deployment:

1. **Asynchronous Parallel Tool Execution**:
   - Migrate tool invocations from sequential execution to `asyncio.gather` with an `asyncio.Semaphore(5)` to execute sub-searches and page scrapes concurrently, reducing overall query latency by 60%.
2. **Distributed Multi-Tier Caching**:
   - Upgrade `ToolCache` from in-memory to Redis with semantic vector caching (e.g. GPTCache), caching identical or semantically similar research queries across users.
3. **Sandboxed Headless Browser Execution**:
   - For JavaScript-heavy single-page applications (SPAs), deploy headless Playwright / Chromium workers in isolated containers (e.g., Docker or AWS Lambda) with strict resource limits and egress firewalls.
4. **Dynamic Context-Aware Token Budgeting**:
   - Implement dynamic chunking and cross-encoder re-ranking (e.g. Cohere Rerank or BGE-Reranker) to extract only the most relevant 500-token passages from long pages before passing them to the synthesis prompt.
5. **Circuit Breakers & Graceful Degradation**:
   - Implement a circuit breaker (e.g. using `pybreaker`) for external search engines and LLM providers to fail over automatically from OpenAI to Gemini or offline cached summaries during upstream outages.

---

### 6. What would you monitor in production?

| Category | Telemetry & Metrics | Target SLA / Alert Threshold |
|:---|:---|:---|
| **System Reliability** | P50, P95, P99 Request Latency | P95 < 5.0 seconds |
| | Tool Failure Rate (% of search/scrape 4xx/5xx errors) | Alert if > 5% over 5-minute window |
| | Schema Validation Error Rate | 0.0% (Zero tolerance for malformed API responses) |
| **Quality & Grounding** | Grounding Citation Ratio (% of findings cited) | Alert if citation coverage drops below 70% |
| | Confidence Level Distribution | Track shifts in High vs Medium vs Low ratios |
| | LLM-as-a-Judge Hallucination Sampling Rate | Periodic background evaluation on 1% of live traffic |
| **Financial / Cost** | Input & Output Token Consumption per Query | Track average token cost (< $0.01 per research run) |
| | Cache Hit Ratio | Target > 35% on common domain queries |
| **Security** | Prompt Injection Interception Count | Alert on sudden spike in flagged directives |

---

### 7. What were your key tradeoffs?

1. **Single-Agent Planner-Executor vs. Multi-Agent Swarm**:
   - *Decision*: Chose a deterministic, transparent single-agent planner-executor with self-critique over a multi-agent swarm (e.g. AutoGen / CrewAI).
   - *Tradeoff*: Multi-agent swarms introduce severe inter-agent chatter, compounding latency (15-30s), 3-5x higher token costs, and non-deterministic loops. A disciplined single-agent architecture offers sub-3-second latency, deterministic debugging, and superior reliability.
2. **Selective Deep Scraping vs. Snippet-Only Synthesis**:
   - *Decision*: Selectively scrape top 2-3 high-relevance URLs while falling back to search snippets for the rest.
   - *Tradeoff*: Scraping every search result adds substantial network latency and bot-blocking risk. Selective scraping balances technical depth with fast response times.
3. **Strict Schema Validation vs. Free-Form Text**:
   - *Decision*: Enforced strict Pydantic JSON schema output with a repair retry loop.
   - *Tradeoff*: Schema validation requires slightly more defensive parsing code and occasional retry overhead, but completely eliminates downstream frontend rendering bugs and API integration errors.

---

## Installation & Setup

### Prerequisites
- Python 3.9+ (Tested on Python 3.10 and 3.11)
- Git

### 1. Clone & Set Up Virtual Environment

```bash
# Clone the repository
git clone https://github.com/ommore86/AI-Research-Agent.git
cd AI-Research-Agent

# Create and activate a virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables (Optional)

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

*Note: The agent includes a high-fidelity **Deterministic Mock Engine** by default (`DEFAULT_LLM_PROVIDER=mock`). You can run all CLI tools, tests, benchmarks, and web interfaces immediately without entering any paid API keys!*

To use live LLMs, simply add your keys to `.env`:
```env
OPENAI_API_KEY=sk-...
# OR
GEMINI_API_KEY=AIzaSy...
```

---

## Usage Guide

### 1. Interactive Terminal CLI

```bash
# Launch interactive CLI
python -m agent.cli

# Run a single query directly and export report to markdown
python -m agent.cli --query "Compare the top 3 open-source vector databases for a startup building RAG products." --output outputs/report.md

# Compare agentic output side-by-side with raw ungrounded LLM baseline
python -m agent.cli --query "Compare different approaches to adding memory in an AI support agent." --baseline
```

### 2. Modern Web Dashboard & Visual UI

```bash
python -m agent.web
```
*Open your browser at **`http://127.0.0.1:8000`** to access the research dashboard with live execution timelines, citation badges, and JSON exports.*

### 3. Automated Interactive Demo (For Video Recording)

```bash
python demo.py
```
*Step-by-step interactive walkthrough presenting Happy Path, Failure/Edge Case (Prompt Injection), and Baseline Comparison.*

---

## Testing & Evaluation

### Run Unit & Integration Test Suite

```bash
python -m pytest tests/
```
*Executes all 20 unit tests verifying Pydantic schema validation, tool error recovery, caching, prompt injection defense, and agent orchestration.*

### Run Automated Benchmark Evaluation Suite

```bash
python run_eval.py
```
*Evaluates the 6 benchmark test cases and automatically generates the complete `EVALUATION.md` report.*

---

## Repository Structure

```
AI-Research-Agent/
├── README.md                   # Comprehensive system documentation & tradeoff analysis
├── EVALUATION.md               # Benchmark evaluation report with test-by-test breakdown
├── DEMO_GUIDE.md               # Script & presentation walkthrough for 3-5 min demo video
├── demo.py                     # Interactive demo runner for video presentation
├── run_eval.py                 # Standalone benchmark evaluation script
├── requirements.txt            # Pinned dependencies
├── pyproject.toml              # Packaging & tool configuration
├── .env.example                # Sample environment configuration
│
├── agent/                      # Core agent framework
│   ├── __init__.py
│   ├── config.py               # Pydantic settings & environment management
│   ├── models.py               # Pydantic schemas (ResearchPlan, ResearchReport, etc.)
│   ├── llm.py                  # Multi-provider LLM abstraction (OpenAI, Gemini, Mock)
│   ├── orchestrator.py         # The Agent Core: Plan -> Tools -> Filter -> Synthesize -> Critique
│   ├── prompts.py              # System prompts with anti-hallucination & anti-injection guardrails
│   ├── cli.py                  # Rich terminal interactive UI with formatted panels
│   ├── web.py                  # FastAPI app & modern research dashboard
│   │
│   ├── tools/                  # Extensible tool ecosystem
│   │   ├── base.py             # BaseTool with retries, timeout isolation, and metrics
│   │   ├── search.py           # WebSearchTool (DuckDuckGo + Curated Fallback)
│   │   ├── scraper.py          # WebScraperTool (HTML sanitization, token budgeting)
│   │   ├── wikipedia.py        # WikipediaTool (Authoritative encyclopedia lookup)
│   │   ├── cache.py            # ToolCache with TTL hashing
│   │   └── registry.py         # Centralized ToolRegistry
│   │
│   ├── safety/                 # Defensive engineering
│   │   ├── sanitizer.py        # Prompt injection detection & XML boundary wrapping
│   │   └── filter.py           # Noise reduction, URL deduplication & relevance scoring
│   │
│   └── evaluation/             # Evaluation framework
│       ├── dataset.py          # 6 diverse benchmark test cases
│       └── framework.py        # Quantitative scoring engine (Grounding, Schema, Safety)
│
├── tests/                      # Automated test suite (20 passing tests)
│   ├── test_models.py          # Schema validation tests
│   ├── test_tools.py           # Tool execution, timeout, and caching tests
│   ├── test_sanitizer.py       # Prompt injection sanitization tests
│   ├── test_orchestrator.py    # End-to-end agentic workflow tests
│   └── test_evaluator.py       # Evaluator framework tests
│
└── outputs/                    # Realistic sample research outputs
    ├── sample_1_vector_dbs.json
    ├── sample_1_vector_dbs.md
    ├── sample_2_indian_saas.json
    ├── sample_2_indian_saas.md
    ├── sample_3_multi_agent_support.json
    └── sample_3_multi_agent_support.md
```

---

## Author & Project Info

- **Author**: Om More
- **Project**: AI Startup Intern Assignment — Production-Oriented AI Research Agent
- **License**: MIT
