"""Recursive-descent parser for ShengSiong."""

from __future__ import annotations

from . import ast_nodes as A
from .lexer import Token, TokenType as T


class ParseError(Exception):
    def __init__(self, message: str, token: Token):
        super().__init__(f"[line {token.line}:{token.col}] Parse error at {token.lexeme!r}: {message}")
        self.token = token


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    # -- token helpers -----------------------------------------------------
    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _previous(self) -> Token:
        return self.tokens[self.pos - 1]

    def _at_end(self) -> bool:
        return self._peek().type == T.EOF

    def _check(self, ttype: T) -> bool:
        return not self._at_end() and self._peek().type == ttype

    def _advance(self) -> Token:
        if not self._at_end():
            self.pos += 1
        return self._previous()

    def _match(self, *types: T) -> bool:
        for tt in types:
            if self._check(tt):
                self._advance()
                return True
        return False

    def _consume(self, ttype: T, message: str) -> Token:
        if self._check(ttype):
            return self._advance()
        raise ParseError(message, self._peek())

    # -- entry -------------------------------------------------------------
    def parse(self) -> list[A.Stmt]:
        statements: list[A.Stmt] = []
        while not self._at_end():
            statements.append(self._declaration())
        return statements

    # -- declarations / statements ----------------------------------------
    def _declaration(self) -> A.Stmt:
        if self._match(T.LET):
            return self._let_decl()
        if self._match(T.FUNC):
            return self._func_decl()
        if self._match(T.STORE):
            return self._entity_decl(A.StoreDecl)
        if self._match(T.PRODUCT):
            return self._entity_decl(A.ProductDecl)
        if self._match(T.SUPPLIER):
            return self._entity_decl(A.SupplierDecl)
        if self._match(T.WAREHOUSE):
            return self._entity_decl(A.WarehouseDecl)
        if self._match(T.TRUCK):
            return self._entity_decl(A.TruckDecl)
        return self._statement()

    def _let_decl(self) -> A.Stmt:
        name = self._consume(T.IDENT, "expected variable name after 'let'").lexeme
        self._consume(T.ASSIGN, "expected '=' in let declaration")
        value = self._expression()
        self._match(T.SEMICOLON)
        return A.Let(name, value)

    def _func_decl(self) -> A.Stmt:
        name = self._consume(T.IDENT, "expected function name").lexeme
        self._consume(T.LPAREN, "expected '(' after function name")
        params: list[str] = []
        if not self._check(T.RPAREN):
            params.append(self._consume(T.IDENT, "expected parameter name").lexeme)
            while self._match(T.COMMA):
                params.append(self._consume(T.IDENT, "expected parameter name").lexeme)
        self._consume(T.RPAREN, "expected ')' after parameters")
        body = self._block()
        return A.Func(name, params, body)

    def _entity_decl(self, cls) -> A.Stmt:
        name = self._consume(T.IDENT, "expected entity name").lexeme
        props: dict[str, A.Expr] = {}
        if self._match(T.LBRACE):
            while not self._check(T.RBRACE) and not self._at_end():
                key = self._property_name()
                self._consume(T.COLON, "expected ':' after property name")
                props[key] = self._expression()
                self._match(T.COMMA)
            self._consume(T.RBRACE, "expected '}' to close entity body")
        else:
            self._match(T.SEMICOLON)
        return cls(name, props)

    def _property_name_token(self) -> Token:
        tok = self._peek()
        if tok.lexeme and (tok.lexeme[0].isalpha() or tok.lexeme[0] == "_") and tok.lexeme.replace("_", "").isalnum():
            return self._advance()
        raise ParseError("expected property name after '.'", tok)

    def _property_name(self) -> str:
        tok = self._peek()
        if tok.lexeme and (tok.lexeme[0].isalpha() or tok.lexeme[0] == "_") and tok.lexeme.replace("_", "").isalnum():
            self._advance()
            return tok.lexeme
        raise ParseError("expected property name", tok)

    def _statement(self) -> A.Stmt:
        if self._match(T.PRINT):
            expr = self._expression()
            self._match(T.SEMICOLON)
            return A.Print(expr)
        if self._match(T.IF):
            return self._if_stmt()
        if self._match(T.WHILE):
            return self._while_stmt()
        if self._match(T.RETURN):
            return self._return_stmt()
        if self._check(T.LBRACE):
            return self._block()
        if self._match(T.STOCK):
            return self._stock_stmt()
        if self._match(T.SELL):
            return self._sell_stmt()
        if self._match(T.ORDER):
            return self._order_stmt()
        if self._match(T.PRICE):
            return self._price_stmt()
        if self._match(T.RESTOCK):
            return self._restock_stmt()
        if self._match(T.DELIVER):
            return self._deliver_stmt()
        if self._match(T.REPORT):
            return self._report_stmt()
        return self._expr_stmt()

    def _if_stmt(self) -> A.Stmt:
        self._consume(T.LPAREN, "expected '(' after 'if'")
        condition = self._expression()
        self._consume(T.RPAREN, "expected ')' after condition")
        then_branch = self._block()
        else_branch = None
        if self._match(T.ELSE):
            else_branch = self._block()
        return A.If(condition, then_branch, else_branch)

    def _while_stmt(self) -> A.Stmt:
        self._consume(T.LPAREN, "expected '(' after 'while'")
        condition = self._expression()
        self._consume(T.RPAREN, "expected ')' after condition")
        body = self._block()
        return A.While(condition, body)

    def _return_stmt(self) -> A.Stmt:
        line = self._previous().line
        value = None
        if not self._check(T.SEMICOLON) and not self._check(T.RBRACE):
            value = self._expression()
        self._match(T.SEMICOLON)
        return A.Return(value, line)

    def _block(self) -> A.Block:
        self._consume(T.LBRACE, "expected '{'")
        statements: list[A.Stmt] = []
        while not self._check(T.RBRACE) and not self._at_end():
            statements.append(self._declaration())
        self._consume(T.RBRACE, "expected '}'")
        return A.Block(statements)

    def _expr_stmt(self) -> A.Stmt:
        expr = self._expression()
        self._match(T.SEMICOLON)
        return A.ExprStmt(expr)

    # -- domain statements -------------------------------------------------
    def _qty_of_product(self):
        line = self._previous().line
        quantity = self._expression()
        self._match(T.UNITS)
        self._consume_kw_of()
        product = self._expression()
        return line, quantity, product

    def _consume_kw_of(self):
        # 'of' is not a keyword; accept identifier 'of' or skip if absent
        if self._check(T.IDENT) and self._peek().lexeme == "of":
            self._advance()

    def _stock_stmt(self) -> A.Stmt:
        _, quantity, product = self._qty_of_product()
        self._consume(T.AT, "expected 'at <store>' in stock statement")
        store = self._expression()
        self._match(T.SEMICOLON)
        return A.StockStmt(quantity, product, store)

    def _sell_stmt(self) -> A.Stmt:
        line, quantity, product = self._qty_of_product()
        self._consume(T.AT, "expected 'at <store>' in sell statement")
        store = self._expression()
        self._match(T.SEMICOLON)
        return A.SellStmt(quantity, product, store, line)

    def _order_stmt(self) -> A.Stmt:
        line, quantity, product = self._qty_of_product()
        self._consume(T.FROM, "expected 'from <supplier>' in order statement")
        supplier = self._expression()
        self._consume(T.TO, "expected 'to <destination>' in order statement")
        destination = self._expression()
        self._match(T.SEMICOLON)
        return A.OrderStmt(quantity, product, supplier, destination, line)

    def _price_stmt(self) -> A.Stmt:
        product = self._expression()
        self._consume(T.AT, "expected 'at <amount>' in price statement")
        amount = self._expression()
        self._match(T.SEMICOLON)
        return A.PriceStmt(product, amount)

    def _restock_stmt(self) -> A.Stmt:
        product = self._expression()
        self._consume(T.AT, "expected 'at <store>' in restock rule")
        store = self._expression()
        self._consume(T.WHEN, "expected 'when below <n>' in restock rule")
        self._consume(T.BELOW, "expected 'below' in restock rule")
        threshold = self._expression()
        self._consume(T.ORDER, "expected 'order <qty>' in restock rule")
        quantity = self._expression()
        self._match(T.UNITS)
        self._consume(T.FROM, "expected 'from <supplier>' in restock rule")
        supplier = self._expression()
        self._match(T.SEMICOLON)
        return A.RestockRule(product, store, threshold, quantity, supplier)

    def _deliver_stmt(self) -> A.Stmt:
        line, quantity, product = self._qty_of_product()
        self._consume(T.FROM, "expected 'from <source>' in deliver statement")
        source = self._expression()
        self._consume(T.TO, "expected 'to <store>' in deliver statement")
        store = self._expression()
        truck = None
        if self._check(T.IDENT) and self._peek().lexeme == "via":
            self._advance()
            truck = self._expression()
        self._match(T.SEMICOLON)
        return A.DeliverStmt(quantity, product, source, store, truck, line)

    def _report_stmt(self) -> A.Stmt:
        target = None
        if not self._check(T.SEMICOLON) and not self._at_end() and self._peek().type in (T.IDENT, T.STRING):
            target = self._expression()
        self._match(T.SEMICOLON)
        return A.ReportStmt(target)

    # -- expressions -------------------------------------------------------
    def _expression(self) -> A.Expr:
        return self._assignment()

    def _assignment(self) -> A.Expr:
        expr = self._logic_or()
        if self._match(T.ASSIGN):
            value = self._assignment()
            if isinstance(expr, A.Variable):
                return A.Assign(expr.name, value, expr.line)
            raise ParseError("invalid assignment target", self._previous())
        return expr

    def _logic_or(self) -> A.Expr:
        expr = self._logic_and()
        while self._match(T.OR):
            expr = A.Logical(expr, "or", self._logic_and())
        return expr

    def _logic_and(self) -> A.Expr:
        expr = self._equality()
        while self._match(T.AND):
            expr = A.Logical(expr, "and", self._equality())
        return expr

    def _equality(self) -> A.Expr:
        expr = self._comparison()
        while self._match(T.EQ, T.NEQ):
            op = self._previous()
            expr = A.Binary(expr, op.lexeme, self._comparison(), op.line)
        return expr

    def _comparison(self) -> A.Expr:
        expr = self._term()
        while self._match(T.LT, T.GT, T.LTE, T.GTE):
            op = self._previous()
            expr = A.Binary(expr, op.lexeme, self._term(), op.line)
        return expr

    def _term(self) -> A.Expr:
        expr = self._factor()
        while self._match(T.PLUS, T.MINUS):
            op = self._previous()
            expr = A.Binary(expr, op.lexeme, self._factor(), op.line)
        return expr

    def _factor(self) -> A.Expr:
        expr = self._unary()
        while self._match(T.STAR, T.SLASH, T.PERCENT):
            op = self._previous()
            expr = A.Binary(expr, op.lexeme, self._unary(), op.line)
        return expr

    def _unary(self) -> A.Expr:
        if self._match(T.NOT, T.MINUS):
            op = self._previous()
            return A.Unary(op.lexeme, self._unary(), op.line)
        return self._call()

    def _call(self) -> A.Expr:
        expr = self._primary()
        while True:
            if self._match(T.LPAREN):
                expr = self._finish_call(expr)
            elif self._match(T.DOT):
                name = self._property_name_token()
                expr = A.Get(expr, name.lexeme, name.line)
            elif self._match(T.LBRACKET):
                index = self._expression()
                self._consume(T.RBRACKET, "expected ']' after index")
                expr = A.Index(expr, index, self._previous().line)
            else:
                break
        return expr

    def _finish_call(self, callee: A.Expr) -> A.Expr:
        line = self._previous().line
        args: list[A.Expr] = []
        if not self._check(T.RPAREN):
            args.append(self._expression())
            while self._match(T.COMMA):
                args.append(self._expression())
        self._consume(T.RPAREN, "expected ')' after arguments")
        return A.Call(callee, args, line)

    def _primary(self) -> A.Expr:
        if self._match(T.TRUE):
            return A.Literal(True)
        if self._match(T.FALSE):
            return A.Literal(False)
        if self._match(T.NUMBER, T.STRING):
            return A.Literal(self._previous().literal)
        if self._match(T.IDENT):
            tok = self._previous()
            return A.Variable(tok.lexeme, tok.line)
        if self._match(T.LPAREN):
            expr = self._expression()
            self._consume(T.RPAREN, "expected ')' after expression")
            return expr
        if self._match(T.LBRACKET):
            elements: list[A.Expr] = []
            if not self._check(T.RBRACKET):
                elements.append(self._expression())
                while self._match(T.COMMA):
                    elements.append(self._expression())
            self._consume(T.RBRACKET, "expected ']' after list")
            return A.ListLiteral(elements)
        raise ParseError("expected expression", self._peek())
