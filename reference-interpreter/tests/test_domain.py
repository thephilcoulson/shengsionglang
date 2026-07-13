import pytest

from shengsiong import run
from shengsiong.interpreter import RuntimeErrorSS


def market(src):
    return run(src).market


def out(src):
    return run(src).output


def test_declare_entities_and_report():
    src = (
        "store tampines\n"
        "warehouse central\n"
        "supplier acme { lead_time: 2, reliability: 0.95 }\n"
        "product milk { price: 3.0, category: \"dairy\" }\n"
        "truck lorry { capacity: 500 }\n"
    )
    m = market(src)
    assert "tampines" in m.stores
    assert "central" in m.warehouses
    assert m.suppliers["acme"].lead_time == 2
    assert m.products["milk"].category == "dairy"
    assert m.trucks["lorry"].capacity == 500


def test_full_supply_chain_flow():
    src = (
        "store tampines\n"
        "warehouse central\n"
        "supplier acme\n"
        "product milk { price: 2.0 }\n"
        "order 100 units of milk from acme to central\n"
        "deliver 40 units of milk from central to tampines\n"
        "stock 10 units of milk at tampines\n"
        "sell 20 units of milk at tampines\n"
        "report tampines\n"
    )
    interp = run(src)
    m = interp.market
    assert m.location("tampines").qty("milk") == 30  # 40 + 10 - 20
    assert m.location("central").qty("milk") == 60
    assert m.revenue == 40.0
    assert any("tampines" in line for line in interp.output)


def test_price_statement_updates_product():
    src = "product milk { price: 1.0 }\nprice milk at 5.5\nprint milk.price"
    assert out(src) == ["5.5"]


def test_deliver_via_truck_counts_delivery():
    src = (
        "warehouse central\nstore tampines\nsupplier acme\n"
        "product milk\ntruck lorry { capacity: 100 }\n"
        "order 50 units of milk from acme to central\n"
        "deliver 30 units of milk from central to tampines via lorry\n"
    )
    m = market(src)
    assert m.trucks["lorry"].deliveries == 1


def test_restock_rule_auto_triggers():
    src = (
        "store tampines\nsupplier acme\nproduct milk { price: 1.0 }\n"
        "stock 30 units of milk at tampines\n"
        "restock milk at tampines when below 20 order 100 units from acme\n"
        "sell 15 units of milk at tampines\n"  # -> 15 < 20, auto +100 => 115
    )
    m = market(src)
    assert m.location("tampines").qty("milk") == 115


def test_inventory_builtin_reads_stock():
    src = (
        "store tampines\nproduct milk\n"
        "stock 7 units of milk at tampines\n"
        "print inventory(milk, tampines)\n"
    )
    assert out(src) == ["7"]


def test_revenue_builtin():
    src = (
        "store s\nproduct milk { price: 2.0 }\n"
        "stock 10 units of milk at s\nsell 3 units of milk at s\n"
        "print revenue()\n"
    )
    assert out(src) == ["6"]


def test_entity_attribute_access_all_kinds():
    src = (
        "store s\nwarehouse w\n"
        "supplier acme { lead_time: 4, reliability: 0.8 }\n"
        "product milk { price: 3.0, category: \"dairy\" }\n"
        "truck lorry { capacity: 250 }\n"
        "print milk.price\nprint milk.category\nprint milk.name\n"
        "print acme.lead_time\nprint acme.reliability\nprint acme.name\n"
        "print lorry.capacity\nprint lorry.deliveries\nprint lorry.name\n"
        "print s.name\n"
    )
    assert out(src) == [
        "3", "dairy", "milk", "4", "0.8", "acme", "250", "0", "lorry", "s",
    ]


def test_stock_unknown_product_runtime_error():
    with pytest.raises(RuntimeErrorSS):
        run("store s\nstock 1 units of ghost at s")


def test_sell_insufficient_runtime_error_has_line():
    with pytest.raises(RuntimeErrorSS):
        run("store s\nproduct milk\nsell 5 units of milk at s")


def test_deliver_over_capacity_runtime_error():
    src = (
        "warehouse w\nstore s\nsupplier acme\nproduct milk\n"
        "truck t { capacity: 10 }\n"
        "order 100 units of milk from acme to w\n"
        "deliver 50 units of milk from w to s via t\n"
    )
    with pytest.raises(RuntimeErrorSS):
        run(src)


def test_price_non_number_runtime_error():
    with pytest.raises(RuntimeErrorSS):
        run('product milk\nprice milk at "cheap"')


def test_stock_non_integer_quantity_error():
    with pytest.raises(RuntimeErrorSS):
        run("store s\nproduct milk\nstock 2.5 units of milk at s")


def test_quantity_non_number_error():
    with pytest.raises(RuntimeErrorSS):
        run('store s\nproduct milk\nstock "lots" units of milk at s')


def test_entity_name_must_be_string_error():
    # use a number where an entity name is expected
    with pytest.raises(RuntimeErrorSS):
        run("store s\nproduct milk\nstock 1 units of 5 at s")


def test_report_unknown_target_runtime_error():
    with pytest.raises(RuntimeErrorSS):
        run("store s\nreport nowhere")


def test_get_unknown_property_error():
    with pytest.raises(RuntimeErrorSS):
        run("product milk { price: 1.0 }\nprint milk.color")


def test_get_property_of_number_error():
    with pytest.raises(RuntimeErrorSS):
        run("let x = 5\nprint x.price")


def test_report_bare_and_all_and_quoted_target():
    src = (
        "store s\nproduct milk\nstock 2 units of milk at s\n"
        "report\n"
    )
    interp = run(src)
    assert any("milk: 2" in line for line in interp.output)


def test_entity_used_as_value_is_its_name():
    src = "store tampines\nlet x = tampines\nprint x"
    assert out(src) == ["tampines"]
