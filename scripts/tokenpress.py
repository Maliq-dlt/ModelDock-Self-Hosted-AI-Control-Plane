import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.schemas import ChatCompletionRequest
from app.services.token_efficiency import optimize_request


def main() -> None:
    parser = argparse.ArgumentParser(description="Loss-aware ModelDock token efficiency preprocessor")
    parser.add_argument("input", nargs="?", default="-", help="OpenAI-compatible request JSON path, or - for stdin")
    parser.add_argument("--mode", choices=["off", "safe", "caveman", "ponytail", "stacked"], help="Override modeldock.token_mode")
    args = parser.parse_args()
    raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
    request = ChatCompletionRequest.model_validate(json.loads(raw))
    if args.mode:
        request.modeldock.token_mode = args.mode
    optimized, stats = optimize_request(request)
    print(json.dumps({"request": optimized.model_dump(mode="json", exclude_none=True), "stats": stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
