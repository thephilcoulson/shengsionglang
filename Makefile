CC      ?= cc
CFLAGS  ?= -O2 -std=c11 -Wall -Wextra
PREFIX  ?= /usr/local

SRC     := src/shengc.c
BIN     := shengc

.PHONY: all clean test install examples

all: $(BIN)

$(BIN): $(SRC)
	$(CC) $(CFLAGS) -o $(BIN) $(SRC)

# Compile and run the bundled example end-to-end.
examples: $(BIN)
	./$(BIN) examples/supermarket.sheng -o /tmp/ss_supermarket
	/tmp/ss_supermarket

# The test harness drives the real compiler + native binaries.
test: $(BIN)
	pytest -q tests

install: $(BIN)
	install -m 0755 $(BIN) $(PREFIX)/bin/$(BIN)

clean:
	rm -f $(BIN) *.o
	rm -f examples/*.c
