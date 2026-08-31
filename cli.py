"""CLI entry point: python cli.py "your topic here" """
import argparse
import json
import sys

from agents.coordinator import run_pipeline_safe


def main():
    parser = argparse.ArgumentParser(description="4-agent research pipeline (researcher -> summarizer -> evaluator -> coordinator)")
    parser.add_argument("topic", nargs="?", default="the current state of AI agent frameworks")
    parser.add_argument("--max-iterations", type=int, default=5)
    args = parser.parse_args()

    if not args.topic.strip():
        print("error: topic must not be empty", file=sys.stderr)
        sys.exit(2)

    result = run_pipeline_safe(args.topic.strip(), max_iterations=args.max_iterations)
    print("\n=== FINAL RESULT ===", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("status") == "ok" else 1)


if __name__ == "__main__":
    main()
