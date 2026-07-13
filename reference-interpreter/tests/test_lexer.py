import math

import pytest

from shengsiong.lexer import Lexer, LexError, TokenType as T


def types(src):
    return [t.type for t in Lexer(src).tokenize()]


def test_empty_source_is_just_eof():
    toks = Lexer("").tokenize()
    assert len(toks) == 1
    assert toks[0].type == T.EOF


def test_whitespace_and_newlines_skipped():
    toks = Lexer("  \t\n\r  ").tokenize()
    assert [t.type for t in toks] == [T.EOF]


def test_line_and_col_tracking():
    toks = Lexer("a\nbb\nccc").tokenize()
    assert toks[0].line == 1 and toks[0].col == 1
    assert toks[1].line == 2 and toks[1].col == 1
    assert toks[2].line == 3 and toks[2].col == 1


def test_comment_to_end_of_line():
    toks = Lexer("let x = 1 # trailing comment\nprint x").tokenize()
    kinds = [t.type for t in toks]
    assert T.PRINT in kinds
    assert all(t.type != T.STRING for t in toks)


def test_comment_at_eof_without_newline():
    toks = Lexer("# only a comment").tokenize()
    assert [t.type for t in toks] == [T.EOF]


def test_integer_and_float_literals():
    toks = Lexer("42 3.14").tokenize()
    assert toks[0].literal == 42
    assert isinstance(toks[0].literal, int)
    assert math.isclose(toks[1].literal, 3.14)


def test_number_with_trailing_dot_is_not_float():
    # "5." -> NUMBER 5 then DOT, because digit does not follow the dot
    toks = Lexer("5.").tokenize()
    assert toks[0].type == T.NUMBER and toks[0].literal == 5
    assert toks[1].type == T.DOT


def test_string_with_escapes():
    toks = Lexer(r'"a\nb\tc\"d\\e\z"').tokenize()
    assert toks[0].type == T.STRING
    assert toks[0].literal == "a\nb\tc\"d\\ez"


def test_unterminated_string_raises():
    with pytest.raises(LexError):
        Lexer('"no closing quote').tokenize()


def test_unterminated_string_with_trailing_escape():
    with pytest.raises(LexError):
        Lexer('"abc\\').tokenize()


def test_all_operators():
    src = "= == != < > <= >= + - * / % ( ) { } [ ] , : ; ."
    kinds = types(src)
    expected = [
        T.ASSIGN, T.EQ, T.NEQ, T.LT, T.GT, T.LTE, T.GTE,
        T.PLUS, T.MINUS, T.STAR, T.SLASH, T.PERCENT,
        T.LPAREN, T.RPAREN, T.LBRACE, T.RBRACE, T.LBRACKET, T.RBRACKET,
        T.COMMA, T.COLON, T.SEMICOLON, T.DOT, T.EOF,
    ]
    assert kinds == expected


def test_bang_without_equals_raises():
    with pytest.raises(LexError):
        Lexer("!x").tokenize()


def test_unexpected_character_raises():
    with pytest.raises(LexError):
        Lexer("@").tokenize()


def test_keywords_recognised():
    src = ("store product supplier warehouse truck stock sell order from "
           "restock when below above deliver to price report let if else "
           "while func return print true false and or not units at")
    kinds = types(src)
    assert T.STORE in kinds and T.RESTOCK in kinds and T.UNITS in kinds
    assert T.ABOVE in kinds and T.AT in kinds
    assert kinds[-1] == T.EOF
    # none of these should have fallen through to IDENT
    assert T.IDENT not in kinds


def test_identifier_with_underscore_and_digits():
    toks = Lexer("my_store2").tokenize()
    assert toks[0].type == T.IDENT
    assert toks[0].lexeme == "my_store2"


def test_token_repr_smoke():
    tok = Lexer("42").tokenize()[0]
    assert "NUMBER" in repr(tok)
