"""AST node definitions for ShengSiong."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class Node:
    """Base class for all AST nodes."""


# -- expressions -----------------------------------------------------------
class Expr(Node):
    pass


@dataclass
class Literal(Expr):
    value: object


@dataclass
class ListLiteral(Expr):
    elements: list[Expr]


@dataclass
class Variable(Expr):
    name: str
    line: int = 0


@dataclass
class Assign(Expr):
    name: str
    value: Expr
    line: int = 0


@dataclass
class Unary(Expr):
    op: str
    right: Expr
    line: int = 0


@dataclass
class Binary(Expr):
    left: Expr
    op: str
    right: Expr
    line: int = 0


@dataclass
class Logical(Expr):
    left: Expr
    op: str
    right: Expr


@dataclass
class Call(Expr):
    callee: Expr
    args: list[Expr]
    line: int = 0


@dataclass
class Get(Expr):
    obj: Expr
    name: str
    line: int = 0


@dataclass
class Index(Expr):
    obj: Expr
    index: Expr
    line: int = 0


# -- statements ------------------------------------------------------------
class Stmt(Node):
    pass


@dataclass
class ExprStmt(Stmt):
    expr: Expr


@dataclass
class Let(Stmt):
    name: str
    value: Expr


@dataclass
class Print(Stmt):
    expr: Expr


@dataclass
class Block(Stmt):
    statements: list[Stmt]


@dataclass
class If(Stmt):
    condition: Expr
    then_branch: Block
    else_branch: Optional[Block]


@dataclass
class While(Stmt):
    condition: Expr
    body: Block


@dataclass
class Func(Stmt):
    name: str
    params: list[str]
    body: Block


@dataclass
class Return(Stmt):
    value: Optional[Expr]
    line: int = 0


# -- domain statements -----------------------------------------------------
@dataclass
class StoreDecl(Stmt):
    name: str
    props: dict[str, Expr] = field(default_factory=dict)


@dataclass
class ProductDecl(Stmt):
    name: str
    props: dict[str, Expr] = field(default_factory=dict)


@dataclass
class SupplierDecl(Stmt):
    name: str
    props: dict[str, Expr] = field(default_factory=dict)


@dataclass
class WarehouseDecl(Stmt):
    name: str
    props: dict[str, Expr] = field(default_factory=dict)


@dataclass
class TruckDecl(Stmt):
    name: str
    props: dict[str, Expr] = field(default_factory=dict)


@dataclass
class StockStmt(Stmt):
    """stock <qty> units of <product> at <store>"""

    quantity: Expr
    product: Expr
    store: Expr


@dataclass
class SellStmt(Stmt):
    """sell <qty> units of <product> at <store>"""

    quantity: Expr
    product: Expr
    store: Expr
    line: int = 0


@dataclass
class OrderStmt(Stmt):
    """order <qty> units of <product> from <supplier> to <warehouse>"""

    quantity: Expr
    product: Expr
    supplier: Expr
    destination: Expr
    line: int = 0


@dataclass
class PriceStmt(Stmt):
    """price <product> at <amount>"""

    product: Expr
    amount: Expr


@dataclass
class RestockRule(Stmt):
    """restock <product> at <store> when below <threshold> order <qty> from <supplier>"""

    product: Expr
    store: Expr
    threshold: Expr
    quantity: Expr
    supplier: Expr


@dataclass
class DeliverStmt(Stmt):
    """deliver <qty> units of <product> from <warehouse> to <store> [via <truck>]"""

    quantity: Expr
    product: Expr
    source: Expr
    store: Expr
    truck: Optional[Expr] = None
    line: int = 0


@dataclass
class ReportStmt(Stmt):
    """report <target>  (store/warehouse/all)"""

    target: Optional[Expr] = None
