import pytest

from shengsiong.lexer import Lexer
from shengsiong.parser import Parser, ParseError
from shengsiong import ast_nodes as A


def parse(src):
    return Parser(Lexer(src).tokenize()).parse()


def test_let_declaration():
    prog = parse("let x = 1 + 2")
    assert isinstance(prog[0], A.Let)
    assert prog[0].name == "x"
    assert isinstance(prog[0].value, A.Binary)


def test_let_requires_name():
    with pytest.raises(ParseError):
        parse("let = 1")


def test_let_requires_equals():
    with pytest.raises(ParseError):
        parse("let x 1")


def test_print_statement():
    prog = parse('print "hi"')
    assert isinstance(prog[0], A.Print)


def test_block_and_if_else():
    prog = parse("if (true) { print 1 } else { print 2 }")
    node = prog[0]
    assert isinstance(node, A.If)
    assert isinstance(node.then_branch, A.Block)
    assert node.else_branch is not None


def test_if_without_else():
    node = parse("if (1 < 2) { print 1 }")[0]
    assert node.else_branch is None


def test_while_loop():
    node = parse("while (x < 10) { x = x + 1 }")[0]
    assert isinstance(node, A.While)


def test_function_declaration_with_params():
    node = parse("func add(a, b) { return a + b }")[0]
    assert isinstance(node, A.Func)
    assert node.params == ["a", "b"]


def test_function_no_params():
    node = parse("func go() { return 1 }")[0]
    assert node.params == []


def test_return_without_value():
    node = parse("func f() { return }")[0]
    assert node.body.statements[0].value is None


def test_store_declaration_no_body():
    node = parse("store tampines")[0]
    assert isinstance(node, A.StoreDecl)
    assert node.props == {}


def test_entity_declaration_with_props():
    node = parse('product milk { price: 3.5, category: "dairy" }')[0]
    assert isinstance(node, A.ProductDecl)
    assert set(node.props.keys()) == {"price", "category"}


def test_all_entity_types():
    prog = parse("store s\nwarehouse w\nsupplier sup\ntruck t\nproduct p")
    kinds = [type(n).__name__ for n in prog]
    assert kinds == [
        "StoreDecl", "WarehouseDecl", "SupplierDecl", "TruckDecl", "ProductDecl",
    ]


def test_stock_statement():
    node = parse("stock 10 units of milk at tampines")[0]
    assert isinstance(node, A.StockStmt)


def test_stock_without_units_and_of_keyword():
    # 'units' and 'of' are optional sugar
    node = parse("stock 10 milk at tampines")[0]
    assert isinstance(node, A.StockStmt)


def test_sell_statement():
    node = parse("sell 5 units of milk at tampines")[0]
    assert isinstance(node, A.SellStmt)


def test_order_statement():
    node = parse("order 100 units of milk from acme to central")[0]
    assert isinstance(node, A.OrderStmt)


def test_price_statement():
    node = parse("price milk at 4.20")[0]
    assert isinstance(node, A.PriceStmt)


def test_restock_rule():
    node = parse("restock milk at tampines when below 20 order 50 units from acme")[0]
    assert isinstance(node, A.RestockRule)


def test_deliver_with_and_without_truck():
    a = parse("deliver 10 units of milk from central to tampines")[0]
    b = parse("deliver 10 units of milk from central to tampines via lorry")[0]
    assert a.truck is None
    assert isinstance(b.truck, A.Variable)


def test_report_all_and_targeted_and_bare():
    assert parse("report")[0].target is None
    assert isinstance(parse("report tampines")[0].target, A.Variable)
    assert isinstance(parse('report "central"')[0].target, A.Literal)


def test_expression_statement():
    node = parse("foo()")[0]
    assert isinstance(node, A.ExprStmt)


def test_bare_block_statement():
    # a `{ ... }` appearing as a statement is parsed as a Block.
    node = parse("{ print 1 }")[0]
    assert isinstance(node, A.Block)


def test_advance_at_eof_is_safe():
    # _consume at EOF calls _advance past the end without moving position.
    from shengsiong.lexer import Lexer as L
    p = Parser(L("").tokenize())
    before = p.pos
    p._advance()
    assert p.pos == before  # did not advance past EOF


def test_list_literal_and_indexing():
    node = parse("let x = [1, 2, 3]")[0]
    assert isinstance(node.value, A.ListLiteral)
    idx = parse("x[0]")[0]
    assert isinstance(idx.expr, A.Index)


def test_empty_list():
    node = parse("let x = []")[0]
    assert node.value.elements == []


def test_call_chain_and_get():
    node = parse("milk.price")[0]
    assert isinstance(node.expr, A.Get)


def test_assignment_expression():
    node = parse("x = 5")[0]
    assert isinstance(node.expr, A.Assign)


def test_invalid_assignment_target():
    with pytest.raises(ParseError):
        parse("1 = 2")


def test_logical_and_or():
    node = parse("a and b or c")[0]
    assert isinstance(node.expr, A.Logical)


def test_unary_operators():
    node = parse("not -x")[0]
    assert isinstance(node.expr, A.Unary)


def test_grouping():
    node = parse("(1 + 2) * 3")[0]
    assert isinstance(node.expr, A.Binary)
    assert node.expr.op == "*"


def test_comparison_and_equality_chain():
    node = parse("1 < 2 == true")[0]
    assert isinstance(node.expr, A.Binary)


def test_missing_expression_raises():
    with pytest.raises(ParseError):
        parse("let x = ")


def test_unclosed_paren_raises():
    with pytest.raises(ParseError):
        parse("(1 + 2")


def test_unclosed_block_raises():
    with pytest.raises(ParseError):
        parse("if (true) { print 1")


def test_entity_body_missing_colon_raises():
    with pytest.raises(ParseError):
        parse("product milk { price 3 }")


def test_function_param_must_be_ident():
    with pytest.raises(ParseError):
        parse("func f(1) { return }")


def test_unclosed_list_raises():
    with pytest.raises(ParseError):
        parse("let x = [1, 2")


def test_index_requires_bracket_close():
    with pytest.raises(ParseError):
        parse("x[0")


def test_get_requires_name():
    with pytest.raises(ParseError):
        parse("milk.")


def test_get_property_name_cannot_be_number():
    # '.' followed by a numeric token hits the property-name-token guard.
    with pytest.raises(ParseError):
        parse("milk.5")


def test_entity_property_key_cannot_be_number():
    # a numeric property key hits the entity property-name guard.
    with pytest.raises(ParseError):
        parse("product milk { 1: 3 }")
