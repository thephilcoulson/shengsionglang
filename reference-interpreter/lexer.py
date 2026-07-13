"""Lexer for the ShengSiong language."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class LexError(Exception):
    """Raised when the source contains an invalid token."""

    def __init__(self, message: str, line: int, col: int):
        super().__init__(f"[line {line}:{col}] Lex error: {message}")
        self.line = line
        self.col = col


class TokenType(Enum):
    # literals
    NUMBER = auto()
    STRING = auto()
    IDENT = auto()
    # keywords
    STORE = auto()
    PRODUCT = auto()
    SUPPLIER = auto()
    WAREHOUSE = auto()
    TRUCK = auto()
    STOCK = auto()
    SELL = auto()
    ORDER = auto()
    FROM = auto()
    RESTOCK = auto()
    WHEN = auto()
    BELOW = auto()
    ABOVE = auto()
    DELIVER = auto()
    TO = auto()
    PRICE = auto()
    REPORT = auto()
    LET = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FUNC = auto()
    RETURN = auto()
    PRINT = auto()
    TRUE = auto()
    FALSE = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    UNITS = auto()
    AT = auto()
    # symbols
    LBRACE = auto()
    RBRACE = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    COLON = auto()
    SEMICOLON = auto()
    DOT = auto()
    ASSIGN = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQ = auto()
    NEQ = auto()
    LT = auto()
    GT = auto()
    LTE = auto()
    GTE = auto()
    EOF = auto()


KEYWORDS = {
    "store": TokenType.STORE,
    "product": TokenType.PRODUCT,
    "supplier": TokenType.SUPPLIER,
    "warehouse": TokenType.WAREHOUSE,
    "truck": TokenType.TRUCK,
    "stock": TokenType.STOCK,
    "sell": TokenType.SELL,
    "order": TokenType.ORDER,
    "from": TokenType.FROM,
    "restock": TokenType.RESTOCK,
    "when": TokenType.WHEN,
    "below": TokenType.BELOW,
    "above": TokenType.ABOVE,
    "deliver": TokenType.DELIVER,
    "to": TokenType.TO,
    "price": TokenType.PRICE,
    "report": TokenType.REPORT,
    "let": TokenType.LET,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "func": TokenType.FUNC,
    "return": TokenType.RETURN,
    "print": TokenType.PRINT,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "and": TokenType.AND,
    "or": TokenType.OR,
    "not": TokenType.NOT,
    "units": TokenType.UNITS,
    "at": TokenType.AT,
}


@dataclass(frozen=True)
class Token:
    type: TokenType
    lexeme: str
    literal: object
    line: int
    col: int

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Token({self.type.name}, {self.lexeme!r}, {self.literal!r}, {self.line}:{self.col})"


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.tokens: list[Token] = []
        self.start = 0
        self.current = 0
        self.line = 1
        self.col = 1
        self.token_start_col = 1

    def tokenize(self) -> list[Token]:
        while not self._at_end():
            self.start = self.current
            self.token_start_col = self.col
            self._scan_token()
        self.tokens.append(Token(TokenType.EOF, "", None, self.line, self.col))
        return self.tokens

    # -- helpers -----------------------------------------------------------
    def _at_end(self) -> bool:
        return self.current >= len(self.source)

    def _advance(self) -> str:
        ch = self.source[self.current]
        self.current += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _peek(self) -> str:
        if self._at_end():
            return "\0"
        return self.source[self.current]

    def _peek_next(self) -> str:
        if self.current + 1 >= len(self.source):
            return "\0"
        return self.source[self.current + 1]

    def _match(self, expected: str) -> bool:
        if self._at_end() or self.source[self.current] != expected:
            return False
        self._advance()
        return True

    def _add(self, ttype: TokenType, literal: object = None) -> None:
        text = self.source[self.start : self.current]
        self.tokens.append(Token(ttype, text, literal, self.line, self.token_start_col))

    # -- scanning ----------------------------------------------------------
    def _scan_token(self) -> None:
        ch = self._advance()
        if ch in " \t\r\n":
            return
        if ch == "#":  # line comment
            while not self._at_end() and self._peek() != "\n":
                self._advance()
            return
        simple = {
            "{": TokenType.LBRACE,
            "}": TokenType.RBRACE,
            "(": TokenType.LPAREN,
            ")": TokenType.RPAREN,
            "[": TokenType.LBRACKET,
            "]": TokenType.RBRACKET,
            ",": TokenType.COMMA,
            ":": TokenType.COLON,
            ";": TokenType.SEMICOLON,
            ".": TokenType.DOT,
            "+": TokenType.PLUS,
            "-": TokenType.MINUS,
            "*": TokenType.STAR,
            "%": TokenType.PERCENT,
        }
        if ch in simple:
            self._add(simple[ch])
            return
        if ch == "/":
            self._add(TokenType.SLASH)
            return
        if ch == "=":
            self._add(TokenType.EQ if self._match("=") else TokenType.ASSIGN)
            return
        if ch == "!":
            if self._match("="):
                self._add(TokenType.NEQ)
                return
            raise LexError("unexpected '!'", self.line, self.col)
        if ch == "<":
            self._add(TokenType.LTE if self._match("=") else TokenType.LT)
            return
        if ch == ">":
            self._add(TokenType.GTE if self._match("=") else TokenType.GT)
            return
        if ch == '"':
            self._string()
            return
        if ch.isdigit():
            self._number()
            return
        if ch.isalpha() or ch == "_":
            self._identifier()
            return
        raise LexError(f"unexpected character {ch!r}", self.line, self.col)

    def _string(self) -> None:
        chars: list[str] = []
        while not self._at_end() and self._peek() != '"':
            c = self._advance()
            if c == "\\":
                if self._at_end():
                    break
                nxt = self._advance()
                chars.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, nxt))
            else:
                chars.append(c)
        if self._at_end():
            raise LexError("unterminated string", self.line, self.col)
        self._advance()  # closing quote
        self._add(TokenType.STRING, "".join(chars))

    def _number(self) -> None:
        while self._peek().isdigit():
            self._advance()
        if self._peek() == "." and self._peek_next().isdigit():
            self._advance()
            while self._peek().isdigit():
                self._advance()
        text = self.source[self.start : self.current]
        value = float(text) if "." in text else int(text)
        self._add(TokenType.NUMBER, value)

    def _identifier(self) -> None:
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        text = self.source[self.start : self.current]
        ttype = KEYWORDS.get(text, TokenType.IDENT)
        self._add(ttype)
