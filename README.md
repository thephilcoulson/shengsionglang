# ShengSiong 🛒 — native compiler

A **standalone programming language** for supermarket supply-chain and logistics.
Not interpreted, not hosted on a runtime VM: `shengc` compiles a `.sheng`
program to C and then to a **native executable** via the system C compiler. The
resulting binary runs directly on the CPU with **no Python, no JVM, no
interpreter loop** — the only dependency is libc.

```
 program.sheng ──▶ shengc ──▶ (C source) ──▶ cc ──▶ ./program   (native ELF)
                    │                                   │
              lexer│parser│codegen                 runs on the CPU
```

The compiler itself is written in C (`src/shengc.c`), the way real languages
bootstrap — Python is used only as a *test harness*, never at runtime.

## Build

```bash
make                      # builds ./shengc
```

Requires a C11 compiler (`cc`/`gcc`/`clang`).

## Use

```bash
./shengc program.sheng                 # -> ./program (native binary)
./shengc program.sheng -o market       # choose output name
./shengc program.sheng --run           # compile then run
./shengc program.sheng --emit-c        # print the generated C to stdout
./shengc program.sheng --keep-c        # keep the intermediate .c file
```

Set `CC` to pick a backend compiler: `CC=clang ./shengc program.sheng`.

## The language

### Entities

```
store    tampines
warehouse central { capacity: 100000 }
supplier fairprice { lead_time: 2, reliability: 0.98 }
truck    lorry { capacity: 1000 }
product  milk { price: 3.20, category: "dairy" }
```

### Supply-chain statements

```
order   500 units of milk from fairprice to central
deliver 200 units of milk from central to tampines via lorry
stock   50  units of milk at tampines
sell    30  units of milk at tampines
price   milk at 3.50
report                     # or: report tampines
```

### Automatic restocking

```
restock milk at tampines when below 100 order 300 units from fairprice
```

When `milk` at `tampines` falls below 100 (via a sale or delivery), the compiled
engine automatically reorders 300 units. Compiled to a tight C loop — a
200,000-step simulation with live restock rules runs in well under 100 ms.

### General-purpose core

Variables, integers/floats/strings/booleans, arithmetic, comparisons, logical
`and`/`or`/`not`, `if`/`else`, `while`, first-class recursive functions, and
built-ins: `len`, `str`, `num`, `min`, `max`, `abs`, `inventory(product, loc)`,
`revenue()`. Entity attributes via dot access: `milk.price`, `milk.category`,
`fairprice.lead_time`, `lorry.capacity`, `lorry.deliveries`.

```
func margin(retail, cost) { return retail - cost }
print "margin: " + margin(milk.price, 2.10)
print "on hand: " + inventory(milk, tampines)
```

## Compilation model

- **Values** compile to a tagged union `Value` (int / float / bool / string / nil).
- **Entities** compile to C structs held in dynamic arrays; operations are plain
  C functions (`do_stock`, `do_sell`, `do_order`, `do_deliver`, `add_rule`, …).
- **ShengSiong functions** compile to C functions (`fn_name`), so recursion and
  calls are native C calls.
- **Control flow** compiles to native C `if`/`while` — no bytecode, no dispatch
  loop.
- **Undefined variables and unknown properties are compile-time errors.**
  Stock/quantity/capacity violations are runtime errors that abort the binary
  with a diagnostic.

## Errors

- **Compile-time:** lex errors, parse errors, undefined variables, unknown
  entity properties, non-literal entity property values, invalid assignment
  targets. `shengc` exits non-zero and prints `shengc: line N: ...`.
- **Runtime:** overselling, delivering more than a truck's capacity, delivering
  more than a source holds, division/modulo by zero, dynamically-constructed
  unknown product/location names. The binary prints `runtime error: ...` and
  exits non-zero.

## Tests

The suite drives the real toolchain end-to-end: it compiles `.sheng` programs
with `shengc`, runs the produced native binaries, and asserts on their output
and exit status (plus compile-error cases).

```bash
make test           # or: pytest -q tests
```

```
43 passed
```

## Layout

```
src/shengc.c          the compiler (lexer + parser + C codegen + driver)
examples/             sample .sheng programs
tests/                end-to-end test harness (compiles + runs binaries)
Makefile              build / test / examples / install
```

## Reference interpreter

`reference-interpreter/` contains an earlier tree-walking reference implementation
with 100% test coverage. It documents the intended semantics; the native
compiler here is the real deliverable.

## License

MIT.
