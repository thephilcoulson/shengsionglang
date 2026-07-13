"""Command-line interface for ShengSiong.

Usage:
    python -m shengsiong run <file.sheng>
    python -m shengsiong eval "<source>"
    echo "..." | python -m shengsiong run -
"""

from __future__ import annotations

import sys

from .lexer import Lexer, LexError
from .parser import Parser, ParseError
from .interpreter import Interpreter, RuntimeErrorSS


def _run_source(source: str) -> int:
    try:
        tokens = Lexer(source).tokenize()
        program = Parser(tokens).parse()
        interp = Interpreter()
        interp.interpret(program)
    except (LexError, ParseError, RuntimeErrorSS) as e:
        print(str(e), file=sys.stderr)
        return 1
    for line in interp.output:
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "run":
        if not rest:
            print("run: expected a file path or '-'", file=sys.stderr)
            return 2
        path = rest[0]
        if path == "-":
            source = sys.stdin.read()
        else:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    source = fh.read()
            except OSError as e:
                print(f"cannot read {path!r}: {e}", file=sys.stderr)
                return 2
        return _run_source(source)
    if cmd == "eval":
        if not rest:
            print("eval: expected a source string", file=sys.stderr)
            return 2
        return _run_source(" ".join(rest))
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
