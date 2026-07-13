"""Runtime domain model for ShengSiong -- the supermarket abstraction layer.

This module hides the bookkeeping of inventory, ordering, warehousing and
delivery behind a small set of objects. The interpreter drives these; user
programs never touch them directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class SupermarketError(Exception):
    """Domain-level error (e.g. selling stock that isn't there)."""


@dataclass
class Product:
    name: str
    price: float = 0.0
    category: str = "general"

    def as_dict(self) -> dict:
        return {"name": self.name, "price": self.price, "category": self.category}


@dataclass
class Supplier:
    name: str
    lead_time: int = 1  # days
    reliability: float = 1.0

    def as_dict(self) -> dict:
        return {"name": self.name, "lead_time": self.lead_time, "reliability": self.reliability}


@dataclass
class Location:
    """Base for stores and warehouses -- anything that holds inventory."""

    name: str
    kind: str = "store"
    inventory: dict[str, int] = field(default_factory=dict)

    def qty(self, product: str) -> int:
        return self.inventory.get(product, 0)

    def add(self, product: str, amount: int) -> None:
        if amount < 0:
            raise SupermarketError("cannot add a negative quantity")
        self.inventory[product] = self.qty(product) + amount

    def remove(self, product: str, amount: int) -> None:
        if amount < 0:
            raise SupermarketError("cannot remove a negative quantity")
        have = self.qty(product)
        if amount > have:
            raise SupermarketError(
                f"insufficient stock of {product!r} at {self.name!r}: "
                f"have {have}, need {amount}"
            )
        self.inventory[product] = have - amount


@dataclass
class Truck:
    name: str
    capacity: int = 1000
    deliveries: int = 0

    def as_dict(self) -> dict:
        return {"name": self.name, "capacity": self.capacity, "deliveries": self.deliveries}


@dataclass
class RestockRuleObj:
    product: str
    store: str
    threshold: int
    quantity: int
    supplier: str


class Supermarket:
    """The world. Holds every entity and the transaction ledger."""

    def __init__(self):
        self.stores: dict[str, Location] = {}
        self.warehouses: dict[str, Location] = {}
        self.products: dict[str, Product] = {}
        self.suppliers: dict[str, Supplier] = {}
        self.trucks: dict[str, Truck] = {}
        self.restock_rules: list[RestockRuleObj] = []
        self.ledger: list[dict] = []
        self.revenue: float = 0.0
        self.cost: float = 0.0

    # -- registration ------------------------------------------------------
    def add_store(self, name: str, **props) -> Location:
        loc = Location(name, kind="store")
        self.stores[name] = loc
        return loc

    def add_warehouse(self, name: str, **props) -> Location:
        loc = Location(name, kind="warehouse")
        self.warehouses[name] = loc
        return loc

    def add_product(self, name: str, price: float = 0.0, category: str = "general") -> Product:
        p = Product(name, price=float(price), category=category)
        self.products[name] = p
        return p

    def add_supplier(self, name: str, lead_time: int = 1, reliability: float = 1.0) -> Supplier:
        s = Supplier(name, lead_time=int(lead_time), reliability=float(reliability))
        self.suppliers[name] = s
        return s

    def add_truck(self, name: str, capacity: int = 1000) -> Truck:
        t = Truck(name, capacity=int(capacity))
        self.trucks[name] = t
        return t

    # -- lookup ------------------------------------------------------------
    def location(self, name: str) -> Location:
        if name in self.stores:
            return self.stores[name]
        if name in self.warehouses:
            return self.warehouses[name]
        raise SupermarketError(f"unknown store/warehouse {name!r}")

    def require_product(self, name: str) -> Product:
        if name not in self.products:
            raise SupermarketError(f"unknown product {name!r}")
        return self.products[name]

    def require_supplier(self, name: str) -> Supplier:
        if name not in self.suppliers:
            raise SupermarketError(f"unknown supplier {name!r}")
        return self.suppliers[name]

    # -- operations --------------------------------------------------------
    def _log(self, action: str, **data) -> None:
        entry = {"action": action, **data}
        self.ledger.append(entry)

    def stock(self, product: str, store: str, quantity: int) -> None:
        self.require_product(product)
        loc = self.location(store)
        loc.add(product, int(quantity))
        self._log("stock", product=product, location=store, quantity=int(quantity))
        self._check_rules(product, store)

    def sell(self, product: str, store: str, quantity: int) -> float:
        p = self.require_product(product)
        loc = self.location(store)
        loc.remove(product, int(quantity))
        amount = p.price * int(quantity)
        self.revenue += amount
        self._log("sell", product=product, location=store, quantity=int(quantity), amount=amount)
        self._check_rules(product, store)
        return amount

    def order(self, product: str, supplier: str, destination: str, quantity: int) -> None:
        self.require_product(product)
        self.require_supplier(supplier)
        loc = self.location(destination)
        loc.add(product, int(quantity))
        self._log(
            "order", product=product, supplier=supplier,
            destination=destination, quantity=int(quantity),
        )

    def set_price(self, product: str, amount: float) -> None:
        p = self.require_product(product)
        p.price = float(amount)
        self._log("price", product=product, amount=float(amount))

    def deliver(self, product: str, source: str, store: str, quantity: int, truck: str | None = None) -> None:
        self.require_product(product)
        src = self.location(source)
        dst = self.location(store)
        qty = int(quantity)
        if truck is not None:
            if truck not in self.trucks:
                raise SupermarketError(f"unknown truck {truck!r}")
            t = self.trucks[truck]
            if qty > t.capacity:
                raise SupermarketError(
                    f"delivery of {qty} exceeds truck {truck!r} capacity {t.capacity}"
                )
            t.deliveries += 1
        src.remove(product, qty)
        dst.add(product, qty)
        self._log("deliver", product=product, source=source, destination=store, quantity=qty, truck=truck)
        self._check_rules(product, store)

    # -- restock automation ------------------------------------------------
    def add_restock_rule(self, product: str, store: str, threshold: int, quantity: int, supplier: str) -> None:
        self.require_product(product)
        self.require_supplier(supplier)
        self.location(store)
        self.restock_rules.append(
            RestockRuleObj(product, store, int(threshold), int(quantity), supplier)
        )
        self._check_rules(product, store)

    def _check_rules(self, product: str, store: str) -> None:
        for rule in self.restock_rules:
            if rule.product == product and rule.store == store:
                loc = self.location(store)
                if loc.qty(product) < rule.threshold:
                    loc.add(product, rule.quantity)
                    self._log(
                        "auto_restock", product=product, location=store,
                        quantity=rule.quantity, supplier=rule.supplier,
                    )

    # -- reporting ---------------------------------------------------------
    def report(self, target: str | None = None) -> str:
        lines: list[str] = []
        locs: list[Location]
        if target is None or target == "all":
            locs = list(self.stores.values()) + list(self.warehouses.values())
        elif target in self.stores or target in self.warehouses:
            locs = [self.location(target)]
        else:
            raise SupermarketError(f"cannot report unknown target {target!r}")
        for loc in locs:
            lines.append(f"[{loc.kind}] {loc.name}")
            if not loc.inventory:
                lines.append("  (empty)")
            for prod in sorted(loc.inventory):
                lines.append(f"  {prod}: {loc.inventory[prod]}")
        lines.append(f"revenue: {self.revenue:.2f}")
        return "\n".join(lines)
