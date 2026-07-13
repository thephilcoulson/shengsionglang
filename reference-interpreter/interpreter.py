"""Tree-walking interpreter for ShengSiong."""

from __future__ import annotations

from . import ast_nodes as A
from .runtime import Supermarket, SupermarketError


class RuntimeErrorSS(Exception):
    def __init__(self, message: str, line: int = 0):
        prefix = f"[line {line}] " if line else ""
        super().__init__(f"{prefix}Runtime error: {message}")
        self.line = line


class _Return(Exception):
    def __init__(self, value):
        self.value = value


class Environment:
    def __init__(self, parent: "Environment | None" = None):
        self.values: dict[str, object] = {}
        self.parent = parent

    def define(self, name: str, value: object) -> None:
        self.values[name] = value

    def get(self, name: str, line: int = 0) -> object:
        if name in self.values:
            return self.values[name]
        if self.parent is not None:
            return self.parent.get(name, line)
        raise RuntimeErrorSS(f"undefined variable {name!r}", line)

    def assign(self, name: str, value: object, line: int = 0) -> None:
        if name in self.values:
            self.values[name] = value
            return
        if self.parent is not None:
            self.parent.assign(name, value, line)
            return
        raise RuntimeErrorSS(f"assignment to undefined variable {name!r}", line)


class SSFunction:
    def __init__(self, decl: A.Func, closure: Environment):
        self.decl = decl
        self.closure = closure

    def call(self, interp: "Interpreter", args: list) -> object:
        if len(args) != len(self.decl.params):
            raise RuntimeErrorSS(
                f"{self.decl.name!r} expects {len(self.decl.params)} args, got {len(args)}"
            )
        env = Environment(self.closure)
        for name, val in zip(self.decl.params, args):
            env.define(name, val)
        try:
            interp._execute_block(self.decl.body.statements, env)
        except _Return as r:
            return r.value
        return None


class NativeFunction:
    def __init__(self, name, arity_min, arity_max, fn):
        self.name = name
        self.arity_min = arity_min
        self.arity_max = arity_max
        self.fn = fn

    def call(self, interp, args):
        n = len(args)
        if n < self.arity_min or (self.arity_max is not None and n > self.arity_max):
            raise RuntimeErrorSS(f"{self.name!r} got {n} args")
        return self.fn(*args)


class Interpreter:
    MAX_LOOP_ITERATIONS = 1_000_000

    def __init__(self, market: Supermarket | None = None):
        self.market = market or Supermarket()
        self.globals = Environment()
        self.env = self.globals
        self.output: list[str] = []
        self._install_builtins()

    def _install_builtins(self) -> None:
        def _len(x):
            try:
                return len(x)
            except TypeError:
                raise RuntimeErrorSS("len() expects a string or list")

        def _str(x):
            return self._stringify(x)

        def _num(x):
            try:
                f = float(x)
            except (TypeError, ValueError):
                raise RuntimeErrorSS(f"cannot convert {x!r} to number")
            return int(f) if f.is_integer() else f

        def _min(*xs):
            return min(xs)

        def _max(*xs):
            return max(xs)

        def _abs(x):
            return abs(x)

        builtins = {
            "len": NativeFunction("len", 1, 1, _len),
            "str": NativeFunction("str", 1, 1, _str),
            "num": NativeFunction("num", 1, 1, _num),
            "min": NativeFunction("min", 1, None, _min),
            "max": NativeFunction("max", 1, None, _max),
            "abs": NativeFunction("abs", 1, 1, _abs),
            "inventory": NativeFunction(
                "inventory", 2, 2,
                lambda product, loc: self.market.location(loc).qty(product),
            ),
            "revenue": NativeFunction("revenue", 0, 0, lambda: self.market.revenue),
        }
        for name, fn in builtins.items():
            self.globals.define(name, fn)

    # -- public entry ------------------------------------------------------
    def interpret(self, statements: list[A.Stmt]) -> None:
        for stmt in statements:
            self._execute(stmt)

    # -- execution ---------------------------------------------------------
    def _execute(self, stmt: A.Stmt) -> None:
        method = getattr(self, "_exec_" + type(stmt).__name__)
        method(stmt)

    def _execute_block(self, statements: list[A.Stmt], env: Environment) -> None:
        previous = self.env
        self.env = env
        try:
            for stmt in statements:
                self._execute(stmt)
        finally:
            self.env = previous

    # -- statement executors ----------------------------------------------
    def _exec_ExprStmt(self, stmt: A.ExprStmt) -> None:
        self._evaluate(stmt.expr)

    def _exec_Let(self, stmt: A.Let) -> None:
        self.env.define(stmt.name, self._evaluate(stmt.value))

    def _exec_Print(self, stmt: A.Print) -> None:
        value = self._evaluate(stmt.expr)
        self.output.append(self._stringify(value))

    def _exec_Block(self, stmt: A.Block) -> None:
        self._execute_block(stmt.statements, Environment(self.env))

    def _exec_If(self, stmt: A.If) -> None:
        if self._truthy(self._evaluate(stmt.condition)):
            self._exec_Block(stmt.then_branch)
        elif stmt.else_branch is not None:
            self._exec_Block(stmt.else_branch)

    def _exec_While(self, stmt: A.While) -> None:
        guard = 0
        while self._truthy(self._evaluate(stmt.condition)):
            self._exec_Block(stmt.body)
            guard += 1
            if guard > self.MAX_LOOP_ITERATIONS:
                raise RuntimeErrorSS(
                    f"while loop exceeded {self.MAX_LOOP_ITERATIONS:,} iterations"
                )

    def _exec_Func(self, stmt: A.Func) -> None:
        self.env.define(stmt.name, SSFunction(stmt, self.env))

    def _exec_Return(self, stmt: A.Return) -> None:
        value = self._evaluate(stmt.value) if stmt.value is not None else None
        raise _Return(value)

    # -- domain declarations ----------------------------------------------
    def _props(self, decl) -> dict:
        return {k: self._evaluate(v) for k, v in decl.props.items()}

    def _exec_StoreDecl(self, stmt: A.StoreDecl) -> None:
        self.market.add_store(stmt.name, **self._props(stmt))
        self.env.define(stmt.name, stmt.name)

    def _exec_WarehouseDecl(self, stmt: A.WarehouseDecl) -> None:
        self.market.add_warehouse(stmt.name, **self._props(stmt))
        self.env.define(stmt.name, stmt.name)

    def _exec_ProductDecl(self, stmt: A.ProductDecl) -> None:
        p = self._props(stmt)
        self.market.add_product(
            stmt.name,
            price=p.get("price", 0.0),
            category=p.get("category", "general"),
        )
        self.env.define(stmt.name, stmt.name)

    def _exec_SupplierDecl(self, stmt: A.SupplierDecl) -> None:
        p = self._props(stmt)
        self.market.add_supplier(
            stmt.name,
            lead_time=p.get("lead_time", 1),
            reliability=p.get("reliability", 1.0),
        )
        self.env.define(stmt.name, stmt.name)

    def _exec_TruckDecl(self, stmt: A.TruckDecl) -> None:
        p = self._props(stmt)
        self.market.add_truck(stmt.name, capacity=p.get("capacity", 1000))
        self.env.define(stmt.name, stmt.name)

    # -- domain operations -------------------------------------------------
    def _name_of(self, expr) -> str:
        val = self._evaluate(expr)
        if not isinstance(val, str):
            raise RuntimeErrorSS(f"expected an entity name, got {self._stringify(val)}")
        return val

    def _int_of(self, expr) -> int:
        val = self._evaluate(expr)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise RuntimeErrorSS(f"expected a number, got {self._stringify(val)}")
        if isinstance(val, float) and not val.is_integer():
            raise RuntimeErrorSS(f"expected a whole number of units, got {val}")
        return int(val)

    def _guard(self, fn, line=0):
        try:
            return fn()
        except SupermarketError as e:
            raise RuntimeErrorSS(str(e), line)

    def _exec_StockStmt(self, stmt: A.StockStmt) -> None:
        qty = self._int_of(stmt.quantity)
        product = self._name_of(stmt.product)
        store = self._name_of(stmt.store)
        self._guard(lambda: self.market.stock(product, store, qty))

    def _exec_SellStmt(self, stmt: A.SellStmt) -> None:
        qty = self._int_of(stmt.quantity)
        product = self._name_of(stmt.product)
        store = self._name_of(stmt.store)
        self._guard(lambda: self.market.sell(product, store, qty), stmt.line)

    def _exec_OrderStmt(self, stmt: A.OrderStmt) -> None:
        qty = self._int_of(stmt.quantity)
        product = self._name_of(stmt.product)
        supplier = self._name_of(stmt.supplier)
        dest = self._name_of(stmt.destination)
        self._guard(lambda: self.market.order(product, supplier, dest, qty), stmt.line)

    def _exec_PriceStmt(self, stmt: A.PriceStmt) -> None:
        product = self._name_of(stmt.product)
        amount = self._evaluate(stmt.amount)
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise RuntimeErrorSS("price must be a number")
        self._guard(lambda: self.market.set_price(product, amount))

    def _exec_RestockRule(self, stmt: A.RestockRule) -> None:
        product = self._name_of(stmt.product)
        store = self._name_of(stmt.store)
        threshold = self._int_of(stmt.threshold)
        qty = self._int_of(stmt.quantity)
        supplier = self._name_of(stmt.supplier)
        self._guard(lambda: self.market.add_restock_rule(product, store, threshold, qty, supplier))

    def _exec_DeliverStmt(self, stmt: A.DeliverStmt) -> None:
        qty = self._int_of(stmt.quantity)
        product = self._name_of(stmt.product)
        source = self._name_of(stmt.source)
        store = self._name_of(stmt.store)
        truck = self._name_of(stmt.truck) if stmt.truck is not None else None
        self._guard(lambda: self.market.deliver(product, source, store, qty, truck), stmt.line)

    def _exec_ReportStmt(self, stmt: A.ReportStmt) -> None:
        target = self._name_of(stmt.target) if stmt.target is not None else None
        text = self._guard(lambda: self.market.report(target))
        self.output.append(text)

    # -- expression evaluation --------------------------------------------
    def _evaluate(self, expr: A.Expr):
        method = getattr(self, "_eval_" + type(expr).__name__)
        return method(expr)

    def _eval_Literal(self, expr: A.Literal):
        return expr.value

    def _eval_ListLiteral(self, expr: A.ListLiteral):
        return [self._evaluate(e) for e in expr.elements]

    def _eval_Variable(self, expr: A.Variable):
        return self.env.get(expr.name, expr.line)

    def _eval_Assign(self, expr: A.Assign):
        value = self._evaluate(expr.value)
        self.env.assign(expr.name, value, expr.line)
        return value

    def _eval_Unary(self, expr: A.Unary):
        right = self._evaluate(expr.right)
        if expr.op == "-":
            if isinstance(right, bool) or not isinstance(right, (int, float)):
                raise RuntimeErrorSS("unary '-' expects a number", expr.line)
            return -right
        if expr.op == "not":
            return not self._truthy(right)
        raise RuntimeErrorSS(f"unknown unary op {expr.op!r}", expr.line)  # pragma: no cover

    def _eval_Logical(self, expr: A.Logical):
        left = self._evaluate(expr.left)
        if expr.op == "or":
            return left if self._truthy(left) else self._evaluate(expr.right)
        return self._evaluate(expr.right) if self._truthy(left) else left

    def _eval_Binary(self, expr: A.Binary):
        left = self._evaluate(expr.left)
        right = self._evaluate(expr.right)
        op = expr.op
        if op == "+":
            if isinstance(left, str) or isinstance(right, str):
                return self._stringify(left) + self._stringify(right)
            self._check_nums(left, right, op, expr.line)
            return left + right
        if op == "-":
            self._check_nums(left, right, op, expr.line)
            return left - right
        if op == "*":
            self._check_nums(left, right, op, expr.line)
            return left * right
        if op == "/":
            self._check_nums(left, right, op, expr.line)
            if right == 0:
                raise RuntimeErrorSS("division by zero", expr.line)
            result = left / right
            return int(result) if isinstance(left, int) and isinstance(right, int) and result.is_integer() else result
        if op == "%":
            self._check_nums(left, right, op, expr.line)
            if right == 0:
                raise RuntimeErrorSS("modulo by zero", expr.line)
            return left % right
        if op == "==":
            return self._equal(left, right)
        if op == "!=":
            return not self._equal(left, right)
        if op in ("<", ">", "<=", ">="):
            self._check_nums(left, right, op, expr.line)
            return {
                "<": left < right,
                ">": left > right,
                "<=": left <= right,
                ">=": left >= right,
            }[op]
        raise RuntimeErrorSS(f"unknown binary op {op!r}", expr.line)  # pragma: no cover

    def _eval_Call(self, expr: A.Call):
        callee = self._evaluate(expr.callee)
        args = [self._evaluate(a) for a in expr.args]
        if isinstance(callee, (SSFunction, NativeFunction)):
            return callee.call(self, args)
        raise RuntimeErrorSS(f"can only call functions, not {self._stringify(callee)}", expr.line)

    def _eval_Get(self, expr: A.Get):
        obj = self._evaluate(expr.obj)
        name = expr.name
        if isinstance(obj, str):
            # entity attribute access, e.g. milk.price, tampines.stock
            m = self.market
            if obj in m.products and name in ("price", "category", "name"):
                return getattr(m.products[obj], name)
            if obj in m.suppliers and name in ("lead_time", "reliability", "name"):
                return getattr(m.suppliers[obj], name)
            if obj in m.trucks and name in ("capacity", "deliveries", "name"):
                return getattr(m.trucks[obj], name)
            if (obj in m.stores or obj in m.warehouses) and name == "name":
                return obj
        raise RuntimeErrorSS(f"cannot read property {name!r} of {self._stringify(obj)}", expr.line)

    def _eval_Index(self, expr: A.Index):
        obj = self._evaluate(expr.obj)
        index = self._evaluate(expr.index)
        if isinstance(obj, list):
            if isinstance(index, bool) or not isinstance(index, int):
                raise RuntimeErrorSS("list index must be an integer", expr.line)
            if index < 0 or index >= len(obj):
                raise RuntimeErrorSS(f"list index {index} out of range", expr.line)
            return obj[index]
        if isinstance(obj, str):
            if isinstance(index, bool) or not isinstance(index, int):
                raise RuntimeErrorSS("string index must be an integer", expr.line)
            if index < 0 or index >= len(obj):
                raise RuntimeErrorSS(f"string index {index} out of range", expr.line)
            return obj[index]
        raise RuntimeErrorSS("only lists and strings can be indexed", expr.line)

    # -- helpers -----------------------------------------------------------
    def _check_nums(self, left, right, op, line):
        for v in (left, right):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise RuntimeErrorSS(f"operator {op!r} expects numbers", line)

    def _truthy(self, value) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return len(value) > 0
        if isinstance(value, list):
            return len(value) > 0
        return True

    def _equal(self, a, b) -> bool:
        if isinstance(a, bool) != isinstance(b, bool):
            return False
        return a == b

    def _stringify(self, value) -> str:
        if value is None:
            return "nil"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, float):
            if value.is_integer():
                return str(int(value))
            # Trim IEEE-754 noise for human/money-friendly output while keeping
            # meaningful precision.
            return f"{value:.10g}"
        if isinstance(value, list):
            return "[" + ", ".join(self._stringify(v) for v in value) + "]"
        if isinstance(value, (SSFunction,)):
            return f"<func {value.decl.name}>"
        if isinstance(value, (NativeFunction,)):
            return f"<native {value.name}>"
        return str(value)
