"""
Standalone Runner for the AI Research Agent Evaluation Suite.
Usage:
    python run_eval.py
"""

import sys
from pathlib import Path
from rich.console import Console

from agent.evaluation.framework import EvaluationFramework
from agent.orchestrator import ResearchAgent


def main():
    console = Console()
    console.print("\n[bold cyan]=== Running AI Research Agent Evaluation Suite ===[/bold cyan]\n")

    agent = ResearchAgent()
    framework = EvaluationFramework(agent=agent)

    # Run all test cases
    results = framework.run_all()

    # Generate markdown report
    markdown_report = framework.generate_markdown_report(results)

    # Save to EVALUATION.md
    eval_file = Path("EVALUATION.md")
    eval_file.write_text(markdown_report, encoding="utf-8")
    console.print(f"\n[bold green]Successfully generated {eval_file.name}![/bold green]\n")


if __name__ == "__main__":
    main()
