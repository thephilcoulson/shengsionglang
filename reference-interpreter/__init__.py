"""ShengSiong: a domain-specific language for supermarket supply-chain & logistics.

Named after the Singapore supermarket chain. ShengSiong lets you declare
stores, products, suppliers, warehouses and trucks, then express restocking,
ordering, pricing and fulfilment logic at a high level -- the runtime handles
inventory bookkeeping, reorder logistics and delivery routing for you.
"""

from .lexer import Lexer, Token, TokenType, LexError
from .parser import Parser, ParseError
from .interpreter import Interpreter, RuntimeErrorSS
from .runtime import Supermarket

__version__ = "1.0.0"

__all__ = [
    "Lexer",
    "Token",
    "TokenType",
    "LexError",
    "Parser",
    "ParseError",
    "Interpreter",
    "RuntimeErrorSS",
    "Supermarket",
    "run",
    "run_file",
]


def run(source: str):
    """Lex, parse and interpret ShengSiong ``source``; return the Interpreter."""
    tokens = Lexer(source).tokenize()
    program = Parser(tokens).parse()
    interp = Interpreter()
    interp.interpret(program)
    return interp


def run_file(path: str):
    """Read and run a ``.sheng`` source file."""
    with open(path, "r", encoding="utf-8") as fh:
        return run(fh.read())
