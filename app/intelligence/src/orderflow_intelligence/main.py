from __future__ import annotations

import argparse
import json

from orderflow_intelligence.graph.intake_graph import run_extraction_graph_with_defaults


def run() -> None:
    parser = argparse.ArgumentParser(description="Run the OrderFlow intake graph skeleton")
    parser.add_argument(
        "--text",
        required=True,
        help="Input text to parse through the LangGraph skeleton",
    )
    args = parser.parse_args()

    result = run_extraction_graph_with_defaults(args.text)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    run()
