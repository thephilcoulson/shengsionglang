import pytest

from shengsiong.runtime import Supermarket, SupermarketError, Location, Product


def make():
    m = Supermarket()
    m.add_store("tampines")
    m.add_warehouse("central")
    m.add_product("milk", price=3.0)
    m.add_supplier("acme", lead_time=2, reliability=0.9)
    m.add_truck("lorry", capacity=100)
    return m


def test_add_and_lookup_entities():
    m = make()
    assert m.location("tampines").kind == "store"
    assert m.location("central").kind == "warehouse"
    assert m.require_product("milk").price == 3.0
    assert m.require_supplier("acme").lead_time == 2
    assert m.trucks["lorry"].capacity == 100


def test_location_unknown_raises():
    m = make()
    with pytest.raises(SupermarketError):
        m.location("nowhere")


def test_require_product_unknown_raises():
    m = make()
    with pytest.raises(SupermarketError):
        m.require_product("bread")


def test_require_supplier_unknown_raises():
    m = make()
    with pytest.raises(SupermarketError):
        m.require_supplier("ghost")


def test_stock_adds_inventory():
    m = make()
    m.stock("milk", "tampines", 10)
    assert m.location("tampines").qty("milk") == 10


def test_sell_reduces_and_earns_revenue():
    m = make()
    m.stock("milk", "tampines", 10)
    earned = m.sell("milk", "tampines", 4)
    assert earned == 12.0
    assert m.revenue == 12.0
    assert m.location("tampines").qty("milk") == 6


def test_sell_more_than_available_raises():
    m = make()
    m.stock("milk", "tampines", 2)
    with pytest.raises(SupermarketError):
        m.sell("milk", "tampines", 5)


def test_order_places_into_destination():
    m = make()
    m.order("milk", "acme", "central", 500)
    assert m.location("central").qty("milk") == 500


def test_order_unknown_supplier_raises():
    m = make()
    with pytest.raises(SupermarketError):
        m.order("milk", "ghost", "central", 10)


def test_set_price():
    m = make()
    m.set_price("milk", 4.5)
    assert m.require_product("milk").price == 4.5


def test_deliver_moves_between_locations():
    m = make()
    m.order("milk", "acme", "central", 100)
    m.deliver("milk", "central", "tampines", 40, truck="lorry")
    assert m.location("central").qty("milk") == 60
    assert m.location("tampines").qty("milk") == 40
    assert m.trucks["lorry"].deliveries == 1


def test_deliver_without_truck():
    m = make()
    m.order("milk", "acme", "central", 100)
    m.deliver("milk", "central", "tampines", 10)
    assert m.location("tampines").qty("milk") == 10


def test_deliver_unknown_truck_raises():
    m = make()
    m.order("milk", "acme", "central", 100)
    with pytest.raises(SupermarketError):
        m.deliver("milk", "central", "tampines", 10, truck="ghost")


def test_deliver_exceeds_truck_capacity_raises():
    m = make()
    m.order("milk", "acme", "central", 500)
    with pytest.raises(SupermarketError):
        m.deliver("milk", "central", "tampines", 200, truck="lorry")


def test_deliver_insufficient_source_raises():
    m = make()
    with pytest.raises(SupermarketError):
        m.deliver("milk", "central", "tampines", 5)


def test_location_add_negative_raises():
    loc = Location("x")
    with pytest.raises(SupermarketError):
        loc.add("milk", -1)


def test_location_remove_negative_raises():
    loc = Location("x")
    with pytest.raises(SupermarketError):
        loc.remove("milk", -1)


def test_restock_rule_triggers_on_low_stock():
    m = make()
    m.stock("milk", "tampines", 30)
    m.add_restock_rule("milk", "tampines", threshold=20, quantity=100, supplier="acme")
    # currently 30 >= 20, no trigger yet
    assert m.location("tampines").qty("milk") == 30
    m.sell("milk", "tampines", 15)  # drops to 15 < 20 -> auto restock +100
    assert m.location("tampines").qty("milk") == 115


def test_restock_rule_triggers_immediately_when_added_below():
    m = make()
    m.stock("milk", "tampines", 5)
    m.add_restock_rule("milk", "tampines", threshold=20, quantity=50, supplier="acme")
    assert m.location("tampines").qty("milk") == 55


def test_restock_rule_unknown_entities_raise():
    m = make()
    with pytest.raises(SupermarketError):
        m.add_restock_rule("ghost", "tampines", 1, 1, "acme")
    with pytest.raises(SupermarketError):
        m.add_restock_rule("milk", "tampines", 1, 1, "ghost")
    with pytest.raises(SupermarketError):
        m.add_restock_rule("milk", "nowhere", 1, 1, "acme")


def test_report_all_default():
    m = make()
    m.stock("milk", "tampines", 3)
    text = m.report()
    assert "tampines" in text
    assert "central" in text
    assert "milk: 3" in text
    assert "revenue: 0.00" in text


def test_report_targeted():
    m = make()
    m.stock("milk", "tampines", 3)
    text = m.report("tampines")
    assert "tampines" in text
    assert "central" not in text


def test_report_empty_location_shows_empty():
    m = make()
    text = m.report("central")
    assert "(empty)" in text


def test_report_all_keyword():
    m = make()
    assert "tampines" in m.report("all")


def test_report_unknown_target_raises():
    m = make()
    with pytest.raises(SupermarketError):
        m.report("nowhere")


def test_entity_as_dict_helpers():
    m = make()
    assert m.require_product("milk").as_dict()["name"] == "milk"
    assert m.require_supplier("acme").as_dict()["reliability"] == 0.9
    assert m.trucks["lorry"].as_dict()["capacity"] == 100


def test_ledger_records_actions():
    m = make()
    m.stock("milk", "tampines", 10)
    m.sell("milk", "tampines", 1)
    actions = [e["action"] for e in m.ledger]
    assert "stock" in actions and "sell" in actions
