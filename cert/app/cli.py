from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from app.config import DEFAULT_PLACEHOLDER
from app.services.certificates import CertificateGenerationError, generate_certificates


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the certificate generator.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate PDFs from a local names file.",
    )
    generate_parser.add_argument("names_file", type=Path)
    generate_parser.add_argument("--output-dir", type=Path, default=Path("output"))
    generate_parser.add_argument("--template", type=Path, default=Path("Certificate.docx"))
    generate_parser.add_argument("--font", type=Path, default=Path("AbarHigh-SemiBold.ttf"))
    generate_parser.add_argument("--placeholder", default=DEFAULT_PLACEHOLDER)

    serve_parser = subparsers.add_parser("serve", help="Run the FastAPI web service.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(_normalize_argv(argv))
    try:
        if args.command == "generate":
            pdfs = generate_certificates(
                names_file=args.names_file,
                output_dir=args.output_dir,
                template_path=args.template,
                font_path=args.font,
                placeholder=args.placeholder,
            )
            for pdf in pdfs:
                print(pdf)
            return 0

        if args.command == "serve":
            import uvicorn

            uvicorn.run(
                "app.main:app",
                host=args.host,
                port=args.port,
                reload=args.reload,
            )
            return 0
    except (CertificateGenerationError, FileNotFoundError, OSError) as exc:
        print(f"Error: {exc}")
        return 1
    return 1


def _normalize_argv(argv: Sequence[str] | None) -> Sequence[str] | None:
    if not argv:
        return argv
    first = argv[0]
    known_commands = {"generate", "serve", "-h", "--help"}
    if first not in known_commands:
        return ["generate", *argv]
    return argv
