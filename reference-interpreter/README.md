# ShengSiong 🛒

A domain-specific programming language that **abstracts away the complexity of
running a supermarket supply chain**. Declare your stores, warehouses,
suppliers, trucks and products; then express ordering, delivery, pricing and
restocking as first-class statements. ShengSiong handles the inventory
bookkeeping, delivery logistics and automatic replenishment for you.

Named after the Singapore supermarket chain.

```
       ┌────────────┐   order    ┌────────────┐   deliver   ┌────────────┐
       │  supplier  │ ─────────▶ │ warehouse  │ ──────────▶ │   store    │
       └────────────┘            └────────────┘   (truck)   └────────────┘
                                                                  │ sell
                                                                  ▼
                                                             revenue 💰
```

## Why

Managing a supermarket conglomerate means juggling inventory across locations,
placing supplier orders with lead times, routing deliveries within truck
capacity, keeping shelves stocked, and pricing goods. ShengSiong turns all of
that into a handful of readable statements so anyone can deploy and run their
own supermarket — no ledger spreadsheets, no manual stock math.

## Install / Run

Pure Python, no runtime dependencies (tests use `pytest` + `pytest-cov`).

```bash
# run a program
python -m shengsiong run examples/supermarket.sheng

# evaluate a snippet
python -m shengsiong eval 'print 2 + 2'

# pipe from stdin
echo 'print "hi"' | python -m shengsiong run -
```

## Language tour

### Declaring entities

```
store    tampines
warehouse central { capacity: 100000 }
supplier fairprice { lead_time: 2, reliability: 0.98 }
truck    lorry { capacity: 1000 }
product  milk { price: 3.20, category: "dairy" }
```

### Supply-chain statements

```
order   500 units of milk from fairprice to central   # supplier -> warehouse/store
deliver 200 units of milk from central to tampines via lorry   # move stock (truck optional)
stock   50  units of milk at tampines                 # add stock directly
sell    30  units of milk at tampines                 # sell -> earns revenue
price   milk at 3.50                                  # set unit price
```

### Automatic restocking

```
restock milk at tampines when below 100 order 300 units from fairprice
```

Whenever `milk` at `tampines` drops below 100 units (via a sale or delivery),
the runtime automatically orders 300 more from `fairprice`. No polling, no
manual checks.

### Reporting

```
report            # all stores + warehouses + revenue
report tampines   # a single location
```

### General-purpose layer

ShengSiong is a full little language too — variables, arithmetic, comparisons,
`if`/`else`, `while`, first-class functions with closures and recursion, lists,
strings, and built-ins (`len`, `str`, `num`, `min`, `max`, `abs`,
`inventory(product, location)`, `revenue()`).

```
func margin(retail, cost) { return retail - cost }
print "margin: " + margin(milk.price, 2.10)
print "on hand: " + inventory(milk, tampines)
print "revenue: " + revenue()
```

Entity attributes are readable with dot access: `milk.price`, `milk.category`,
`fairprice.lead_time`, `lorry.capacity`, `lorry.deliveries`.

## Semantics & safety

- Selling or delivering more than is in stock is a runtime error (no negative
  inventory).
- Deliveries cannot exceed the assigned truck's capacity.
- Quantities must be whole numbers of units.
- Unknown products / suppliers / locations are caught at use.
- `while` loops have a runaway guard.

## Architecture

| Module | Responsibility |
|--------|----------------|
| `lexer.py` | Source text → tokens |
| `ast_nodes.py` | AST node definitions |
| `parser.py` | Recursive-descent parser → AST |
| `runtime.py` | Supermarket domain model (inventory, orders, delivery, restock rules, reporting) |
| `interpreter.py` | Tree-walking evaluator + built-ins |
| `cli.py` | `run` / `eval` command-line interface |

## Tests

100% statement **and** branch coverage.

```bash
python -m pytest --cov=shengsiong --cov-branch --cov-report=term-missing
```

```
TOTAL  1211 stmts  336 branch  100%
173 passed
```

## Grammar (informal EBNF)

```
program     := declaration*
declaration := letDecl | funcDecl | entityDecl | statement
entityDecl  := ("store"|"warehouse"|"supplier"|"truck"|"product") IDENT ["{" props "}"]
statement   := print | if | while | return | block
             | stock | sell | order | price | restock | deliver | report
             | exprStmt
stock       := "stock" expr ["units"] ["of"] expr "at" expr
sell        := "sell"  expr ["units"] ["of"] expr "at" expr
order       := "order" expr ["units"] ["of"] expr "from" expr "to" expr
deliver     := "deliver" expr ["units"] ["of"] expr "from" expr "to" expr ["via" expr]
price       := "price" expr "at" expr
restock     := "restock" expr "at" expr "when" "below" expr "order" expr ["units"] "from" expr
report      := "report" [expr]
```

## License

MIT.
