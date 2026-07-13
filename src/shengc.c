/*
 * shengc -- the ShengSiong compiler.
 *
 * ShengSiong is a standalone programming language for supermarket supply-chain
 * and logistics. This compiler translates a .sheng program into C source, then
 * invokes the system C compiler to produce a native, self-contained executable
 * that depends on NO runtime VM (no Python, no JVM). The generated binary runs
 * directly on the CPU.
 *
 * Usage:
 *   shengc <input.sheng> [-o output] [--emit-c] [--keep-c] [--run]
 *
 * The language supports: variables, integer/float/string values, arithmetic,
 * comparisons, if/else, while, functions with recursion, print, and first-class
 * supermarket statements (store/warehouse/supplier/truck/product declarations,
 * order/deliver/stock/sell/price/restock/report). The domain model compiles to
 * plain C structs and functions -- native speed, designed to scale.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdarg.h>

/* ------------------------------------------------------------------ */
/* utilities                                                           */
/* ------------------------------------------------------------------ */
static void die(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "shengc: ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    va_end(ap);
    exit(1);
}

static void *xmalloc(size_t n) {
    void *p = malloc(n);
    if (!p) die("out of memory");
    return p;
}

static void *xrealloc(void *p, size_t n) {
    void *q = realloc(p, n);
    if (!q) die("out of memory");
    return q;
}

static char *xstrndup(const char *s, size_t n) {
    char *p = xmalloc(n + 1);
    memcpy(p, s, n);
    p[n] = 0;
    return p;
}

/* A growable string buffer used to build the generated C source. */
typedef struct {
    char *data;
    size_t len;
    size_t cap;
} Buf;

static void buf_init(Buf *b) {
    b->cap = 1024;
    b->len = 0;
    b->data = xmalloc(b->cap);
    b->data[0] = 0;
}

static void buf_ensure(Buf *b, size_t extra) {
    if (b->len + extra + 1 > b->cap) {
        while (b->len + extra + 1 > b->cap) b->cap *= 2;
        b->data = xrealloc(b->data, b->cap);
    }
}

static void buf_puts(Buf *b, const char *s) {
    size_t n = strlen(s);
    buf_ensure(b, n);
    memcpy(b->data + b->len, s, n);
    b->len += n;
    b->data[b->len] = 0;
}

static void buf_printf(Buf *b, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    char tmp[4096];
    int n = vsnprintf(tmp, sizeof tmp, fmt, ap);
    va_end(ap);
    if (n < 0) die("formatting error");
    if ((size_t)n < sizeof tmp) {
        buf_puts(b, tmp);
    } else {
        char *big = xmalloc((size_t)n + 1);
        va_start(ap, fmt);
        vsnprintf(big, (size_t)n + 1, fmt, ap);
        va_end(ap);
        buf_puts(b, big);
        free(big);
    }
}

/* ------------------------------------------------------------------ */
/* lexer                                                               */
/* ------------------------------------------------------------------ */
typedef enum {
    T_EOF, T_NUMBER, T_STRING, T_IDENT,
    /* keywords */
    T_STORE, T_WAREHOUSE, T_SUPPLIER, T_TRUCK, T_PRODUCT,
    T_STOCK, T_SELL, T_ORDER, T_FROM, T_TO, T_VIA, T_OF, T_UNITS, T_AT,
    T_DELIVER, T_PRICE, T_RESTOCK, T_WHEN, T_BELOW, T_REPORT,
    T_LET, T_IF, T_ELSE, T_WHILE, T_FUNC, T_RETURN, T_PRINT,
    T_TRUE, T_FALSE, T_AND, T_OR, T_NOT,
    /* symbols */
    T_LBRACE, T_RBRACE, T_LPAREN, T_RPAREN, T_COMMA, T_COLON, T_SEMI,
    T_DOT, T_ASSIGN, T_PLUS, T_MINUS, T_STAR, T_SLASH, T_PERCENT,
    T_EQ, T_NEQ, T_LT, T_GT, T_LTE, T_GTE
} TokType;

typedef struct {
    TokType type;
    char *lexeme;   /* owned */
    double num;
    int is_int;
    int line;
} Token;

typedef struct {
    const char *src;
    size_t pos;
    size_t len;
    int line;
    Token *toks;
    size_t ntok;
    size_t captok;
} Lexer;

typedef struct { const char *kw; TokType t; } KwEntry;
static KwEntry KEYWORDS[] = {
    {"store",T_STORE},{"warehouse",T_WAREHOUSE},{"supplier",T_SUPPLIER},
    {"truck",T_TRUCK},{"product",T_PRODUCT},{"stock",T_STOCK},{"sell",T_SELL},
    {"order",T_ORDER},{"from",T_FROM},{"to",T_TO},{"via",T_VIA},{"of",T_OF},
    {"units",T_UNITS},{"at",T_AT},{"deliver",T_DELIVER},{"price",T_PRICE},
    {"restock",T_RESTOCK},{"when",T_WHEN},{"below",T_BELOW},{"report",T_REPORT},
    {"let",T_LET},{"if",T_IF},{"else",T_ELSE},{"while",T_WHILE},{"func",T_FUNC},
    {"return",T_RETURN},{"print",T_PRINT},{"true",T_TRUE},{"false",T_FALSE},
    {"and",T_AND},{"or",T_OR},{"not",T_NOT},{NULL,T_EOF}
};

static void lex_push(Lexer *L, TokType t, char *lex, double num, int is_int) {
    if (L->ntok == L->captok) {
        L->captok = L->captok ? L->captok * 2 : 64;
        L->toks = xrealloc(L->toks, L->captok * sizeof(Token));
    }
    Token *tk = &L->toks[L->ntok++];
    tk->type = t;
    tk->lexeme = lex;
    tk->num = num;
    tk->is_int = is_int;
    tk->line = L->line;
}

static int lex_peek(Lexer *L) {
    return L->pos < L->len ? (unsigned char)L->src[L->pos] : 0;
}

static void lex_string(Lexer *L) {
    L->pos++; /* opening quote */
    Buf b; buf_init(&b);
    while (L->pos < L->len && L->src[L->pos] != '"') {
        char c = L->src[L->pos++];
        if (c == '\n') L->line++;
        if (c == '\\' && L->pos < L->len) {
            char n = L->src[L->pos++];
            char r = n;
            if (n == 'n') r = '\n';
            else if (n == 't') r = '\t';
            char tmp[2] = { r, 0 };
            buf_puts(&b, tmp);
        } else {
            char tmp[2] = { c, 0 };
            buf_puts(&b, tmp);
        }
    }
    if (L->pos >= L->len) die("line %d: unterminated string", L->line);
    L->pos++; /* closing quote */
    lex_push(L, T_STRING, b.data, 0, 0);
}

static void lex_number(Lexer *L) {
    size_t start = L->pos;
    int is_int = 1;
    while (isdigit(lex_peek(L))) L->pos++;
    if (lex_peek(L) == '.' && L->pos + 1 < L->len && isdigit((unsigned char)L->src[L->pos+1])) {
        is_int = 0;
        L->pos++;
        while (isdigit(lex_peek(L))) L->pos++;
    }
    char *txt = xstrndup(L->src + start, L->pos - start);
    double v = atof(txt);
    lex_push(L, T_NUMBER, txt, v, is_int);
}

static void lex_ident(Lexer *L) {
    size_t start = L->pos;
    while (isalnum(lex_peek(L)) || lex_peek(L) == '_') L->pos++;
    char *txt = xstrndup(L->src + start, L->pos - start);
    for (int i = 0; KEYWORDS[i].kw; i++) {
        if (strcmp(KEYWORDS[i].kw, txt) == 0) {
            lex_push(L, KEYWORDS[i].t, txt, 0, 0);
            return;
        }
    }
    lex_push(L, T_IDENT, txt, 0, 0);
}

static void lex_run(Lexer *L) {
    while (L->pos < L->len) {
        int c = lex_peek(L);
        if (c == '\n') { L->line++; L->pos++; continue; }
        if (c == ' ' || c == '\t' || c == '\r') { L->pos++; continue; }
        if (c == '#') { while (L->pos < L->len && L->src[L->pos] != '\n') L->pos++; continue; }
        if (c == '"') { lex_string(L); continue; }
        if (isdigit(c)) { lex_number(L); continue; }
        if (isalpha(c) || c == '_') { lex_ident(L); continue; }
        L->pos++;
        switch (c) {
            case '{': lex_push(L,T_LBRACE,xstrndup("{",1),0,0); break;
            case '}': lex_push(L,T_RBRACE,xstrndup("}",1),0,0); break;
            case '(': lex_push(L,T_LPAREN,xstrndup("(",1),0,0); break;
            case ')': lex_push(L,T_RPAREN,xstrndup(")",1),0,0); break;
            case ',': lex_push(L,T_COMMA,xstrndup(",",1),0,0); break;
            case ':': lex_push(L,T_COLON,xstrndup(":",1),0,0); break;
            case ';': lex_push(L,T_SEMI,xstrndup(";",1),0,0); break;
            case '.': lex_push(L,T_DOT,xstrndup(".",1),0,0); break;
            case '+': lex_push(L,T_PLUS,xstrndup("+",1),0,0); break;
            case '-': lex_push(L,T_MINUS,xstrndup("-",1),0,0); break;
            case '*': lex_push(L,T_STAR,xstrndup("*",1),0,0); break;
            case '/': lex_push(L,T_SLASH,xstrndup("/",1),0,0); break;
            case '%': lex_push(L,T_PERCENT,xstrndup("%",1),0,0); break;
            case '=':
                if (lex_peek(L)=='=') { L->pos++; lex_push(L,T_EQ,xstrndup("==",2),0,0); }
                else lex_push(L,T_ASSIGN,xstrndup("=",1),0,0);
                break;
            case '!':
                if (lex_peek(L)=='=') { L->pos++; lex_push(L,T_NEQ,xstrndup("!=",2),0,0); }
                else die("line %d: unexpected '!'", L->line);
                break;
            case '<':
                if (lex_peek(L)=='=') { L->pos++; lex_push(L,T_LTE,xstrndup("<=",2),0,0); }
                else lex_push(L,T_LT,xstrndup("<",1),0,0);
                break;
            case '>':
                if (lex_peek(L)=='=') { L->pos++; lex_push(L,T_GTE,xstrndup(">=",2),0,0); }
                else lex_push(L,T_GT,xstrndup(">",1),0,0);
                break;
            default:
                die("line %d: unexpected character '%c'", L->line, c);
        }
    }
    lex_push(L, T_EOF, xstrndup("",0), 0, 0);
}

/* ------------------------------------------------------------------ */
/* AST                                                                 */
/* ------------------------------------------------------------------ */
typedef enum {
    /* expressions */
    E_NUM, E_STR, E_BOOL, E_VAR, E_ASSIGN, E_UNARY, E_BINARY,
    E_CALL, E_GET,
    /* statements */
    S_EXPR, S_LET, S_PRINT, S_BLOCK, S_IF, S_WHILE, S_FUNC, S_RETURN,
    S_STORE, S_WAREHOUSE, S_SUPPLIER, S_TRUCK, S_PRODUCT,
    S_STOCK, S_SELL, S_ORDER, S_PRICE, S_RESTOCK, S_DELIVER, S_REPORT
} NodeKind;

typedef struct Node Node;

typedef struct { char *key; Node *val; } Prop;

struct Node {
    NodeKind kind;
    int line;
    /* literals */
    double num;
    int is_int;
    char *str;      /* string literal / var name / op / entity name / prop */
    int bval;
    /* unary/binary/assign */
    Node *a, *b, *c, *d;
    /* blocks / calls / args / params */
    Node **list;
    size_t nlist;
    /* function params */
    char **params;
    size_t nparams;
    /* entity properties */
    Prop *props;
    size_t nprops;
    /* optional flag (e.g. deliver via truck present) */
    int has_opt;
    Node *opt;
};

static Node *node_new(NodeKind k, int line) {
    Node *n = xmalloc(sizeof(Node));
    memset(n, 0, sizeof(Node));
    n->kind = k;
    n->line = line;
    return n;
}

static void node_add(Node *n, Node *child) {
    n->list = xrealloc(n->list, (n->nlist + 1) * sizeof(Node *));
    n->list[n->nlist++] = child;
}

/* ------------------------------------------------------------------ */
/* parser                                                              */
/* ------------------------------------------------------------------ */
typedef struct {
    Token *toks;
    size_t n;
    size_t pos;
} Parser;

static Token *P_peek(Parser *P) { return &P->toks[P->pos]; }
static Token *P_prev(Parser *P) { return &P->toks[P->pos - 1]; }
static int P_end(Parser *P) { return P_peek(P)->type == T_EOF; }
static int P_check(Parser *P, TokType t) { return !P_end(P) && P_peek(P)->type == t; }
static Token *P_adv(Parser *P) { if (!P_end(P)) P->pos++; return P_prev(P); }
static int P_match(Parser *P, TokType t) { if (P_check(P,t)) { P_adv(P); return 1; } return 0; }
static Token *P_expect(Parser *P, TokType t, const char *msg) {
    if (P_check(P, t)) return P_adv(P);
    die("line %d: parse error near '%s': %s", P_peek(P)->line, P_peek(P)->lexeme, msg);
    return NULL;
}

static Node *parse_expr(Parser *P);
static Node *parse_decl(Parser *P);
static Node *parse_stmt(Parser *P);
static Node *parse_block(Parser *P);

/* a property/attribute name may be a keyword-word too */
static int is_name_tok(Token *t) {
    if (t->type == T_IDENT) return 1;
    const char *s = t->lexeme;
    if (!s || !s[0]) return 0;
    if (!(isalpha((unsigned char)s[0]) || s[0] == '_')) return 0;
    for (const char *p = s; *p; p++)
        if (!(isalnum((unsigned char)*p) || *p == '_')) return 0;
    return 1;
}

static Node *parse_primary(Parser *P) {
    Token *t = P_peek(P);
    if (P_match(P, T_TRUE))  { Node *n = node_new(E_BOOL, t->line); n->bval = 1; return n; }
    if (P_match(P, T_FALSE)) { Node *n = node_new(E_BOOL, t->line); n->bval = 0; return n; }
    if (P_match(P, T_NUMBER)) {
        Node *n = node_new(E_NUM, t->line);
        n->num = t->num; n->is_int = t->is_int; return n;
    }
    if (P_match(P, T_STRING)) {
        Node *n = node_new(E_STR, t->line);
        n->str = xstrndup(t->lexeme, strlen(t->lexeme)); return n;
    }
    if (P_match(P, T_IDENT)) {
        Node *n = node_new(E_VAR, t->line);
        n->str = xstrndup(t->lexeme, strlen(t->lexeme)); return n;
    }
    if (P_match(P, T_LPAREN)) {
        Node *e = parse_expr(P);
        P_expect(P, T_RPAREN, "expected ')'");
        return e;
    }
    die("line %d: parse error near '%s': expected expression", t->line, t->lexeme);
    return NULL;
}

static Node *parse_call(Parser *P) {
    Node *e = parse_primary(P);
    for (;;) {
        if (P_match(P, T_LPAREN)) {
            Node *call = node_new(E_CALL, P_prev(P)->line);
            call->a = e;
            if (!P_check(P, T_RPAREN)) {
                node_add(call, parse_expr(P));
                while (P_match(P, T_COMMA)) node_add(call, parse_expr(P));
            }
            P_expect(P, T_RPAREN, "expected ')' after arguments");
            e = call;
        } else if (P_match(P, T_DOT)) {
            Token *nm = P_peek(P);
            if (!is_name_tok(nm)) die("line %d: expected property name after '.'", nm->line);
            P_adv(P);
            Node *get = node_new(E_GET, nm->line);
            get->a = e;
            get->str = xstrndup(nm->lexeme, strlen(nm->lexeme));
            e = get;
        } else break;
    }
    return e;
}

static Node *parse_unary(Parser *P) {
    if (P_check(P, T_NOT) || P_check(P, T_MINUS)) {
        Token *op = P_adv(P);
        Node *n = node_new(E_UNARY, op->line);
        n->str = xstrndup(op->lexeme, strlen(op->lexeme));
        n->a = parse_unary(P);
        return n;
    }
    return parse_call(P);
}

static Node *bin(Node *l, Token *op, Node *r) {
    Node *n = node_new(E_BINARY, op->line);
    n->str = xstrndup(op->lexeme, strlen(op->lexeme));
    n->a = l; n->b = r;
    return n;
}

static Node *parse_factor(Parser *P) {
    Node *e = parse_unary(P);
    while (P_check(P,T_STAR)||P_check(P,T_SLASH)||P_check(P,T_PERCENT)) {
        Token *op = P_adv(P); e = bin(e, op, parse_unary(P));
    }
    return e;
}
static Node *parse_term(Parser *P) {
    Node *e = parse_factor(P);
    while (P_check(P,T_PLUS)||P_check(P,T_MINUS)) {
        Token *op = P_adv(P); e = bin(e, op, parse_factor(P));
    }
    return e;
}
static Node *parse_cmp(Parser *P) {
    Node *e = parse_term(P);
    while (P_check(P,T_LT)||P_check(P,T_GT)||P_check(P,T_LTE)||P_check(P,T_GTE)) {
        Token *op = P_adv(P); e = bin(e, op, parse_term(P));
    }
    return e;
}
static Node *parse_eq(Parser *P) {
    Node *e = parse_cmp(P);
    while (P_check(P,T_EQ)||P_check(P,T_NEQ)) {
        Token *op = P_adv(P); e = bin(e, op, parse_cmp(P));
    }
    return e;
}
static Node *parse_and(Parser *P) {
    Node *e = parse_eq(P);
    while (P_check(P,T_AND)) {
        Token *op = P_adv(P); e = bin(e, op, parse_eq(P));
    }
    return e;
}
static Node *parse_or(Parser *P) {
    Node *e = parse_and(P);
    while (P_check(P,T_OR)) {
        Token *op = P_adv(P); e = bin(e, op, parse_and(P));
    }
    return e;
}
static Node *parse_assign(Parser *P) {
    Node *e = parse_or(P);
    if (P_match(P, T_ASSIGN)) {
        Token *eq = P_prev(P);
        Node *val = parse_assign(P);
        if (e->kind != E_VAR) die("line %d: invalid assignment target", eq->line);
        Node *n = node_new(E_ASSIGN, eq->line);
        n->str = e->str; n->a = val;
        return n;
    }
    return e;
}
static Node *parse_expr(Parser *P) { return parse_assign(P); }

static Node *parse_entity(Parser *P, NodeKind kind) {
    Token *nm = P_expect(P, T_IDENT, "expected entity name");
    Node *n = node_new(kind, nm->line);
    n->str = xstrndup(nm->lexeme, strlen(nm->lexeme));
    if (P_match(P, T_LBRACE)) {
        while (!P_check(P, T_RBRACE) && !P_end(P)) {
            Token *k = P_peek(P);
            if (!is_name_tok(k)) die("line %d: expected property name", k->line);
            P_adv(P);
            P_expect(P, T_COLON, "expected ':' after property name");
            Node *v = parse_expr(P);
            n->props = xrealloc(n->props, (n->nprops + 1) * sizeof(Prop));
            n->props[n->nprops].key = xstrndup(k->lexeme, strlen(k->lexeme));
            n->props[n->nprops].val = v;
            n->nprops++;
            P_match(P, T_COMMA);
        }
        P_expect(P, T_RBRACE, "expected '}'");
    } else {
        P_match(P, T_SEMI);
    }
    return n;
}

/* quantity [units] [of] product  -> sets a=quantity, b=product */
static void parse_qty_product(Parser *P, Node *n) {
    n->a = parse_expr(P);
    P_match(P, T_UNITS);
    P_match(P, T_OF);
    n->b = parse_expr(P);
}

static Node *parse_stmt(Parser *P) {
    Token *t = P_peek(P);
    if (P_match(P, T_PRINT)) {
        Node *n = node_new(S_PRINT, t->line);
        n->a = parse_expr(P); P_match(P, T_SEMI); return n;
    }
    if (P_match(P, T_IF)) {
        Node *n = node_new(S_IF, t->line);
        P_expect(P, T_LPAREN, "expected '(' after if");
        n->a = parse_expr(P);
        P_expect(P, T_RPAREN, "expected ')'");
        n->b = parse_block(P);
        if (P_match(P, T_ELSE)) n->c = parse_block(P);
        return n;
    }
    if (P_match(P, T_WHILE)) {
        Node *n = node_new(S_WHILE, t->line);
        P_expect(P, T_LPAREN, "expected '(' after while");
        n->a = parse_expr(P);
        P_expect(P, T_RPAREN, "expected ')'");
        n->b = parse_block(P);
        return n;
    }
    if (P_match(P, T_RETURN)) {
        Node *n = node_new(S_RETURN, t->line);
        if (!P_check(P, T_SEMI) && !P_check(P, T_RBRACE)) n->a = parse_expr(P);
        P_match(P, T_SEMI);
        return n;
    }
    if (P_check(P, T_LBRACE)) return parse_block(P);
    if (P_match(P, T_STOCK)) {
        Node *n = node_new(S_STOCK, t->line);
        parse_qty_product(P, n);
        P_expect(P, T_AT, "expected 'at <store>'");
        n->c = parse_expr(P); P_match(P, T_SEMI); return n;
    }
    if (P_match(P, T_SELL)) {
        Node *n = node_new(S_SELL, t->line);
        parse_qty_product(P, n);
        P_expect(P, T_AT, "expected 'at <store>'");
        n->c = parse_expr(P); P_match(P, T_SEMI); return n;
    }
    if (P_match(P, T_ORDER)) {
        Node *n = node_new(S_ORDER, t->line);
        parse_qty_product(P, n);
        P_expect(P, T_FROM, "expected 'from <supplier>'");
        n->c = parse_expr(P);
        P_expect(P, T_TO, "expected 'to <destination>'");
        n->d = parse_expr(P); P_match(P, T_SEMI); return n;
    }
    if (P_match(P, T_PRICE)) {
        Node *n = node_new(S_PRICE, t->line);
        n->a = parse_expr(P);
        P_expect(P, T_AT, "expected 'at <amount>'");
        n->b = parse_expr(P); P_match(P, T_SEMI); return n;
    }
    if (P_match(P, T_RESTOCK)) {
        Node *n = node_new(S_RESTOCK, t->line);
        n->a = parse_expr(P);                 /* product */
        P_expect(P, T_AT, "expected 'at <store>'");
        n->b = parse_expr(P);                 /* store */
        P_expect(P, T_WHEN, "expected 'when below'");
        P_expect(P, T_BELOW, "expected 'below'");
        n->c = parse_expr(P);                 /* threshold */
        P_expect(P, T_ORDER, "expected 'order <qty>'");
        n->d = parse_expr(P);                 /* qty */
        P_match(P, T_UNITS);
        P_expect(P, T_FROM, "expected 'from <supplier>'");
        n->opt = parse_expr(P);               /* supplier */
        n->has_opt = 1;
        P_match(P, T_SEMI);
        return n;
    }
    if (P_match(P, T_DELIVER)) {
        Node *n = node_new(S_DELIVER, t->line);
        parse_qty_product(P, n);
        P_expect(P, T_FROM, "expected 'from <source>'");
        n->c = parse_expr(P);
        P_expect(P, T_TO, "expected 'to <store>'");
        n->d = parse_expr(P);
        if (P_match(P, T_VIA)) { n->has_opt = 1; n->opt = parse_expr(P); }
        P_match(P, T_SEMI);
        return n;
    }
    if (P_match(P, T_REPORT)) {
        Node *n = node_new(S_REPORT, t->line);
        if (P_check(P, T_IDENT) || P_check(P, T_STRING) || P_check(P, T_LPAREN)) n->a = parse_expr(P);
        P_match(P, T_SEMI);
        return n;
    }
    /* expression statement */
    Node *n = node_new(S_EXPR, t->line);
    n->a = parse_expr(P);
    P_match(P, T_SEMI);
    return n;
}

static Node *parse_block(Parser *P) {
    Token *t = P_expect(P, T_LBRACE, "expected '{'");
    Node *n = node_new(S_BLOCK, t->line);
    while (!P_check(P, T_RBRACE) && !P_end(P)) node_add(n, parse_decl(P));
    P_expect(P, T_RBRACE, "expected '}'");
    return n;
}

static Node *parse_decl(Parser *P) {
    Token *t = P_peek(P);
    if (P_match(P, T_LET)) {
        Node *n = node_new(S_LET, t->line);
        Token *nm = P_expect(P, T_IDENT, "expected variable name");
        n->str = xstrndup(nm->lexeme, strlen(nm->lexeme));
        P_expect(P, T_ASSIGN, "expected '='");
        n->a = parse_expr(P);
        P_match(P, T_SEMI);
        return n;
    }
    if (P_match(P, T_FUNC)) {
        Node *n = node_new(S_FUNC, t->line);
        Token *nm = P_expect(P, T_IDENT, "expected function name");
        n->str = xstrndup(nm->lexeme, strlen(nm->lexeme));
        P_expect(P, T_LPAREN, "expected '('");
        if (!P_check(P, T_RPAREN)) {
            do {
                Token *p = P_expect(P, T_IDENT, "expected parameter name");
                n->params = xrealloc(n->params, (n->nparams + 1) * sizeof(char *));
                n->params[n->nparams++] = xstrndup(p->lexeme, strlen(p->lexeme));
            } while (P_match(P, T_COMMA));
        }
        P_expect(P, T_RPAREN, "expected ')'");
        n->a = parse_block(P);
        return n;
    }
    if (P_match(P, T_STORE))     return parse_entity(P, S_STORE);
    if (P_match(P, T_WAREHOUSE)) return parse_entity(P, S_WAREHOUSE);
    if (P_match(P, T_SUPPLIER))  return parse_entity(P, S_SUPPLIER);
    if (P_match(P, T_TRUCK))     return parse_entity(P, S_TRUCK);
    if (P_match(P, T_PRODUCT))   return parse_entity(P, S_PRODUCT);
    return parse_stmt(P);
}

static Node **parse_program(Parser *P, size_t *out_n) {
    Node **prog = NULL;
    size_t n = 0, cap = 0;
    while (!P_end(P)) {
        if (n == cap) { cap = cap ? cap*2 : 32; prog = xrealloc(prog, cap*sizeof(Node*)); }
        prog[n++] = parse_decl(P);
    }
    *out_n = n;
    return prog;
}

/* ------------------------------------------------------------------ */
/* code generation -> C                                                */
/* ------------------------------------------------------------------ */

/* The runtime prelude: a complete supermarket engine in portable C, with a
 * tagged Value type. Emitted verbatim into every compiled program so the
 * result is fully self-contained (no external library, no VM). */
static const char *RUNTIME_PRELUDE =
"#define _POSIX_C_SOURCE 200809L\n"
"#include <stdio.h>\n"
"#include <stdlib.h>\n"
"#include <string.h>\n"
"\n"
"typedef enum { V_NIL, V_INT, V_FLOAT, V_BOOL, V_STR } VType;\n"
"typedef struct { VType t; long long i; double f; int b; char *s; } Value;\n"
"\n"
"static Value v_nil(void){ Value v; v.t=V_NIL; v.i=0; v.f=0; v.b=0; v.s=0; return v; }\n"
"static Value v_int(long long i){ Value v=v_nil(); v.t=V_INT; v.i=i; return v; }\n"
"static Value v_float(double f){ Value v=v_nil(); v.t=V_FLOAT; v.f=f; return v; }\n"
"static Value v_bool(int b){ Value v=v_nil(); v.t=V_BOOL; v.b=b?1:0; return v; }\n"
"static Value v_str(const char*s){ Value v=v_nil(); v.t=V_STR; v.s=strdup(s?s:\"\"); return v; }\n"
"\n"
"static void ss_die(const char*msg){ fprintf(stderr,\"runtime error: %s\\n\",msg); exit(1); }\n"
"\n"
"static double as_num(Value v){\n"
"  if(v.t==V_INT) return (double)v.i;\n"
"  if(v.t==V_FLOAT) return v.f;\n"
"  ss_die(\"expected a number\"); return 0;\n"
"}\n"
"static int is_num(Value v){ return v.t==V_INT||v.t==V_FLOAT; }\n"
"static long long as_units(Value v){\n"
"  if(v.t==V_INT) return v.i;\n"
"  if(v.t==V_FLOAT){ if(v.f!=(long long)v.f) ss_die(\"expected a whole number of units\"); return (long long)v.f; }\n"
"  ss_die(\"expected a number\"); return 0;\n"
"}\n"
"static const char* as_name(Value v){ if(v.t!=V_STR) ss_die(\"expected an entity name\"); return v.s; }\n"
"\n"
"static int v_truthy(Value v){\n"
"  switch(v.t){\n"
"    case V_NIL: return 0;\n"
"    case V_BOOL: return v.b;\n"
"    case V_INT: return v.i!=0;\n"
"    case V_FLOAT: return v.f!=0;\n"
"    case V_STR: return v.s && v.s[0];\n"
"  }\n"
"  return 1;\n"
"}\n"
"\n"
"static char* fmt_num(double f){\n"
"  static char buf[64];\n"
"  if(f==(long long)f) snprintf(buf,sizeof buf,\"%lld\",(long long)f);\n"
"  else snprintf(buf,sizeof buf,\"%.10g\",f);\n"
"  return buf;\n"
"}\n"
"static char* v_to_str(Value v){\n"
"  static char buf[128];\n"
"  switch(v.t){\n"
"    case V_NIL: return \"nil\";\n"
"    case V_BOOL: return v.b?\"true\":\"false\";\n"
"    case V_INT: snprintf(buf,sizeof buf,\"%lld\",v.i); return buf;\n"
"    case V_FLOAT: return fmt_num(v.f);\n"
"    case V_STR: return v.s;\n"
"  }\n"
"  return \"\";\n"
"}\n"
"static void v_print(Value v){ printf(\"%s\\n\", v_to_str(v)); }\n"
"\n"
"static Value v_add(Value a, Value b){\n"
"  if(a.t==V_STR||b.t==V_STR){ char*sa=strdup(v_to_str(a)); char*sb=v_to_str(b);\n"
"    char*r=malloc(strlen(sa)+strlen(sb)+1); strcpy(r,sa); strcat(r,sb); free(sa); return v_str(r); }\n"
"  if(!is_num(a)||!is_num(b)) ss_die(\"operator + expects numbers\");\n"
"  if(a.t==V_INT&&b.t==V_INT) return v_int(a.i+b.i); return v_float(as_num(a)+as_num(b));\n"
"}\n"
"static void need_nums(Value a,Value b){ if(!is_num(a)||!is_num(b)) ss_die(\"operator expects numbers\"); }\n"
"static Value v_sub(Value a,Value b){ need_nums(a,b); if(a.t==V_INT&&b.t==V_INT) return v_int(a.i-b.i); return v_float(as_num(a)-as_num(b)); }\n"
"static Value v_mul(Value a,Value b){ need_nums(a,b); if(a.t==V_INT&&b.t==V_INT) return v_int(a.i*b.i); return v_float(as_num(a)*as_num(b)); }\n"
"static Value v_div(Value a,Value b){ need_nums(a,b); double d=as_num(b); if(d==0) ss_die(\"division by zero\");\n"
"  if(a.t==V_INT&&b.t==V_INT&&b.i!=0&&a.i%b.i==0) return v_int(a.i/b.i); return v_float(as_num(a)/d); }\n"
"static Value v_mod(Value a,Value b){ need_nums(a,b); long long d=as_units(b); if(d==0) ss_die(\"modulo by zero\"); return v_int(as_units(a)%d); }\n"
"static int v_equal(Value a,Value b){\n"
"  if(a.t==V_BOOL||b.t==V_BOOL){ if(a.t!=b.t) return 0; return a.b==b.b; }\n"
"  if(is_num(a)&&is_num(b)) return as_num(a)==as_num(b);\n"
"  if(a.t==V_STR&&b.t==V_STR) return strcmp(a.s,b.s)==0;\n"
"  if(a.t==V_NIL&&b.t==V_NIL) return 1;\n"
"  return 0;\n"
"}\n"
"static Value v_cmp(Value a,Value b,int op){ need_nums(a,b); double x=as_num(a),y=as_num(b);\n"
"  switch(op){case 0:return v_bool(x<y);case 1:return v_bool(x>y);case 2:return v_bool(x<=y);default:return v_bool(x>=y);} }\n"
;

static const char *RUNTIME_ENGINE =
"typedef struct { char*prod; long long qty; } Item;\n"
"typedef struct { char*name; int is_wh; Item*items; int nitems; } Loc;\n"
"typedef struct { char*name; double price; char*category; } Prod;\n"
"typedef struct { char*name; long long lead_time; double reliability; } Supp;\n"
"typedef struct { char*name; long long capacity; long long deliveries; } Truck;\n"
"typedef struct { char*prod; char*store; long long threshold; long long qty; char*supplier; } Rule;\n"
"\n"
"static Loc*   g_locs=0;  static int g_nlocs=0;\n"
"static Prod*  g_prods=0; static int g_nprods=0;\n"
"static Supp*  g_supps=0; static int g_nsupps=0;\n"
"static Truck* g_trucks=0;static int g_ntrucks=0;\n"
"static Rule*  g_rules=0; static int g_nrules=0;\n"
"static double g_revenue=0;\n"
"\n"
"static void reg_loc(const char*n,int wh){ g_locs=realloc(g_locs,(g_nlocs+1)*sizeof(Loc));\n"
"  g_locs[g_nlocs].name=strdup(n); g_locs[g_nlocs].is_wh=wh; g_locs[g_nlocs].items=0; g_locs[g_nlocs].nitems=0; g_nlocs++; }\n"
"static void reg_prod(const char*n,double price,const char*cat){ g_prods=realloc(g_prods,(g_nprods+1)*sizeof(Prod));\n"
"  g_prods[g_nprods].name=strdup(n); g_prods[g_nprods].price=price; g_prods[g_nprods].category=strdup(cat?cat:\"general\"); g_nprods++; }\n"
"static void reg_supp(const char*n,long long lt,double rel){ g_supps=realloc(g_supps,(g_nsupps+1)*sizeof(Supp));\n"
"  g_supps[g_nsupps].name=strdup(n); g_supps[g_nsupps].lead_time=lt; g_supps[g_nsupps].reliability=rel; g_nsupps++; }\n"
"static void reg_truck(const char*n,long long cap){ g_trucks=realloc(g_trucks,(g_ntrucks+1)*sizeof(Truck));\n"
"  g_trucks[g_ntrucks].name=strdup(n); g_trucks[g_ntrucks].capacity=cap; g_trucks[g_ntrucks].deliveries=0; g_ntrucks++; }\n"
"\n"
"static Loc* find_loc(const char*n){ for(int i=0;i<g_nlocs;i++) if(!strcmp(g_locs[i].name,n)) return &g_locs[i];\n"
"  { char m[128]; snprintf(m,sizeof m,\"unknown store/warehouse '%s'\",n); ss_die(m);} return 0; }\n"
"static Prod* find_prod(const char*n){ for(int i=0;i<g_nprods;i++) if(!strcmp(g_prods[i].name,n)) return &g_prods[i];\n"
"  { char m[128]; snprintf(m,sizeof m,\"unknown product '%s'\",n); ss_die(m);} return 0; }\n"
"static Supp* find_supp(const char*n){ for(int i=0;i<g_nsupps;i++) if(!strcmp(g_supps[i].name,n)) return &g_supps[i];\n"
"  { char m[128]; snprintf(m,sizeof m,\"unknown supplier '%s'\",n); ss_die(m);} return 0; }\n"
"static Truck* find_truck(const char*n){ for(int i=0;i<g_ntrucks;i++) if(!strcmp(g_trucks[i].name,n)) return &g_trucks[i];\n"
"  { char m[128]; snprintf(m,sizeof m,\"unknown truck '%s'\",n); ss_die(m);} return 0; }\n"
"\n"
"static long long loc_qty(Loc*L,const char*p){ for(int i=0;i<L->nitems;i++) if(!strcmp(L->items[i].prod,p)) return L->items[i].qty; return 0; }\n"
"static void loc_add(Loc*L,const char*p,long long amt){ for(int i=0;i<L->nitems;i++) if(!strcmp(L->items[i].prod,p)){ L->items[i].qty+=amt; return; }\n"
"  L->items=realloc(L->items,(L->nitems+1)*sizeof(Item)); L->items[L->nitems].prod=strdup(p); L->items[L->nitems].qty=amt; L->nitems++; }\n"
"static void loc_remove(Loc*L,const char*p,long long amt){ long long have=loc_qty(L,p);\n"
"  if(amt>have){ char m[160]; snprintf(m,sizeof m,\"insufficient stock of '%s' at '%s': have %lld, need %lld\",p,L->name,have,amt); ss_die(m);} loc_add(L,p,-amt); }\n"
"\n"
"static void check_rules(const char*prod,const char*store);\n"
"static void do_stock(const char*prod,const char*store,long long qty){ find_prod(prod); loc_add(find_loc(store),prod,qty); check_rules(prod,store); }\n"
"static void do_sell(const char*prod,const char*store,long long qty){ Prod*p=find_prod(prod); Loc*L=find_loc(store); loc_remove(L,prod,qty); g_revenue+=p->price*(double)qty; check_rules(prod,store); }\n"
"static void do_order(const char*prod,const char*supp,const char*dest,long long qty){ find_prod(prod); find_supp(supp); loc_add(find_loc(dest),prod,qty); }\n"
"static void do_price(const char*prod,double amt){ find_prod(prod)->price=amt; }\n"
"static void do_deliver(const char*prod,const char*src,const char*store,long long qty,const char*truck){ find_prod(prod); Loc*S=find_loc(src); Loc*D=find_loc(store);\n"
"  if(truck){ Truck*t=find_truck(truck); if(qty>t->capacity){ char m[160]; snprintf(m,sizeof m,\"delivery of %lld exceeds truck '%s' capacity %lld\",qty,truck,t->capacity); ss_die(m);} t->deliveries++; }\n"
"  loc_remove(S,prod,qty); loc_add(D,prod,qty); check_rules(prod,store); }\n"
"static void add_rule(const char*prod,const char*store,long long th,long long qty,const char*supp){ find_prod(prod); find_supp(supp); find_loc(store);\n"
"  g_rules=realloc(g_rules,(g_nrules+1)*sizeof(Rule)); g_rules[g_nrules].prod=strdup(prod); g_rules[g_nrules].store=strdup(store); g_rules[g_nrules].threshold=th; g_rules[g_nrules].qty=qty; g_rules[g_nrules].supplier=strdup(supp); g_nrules++;\n"
"  check_rules(prod,store); }\n"
"static void check_rules(const char*prod,const char*store){ for(int i=0;i<g_nrules;i++) if(!strcmp(g_rules[i].prod,prod)&&!strcmp(g_rules[i].store,store)){ Loc*L=find_loc(store); if(loc_qty(L,prod)<g_rules[i].threshold) loc_add(L,prod,g_rules[i].qty); } }\n"
"\n"
"static int cmp_item(const void*a,const void*b){ return strcmp(((Item*)a)->prod,((Item*)b)->prod); }\n"
"static void report_loc(Loc*L){ printf(\"[%s] %s\\n\", L->is_wh?\"warehouse\":\"store\", L->name);\n"
"  if(L->nitems==0){ printf(\"  (empty)\\n\"); return; } qsort(L->items,L->nitems,sizeof(Item),cmp_item);\n"
"  for(int i=0;i<L->nitems;i++) printf(\"  %s: %lld\\n\", L->items[i].prod, L->items[i].qty); }\n"
"static void do_report(const char*target){\n"
"  if(!target||!strcmp(target,\"all\")){ for(int i=0;i<g_nlocs;i++) report_loc(&g_locs[i]); }\n"
"  else { int found=0; for(int i=0;i<g_nlocs;i++) if(!strcmp(g_locs[i].name,target)){ report_loc(&g_locs[i]); found=1; }\n"
"    if(!found){ char m[128]; snprintf(m,sizeof m,\"cannot report unknown target '%s'\",target); ss_die(m);} }\n"
"  printf(\"revenue: %.2f\\n\", g_revenue); }\n"
"\n"
"static double prod_price(const char*n){ return find_prod(n)->price; }\n"
"static const char* prod_cat(const char*n){ return find_prod(n)->category; }\n"
"static long long supp_lead(const char*n){ return find_supp(n)->lead_time; }\n"
"static double supp_rel(const char*n){ return find_supp(n)->reliability; }\n"
"static long long truck_cap(const char*n){ return find_truck(n)->capacity; }\n"
"static long long truck_deliv(const char*n){ return find_truck(n)->deliveries; }\n"
"static long long ss_inventory(const char*prod,const char*store){ find_prod(prod); return loc_qty(find_loc(store),prod); }\n"
"\n"
"static Value bi_len(Value v){ if(v.t!=V_STR) ss_die(\"len() expects a string\"); return v_int((long long)strlen(v.s)); }\n"
"static Value bi_str(Value v){ return v_str(v_to_str(v)); }\n"
"static Value bi_num(Value v){ if(is_num(v)) return v; if(v.t==V_STR){ char*e; double d=strtod(v.s,&e); if(e==v.s||*e) ss_die(\"cannot convert to number\"); if(d==(long long)d) return v_int((long long)d); return v_float(d);} ss_die(\"cannot convert to number\"); return v_nil(); }\n"
"static Value bi_abs(Value v){ if(v.t==V_INT) return v_int(v.i<0?-v.i:v.i); return v_float(as_num(v)<0?-as_num(v):as_num(v)); }\n"
;

/* symbol tracking for compile-time entity/function resolution */
typedef struct { char **names; char *kinds; size_t n, cap; } EntTable;
static EntTable g_ents; /* kind: p=product s=supplier t=truck l=store/warehouse */

static void ent_add(const char *name, char kind) {
    if (g_ents.n == g_ents.cap) {
        g_ents.cap = g_ents.cap ? g_ents.cap*2 : 32;
        g_ents.names = xrealloc(g_ents.names, g_ents.cap*sizeof(char*));
        g_ents.kinds = xrealloc(g_ents.kinds, g_ents.cap);
    }
    g_ents.names[g_ents.n] = xstrndup(name, strlen(name));
    g_ents.kinds[g_ents.n] = kind;
    g_ents.n++;
}
static char ent_kind(const char *name) {
    for (size_t i = 0; i < g_ents.n; i++)
        if (strcmp(g_ents.names[i], name) == 0) return g_ents.kinds[i];
    return 0;
}

/* known ShengSiong variable names at file (global) scope */
typedef struct { char **names; size_t n, cap; } NameSet;
static int nameset_has(NameSet *s, const char *n) {
    for (size_t i = 0; i < s->n; i++) if (!strcmp(s->names[i], n)) return 1;
    return 0;
}
static void nameset_add(NameSet *s, const char *n) {
    if (nameset_has(s, n)) return;
    if (s->n == s->cap) { s->cap = s->cap?s->cap*2:16; s->names = xrealloc(s->names, s->cap*sizeof(char*)); }
    s->names[s->n++] = xstrndup(n, strlen(n));
}

static NameSet g_funcs;     /* function names */
static NameSet g_globals;   /* top-level let variables */
static NameSet g_locals;    /* in-scope locals during codegen (params + lets) */

static void nameset_clear(NameSet *s) { s->n = 0; }

static void gen_expr(Buf *b, Node *e);
static void gen_stmt(Buf *b, Node *s, int indent);

static void ind(Buf *b, int n) { for (int i=0;i<n;i++) buf_puts(b, "    "); }

/* emit a C string literal from a C string */
static void emit_cstr(Buf *b, const char *s) {
    buf_puts(b, "\"");
    for (const char *p = s; *p; p++) {
        switch (*p) {
            case '"': buf_puts(b, "\\\""); break;
            case '\\': buf_puts(b, "\\\\"); break;
            case '\n': buf_puts(b, "\\n"); break;
            case '\t': buf_puts(b, "\\t"); break;
            default: { char t[2]={*p,0}; buf_puts(b,t); }
        }
    }
    buf_puts(b, "\"");
}

static void gen_expr(Buf *b, Node *e) {
    switch (e->kind) {
        case E_NUM:
            if (e->is_int) buf_printf(b, "v_int(%lldLL)", (long long)e->num);
            else buf_printf(b, "v_float(%.17g)", e->num);
            break;
        case E_STR:
            buf_puts(b, "v_str("); emit_cstr(b, e->str); buf_puts(b, ")");
            break;
        case E_BOOL:
            buf_printf(b, "v_bool(%d)", e->bval);
            break;
        case E_VAR: {
            char k = ent_kind(e->str);
            if (k) { buf_puts(b, "v_str("); emit_cstr(b, e->str); buf_puts(b, ")"); }
            else {
                if (!nameset_has(&g_globals, e->str) && !nameset_has(&g_locals, e->str))
                    die("line %d: undefined variable '%s'", e->line, e->str);
                buf_printf(b, "ss_%s", e->str);
            }
            break;
        }
        case E_ASSIGN:
            if (!nameset_has(&g_globals, e->str) && !nameset_has(&g_locals, e->str))
                die("line %d: assignment to undefined variable '%s'", e->line, e->str);
            buf_printf(b, "(ss_%s = ", e->str);
            gen_expr(b, e->a);
            buf_puts(b, ")");
            break;
        case E_UNARY:
            if (strcmp(e->str, "-") == 0) {
                buf_puts(b, "v_sub(v_int(0), ");
                gen_expr(b, e->a);
                buf_puts(b, ")");
            } else { /* not */
                buf_puts(b, "v_bool(!v_truthy(");
                gen_expr(b, e->a);
                buf_puts(b, "))");
            }
            break;
        case E_BINARY: {
            const char *op = e->str;
            const char *fn = NULL; int cmp = -1;
            if (!strcmp(op,"+")) fn="v_add";
            else if (!strcmp(op,"-")) fn="v_sub";
            else if (!strcmp(op,"*")) fn="v_mul";
            else if (!strcmp(op,"/")) fn="v_div";
            else if (!strcmp(op,"%")) fn="v_mod";
            else if (!strcmp(op,"==")) fn="EQ";
            else if (!strcmp(op,"!=")) fn="NE";
            else if (!strcmp(op,"<")) cmp=0;
            else if (!strcmp(op,">")) cmp=1;
            else if (!strcmp(op,"<=")) cmp=2;
            else if (!strcmp(op,">=")) cmp=3;
            else if (!strcmp(op,"and")) fn="AND";
            else if (!strcmp(op,"or")) fn="OR";
            if (cmp >= 0) {
                buf_puts(b, "v_cmp("); gen_expr(b,e->a); buf_puts(b,", "); gen_expr(b,e->b); buf_printf(b,", %d)",cmp);
            } else if (!strcmp(fn,"EQ")) {
                buf_puts(b,"v_bool(v_equal("); gen_expr(b,e->a); buf_puts(b,", "); gen_expr(b,e->b); buf_puts(b,"))");
            } else if (!strcmp(fn,"NE")) {
                buf_puts(b,"v_bool(!v_equal("); gen_expr(b,e->a); buf_puts(b,", "); gen_expr(b,e->b); buf_puts(b,"))");
            } else if (!strcmp(fn,"AND")) {
                buf_puts(b,"ss_and("); gen_expr(b,e->a); buf_puts(b,", "); gen_expr(b,e->b); buf_puts(b,")");
            } else if (!strcmp(fn,"OR")) {
                buf_puts(b,"ss_or("); gen_expr(b,e->a); buf_puts(b,", "); gen_expr(b,e->b); buf_puts(b,")");
            } else {
                buf_printf(b,"%s(",fn); gen_expr(b,e->a); buf_puts(b,", "); gen_expr(b,e->b); buf_puts(b,")");
            }
            break;
        }
        case E_GET: {
            /* entity attribute access resolved at compile time */
            if (e->a->kind != E_VAR) die("line %d: property access requires an entity", e->line);
            char k = ent_kind(e->a->str);
            const char *nm = e->a->str, *at = e->str;
            if (k=='p' && !strcmp(at,"price")) buf_printf(b,"v_float(prod_price(\"%s\"))",nm);
            else if (k=='p' && !strcmp(at,"category")) buf_printf(b,"v_str(prod_cat(\"%s\"))",nm);
            else if (k=='s' && !strcmp(at,"lead_time")) buf_printf(b,"v_int(supp_lead(\"%s\"))",nm);
            else if (k=='s' && !strcmp(at,"reliability")) buf_printf(b,"v_float(supp_rel(\"%s\"))",nm);
            else if (k=='t' && !strcmp(at,"capacity")) buf_printf(b,"v_int(truck_cap(\"%s\"))",nm);
            else if (k=='t' && !strcmp(at,"deliveries")) buf_printf(b,"v_int(truck_deliv(\"%s\"))",nm);
            else if (!strcmp(at,"name") && k) buf_printf(b,"v_str(\"%s\")",nm);
            else die("line %d: cannot read property '%s' of '%s'", e->line, at, nm);
            break;
        }
        case E_CALL: {
            if (e->a->kind != E_VAR) die("line %d: can only call named functions", e->line);
            const char *fn = e->a->str;
            if (!strcmp(fn,"len")||!strcmp(fn,"str")||!strcmp(fn,"num")||!strcmp(fn,"abs")) {
                if (e->nlist != 1) die("line %d: %s() takes 1 argument", e->line, fn);
                buf_printf(b,"bi_%s(",fn); gen_expr(b,e->list[0]); buf_puts(b,")");
            } else if (!strcmp(fn,"min")||!strcmp(fn,"max")) {
                if (e->nlist < 1) die("line %d: %s() needs arguments", e->line, fn);
                for (size_t i=0;i+1<e->nlist;i++) buf_printf(b,"ss_%s(",fn);
                gen_expr(b,e->list[0]);
                for (size_t i=1;i<e->nlist;i++){ buf_puts(b,", "); gen_expr(b,e->list[i]); buf_puts(b,")"); }
            } else if (!strcmp(fn,"revenue")) {
                if (e->nlist!=0) die("line %d: revenue() takes no arguments", e->line);
                buf_puts(b,"v_float(g_revenue)");
            } else if (!strcmp(fn,"inventory")) {
                if (e->nlist!=2) die("line %d: inventory() takes 2 arguments", e->line);
                buf_puts(b,"v_int(ss_inventory(as_name("); gen_expr(b,e->list[0]);
                buf_puts(b,"), as_name("); gen_expr(b,e->list[1]); buf_puts(b,")))");
            } else {
                buf_printf(b,"fn_%s(",fn);
                for (size_t i=0;i<e->nlist;i++){ if(i) buf_puts(b,", "); gen_expr(b,e->list[i]); }
                buf_puts(b,")");
            }
            break;
        }
        default:
            die("internal: unexpected expression node %d", e->kind);
    }
}

static void gen_block_body(Buf *b, Node *blk, int indent) {
    for (size_t i = 0; i < blk->nlist; i++) gen_stmt(b, blk->list[i], indent);
}

static void gen_stmt(Buf *b, Node *s, int indent) {
    switch (s->kind) {
        case S_EXPR:
            ind(b,indent); buf_puts(b,"(void)("); gen_expr(b,s->a); buf_puts(b,");\n");
            break;
        case S_LET:
            ind(b,indent); buf_printf(b,"Value ss_%s = ", s->str); gen_expr(b,s->a); buf_puts(b,";\n");
            ind(b,indent); buf_printf(b,"(void)ss_%s;\n", s->str);
            nameset_add(&g_locals, s->str);
            break;
        case S_PRINT:
            ind(b,indent); buf_puts(b,"v_print("); gen_expr(b,s->a); buf_puts(b,");\n");
            break;
        case S_BLOCK:
            ind(b,indent); buf_puts(b,"{\n");
            gen_block_body(b, s, indent+1);
            ind(b,indent); buf_puts(b,"}\n");
            break;
        case S_IF:
            ind(b,indent); buf_puts(b,"if (v_truthy("); gen_expr(b,s->a); buf_puts(b,")) {\n");
            gen_block_body(b, s->b, indent+1);
            ind(b,indent); buf_puts(b,"}");
            if (s->c) { buf_puts(b," else {\n"); gen_block_body(b, s->c, indent+1); ind(b,indent); buf_puts(b,"}\n"); }
            else buf_puts(b,"\n");
            break;
        case S_WHILE:
            ind(b,indent); buf_puts(b,"while (v_truthy("); gen_expr(b,s->a); buf_puts(b,")) {\n");
            gen_block_body(b, s->b, indent+1);
            ind(b,indent); buf_puts(b,"}\n");
            break;
        case S_RETURN:
            ind(b,indent);
            if (s->a) { buf_puts(b,"return "); gen_expr(b,s->a); buf_puts(b,";\n"); }
            else buf_puts(b,"return v_nil();\n");
            break;
        case S_STOCK:
            ind(b,indent); buf_puts(b,"do_stock(as_name("); gen_expr(b,s->b);
            buf_puts(b,"), as_name("); gen_expr(b,s->c); buf_puts(b,"), as_units(");
            gen_expr(b,s->a); buf_puts(b,"));\n");
            break;
        case S_SELL:
            ind(b,indent); buf_puts(b,"do_sell(as_name("); gen_expr(b,s->b);
            buf_puts(b,"), as_name("); gen_expr(b,s->c); buf_puts(b,"), as_units(");
            gen_expr(b,s->a); buf_puts(b,"));\n");
            break;
        case S_ORDER:
            ind(b,indent); buf_puts(b,"do_order(as_name("); gen_expr(b,s->b);
            buf_puts(b,"), as_name("); gen_expr(b,s->c); buf_puts(b,"), as_name(");
            gen_expr(b,s->d); buf_puts(b,"), as_units("); gen_expr(b,s->a); buf_puts(b,"));\n");
            break;
        case S_PRICE:
            ind(b,indent); buf_puts(b,"do_price(as_name("); gen_expr(b,s->a);
            buf_puts(b,"), as_num("); gen_expr(b,s->b); buf_puts(b,"));\n");
            break;
        case S_RESTOCK:
            ind(b,indent); buf_puts(b,"add_rule(as_name("); gen_expr(b,s->a);
            buf_puts(b,"), as_name("); gen_expr(b,s->b); buf_puts(b,"), as_units(");
            gen_expr(b,s->c); buf_puts(b,"), as_units("); gen_expr(b,s->d);
            buf_puts(b,"), as_name("); gen_expr(b,s->opt); buf_puts(b,"));\n");
            break;
        case S_DELIVER:
            ind(b,indent); buf_puts(b,"do_deliver(as_name("); gen_expr(b,s->b);
            buf_puts(b,"), as_name("); gen_expr(b,s->c); buf_puts(b,"), as_name(");
            gen_expr(b,s->d); buf_puts(b,"), as_units("); gen_expr(b,s->a); buf_puts(b,"), ");
            if (s->has_opt) { buf_puts(b,"as_name("); gen_expr(b,s->opt); buf_puts(b,")"); }
            else buf_puts(b,"(const char*)0");
            buf_puts(b,");\n");
            break;
        case S_REPORT:
            ind(b,indent);
            if (s->a) { buf_puts(b,"do_report(as_name("); gen_expr(b,s->a); buf_puts(b,"));\n"); }
            else buf_puts(b,"do_report((const char*)0);\n");
            break;
        /* entity declarations become registrations */
        case S_STORE: case S_WAREHOUSE: case S_SUPPLIER: case S_TRUCK: case S_PRODUCT:
            /* handled during registration pass; nothing inline */
            break;
        case S_FUNC:
            /* handled separately */
            break;
        default:
            die("internal: unexpected statement node %d", s->kind);
    }
}

/* extract a numeric/string property value from an entity decl, compile-time */
static double prop_num(Node *decl, const char *key, double dflt, int *found) {
    for (size_t i=0;i<decl->nprops;i++) if (!strcmp(decl->props[i].key,key)) {
        Node *v = decl->props[i].val;
        if (v->kind != E_NUM) die("line %d: property '%s' must be a number literal", decl->line, key);
        if (found) *found = 1;
        return v->num;
    }
    if (found) *found = 0;
    return dflt;
}
static const char *prop_str(Node *decl, const char *key) {
    for (size_t i=0;i<decl->nprops;i++) if (!strcmp(decl->props[i].key,key)) {
        Node *v = decl->props[i].val;
        if (v->kind != E_STR) die("line %d: property '%s' must be a string literal", decl->line, key);
        return v->str;
    }
    return NULL;
}

static void gen_registration(Buf *b, Node **prog, size_t n) {
    buf_puts(b, "static void ss_register(void) {\n");
    for (size_t i=0;i<n;i++) {
        Node *s = prog[i];
        switch (s->kind) {
            case S_STORE:     buf_printf(b,"    reg_loc(\"%s\", 0);\n", s->str); break;
            case S_WAREHOUSE: buf_printf(b,"    reg_loc(\"%s\", 1);\n", s->str); break;
            case S_PRODUCT: {
                int f; double price = prop_num(s,"price",0.0,&f);
                const char *cat = prop_str(s,"category");
                buf_printf(b,"    reg_prod(\"%s\", %.17g, ", s->str, price);
                if (cat) emit_cstr(b, cat); else buf_puts(b,"\"general\"");
                buf_puts(b,");\n");
                break;
            }
            case S_SUPPLIER: {
                int f; double lt = prop_num(s,"lead_time",1,&f);
                double rel = prop_num(s,"reliability",1.0,&f);
                buf_printf(b,"    reg_supp(\"%s\", %lldLL, %.17g);\n", s->str, (long long)lt, rel);
                break;
            }
            case S_TRUCK: {
                int f; double cap = prop_num(s,"capacity",1000,&f);
                buf_printf(b,"    reg_truck(\"%s\", %lldLL);\n", s->str, (long long)cap);
                break;
            }
            default: break;
        }
    }
    buf_puts(b, "}\n\n");
}

static void gen_function(Buf *b, Node *fn) {
    nameset_clear(&g_locals);
    for (size_t i=0;i<fn->nparams;i++) nameset_add(&g_locals, fn->params[i]);
    buf_printf(b, "static Value fn_%s(", fn->str);
    if (fn->nparams == 0) buf_puts(b, "void");
    else for (size_t i=0;i<fn->nparams;i++) {
        if (i) buf_puts(b, ", ");
        buf_printf(b, "Value ss_%s", fn->params[i]);
    }
    buf_puts(b, ") {\n");
    for (size_t i=0;i<fn->nparams;i++) buf_printf(b, "    (void)ss_%s;\n", fn->params[i]);
    gen_block_body(b, fn->a, 1);
    buf_puts(b, "    return v_nil();\n");
    buf_puts(b, "}\n\n");
}

static void gen_forward_decls(Buf *b, Node **prog, size_t n) {
    for (size_t i=0;i<n;i++) if (prog[i]->kind == S_FUNC) {
        Node *fn = prog[i];
        buf_printf(b, "static Value fn_%s(", fn->str);
        if (fn->nparams == 0) buf_puts(b, "void");
        else for (size_t j=0;j<fn->nparams;j++){ if(j) buf_puts(b,", "); buf_puts(b,"Value"); }
        buf_puts(b, ");\n");
    }
    buf_puts(b, "\n");
}

static const char *HELPERS =
"static Value ss_and(Value a, Value b){ return v_truthy(a)?b:a; }\n"
"static Value ss_or(Value a, Value b){ return v_truthy(a)?a:b; }\n"
"static Value ss_min(Value a, Value b){ return as_num(a)<=as_num(b)?a:b; }\n"
"static Value ss_max(Value a, Value b){ return as_num(a)>=as_num(b)?a:b; }\n\n";

static char *generate_c(Node **prog, size_t n) {
    /* registration pass: record entity kinds for compile-time resolution */
    for (size_t i=0;i<n;i++) {
        Node *s = prog[i];
        if (s->kind==S_STORE||s->kind==S_WAREHOUSE) ent_add(s->str,'l');
        else if (s->kind==S_PRODUCT) ent_add(s->str,'p');
        else if (s->kind==S_SUPPLIER) ent_add(s->str,'s');
        else if (s->kind==S_TRUCK) ent_add(s->str,'t');
        else if (s->kind==S_FUNC) nameset_add(&g_funcs, s->str);
        else if (s->kind==S_LET) nameset_add(&g_globals, s->str);
    }
    Buf b; buf_init(&b);
    buf_puts(&b, RUNTIME_PRELUDE);
    buf_puts(&b, RUNTIME_ENGINE);
    buf_puts(&b, HELPERS);
    gen_forward_decls(&b, prog, n);
    /* top-level let variables become file-scope globals so functions see them */
    for (size_t i=0;i<g_globals.n;i++)
        buf_printf(&b, "static Value ss_%s;\n", g_globals.names[i]);
    if (g_globals.n) buf_puts(&b, "\n");
    gen_registration(&b, prog, n);
    for (size_t i=0;i<n;i++) if (prog[i]->kind==S_FUNC) gen_function(&b, prog[i]);
    buf_puts(&b, "int main(void) {\n    ss_register();\n");
    nameset_clear(&g_locals);
    for (size_t i=0;i<n;i++) {
        Node *s = prog[i];
        if (s->kind==S_FUNC) continue;
        if (s->kind==S_STORE||s->kind==S_WAREHOUSE||s->kind==S_SUPPLIER||s->kind==S_TRUCK||s->kind==S_PRODUCT) continue;
        if (s->kind==S_LET) {
            /* assign into the file-scope global rather than redeclaring */
            ind(&b, 1); buf_printf(&b, "ss_%s = ", s->str); gen_expr(&b, s->a); buf_puts(&b, ";\n");
            continue;
        }
        gen_stmt(&b, s, 1);
    }
    buf_puts(&b, "    return 0;\n}\n");
    return b.data;
}

/* ------------------------------------------------------------------ */
/* driver                                                              */
/* ------------------------------------------------------------------ */
static char *read_file(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) die("cannot open '%s'", path);
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = xmalloc((size_t)sz + 1);
    size_t rd = fread(buf, 1, (size_t)sz, f);
    buf[rd] = 0;
    fclose(f);
    return buf;
}

static void write_file(const char *path, const char *data) {
    FILE *f = fopen(path, "wb");
    if (!f) die("cannot write '%s'", path);
    fputs(data, f);
    fclose(f);
}

static void usage(void) {
    fprintf(stderr,
        "shengc -- the ShengSiong native compiler\n"
        "usage: shengc <input.sheng> [-o output] [--emit-c] [--keep-c] [--run]\n");
    exit(2);
}

int main(int argc, char **argv) {
    const char *input = NULL, *output = NULL;
    int emit_c = 0, keep_c = 0, run = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-o")) { if (++i >= argc) usage(); output = argv[i]; }
        else if (!strcmp(argv[i], "--emit-c")) emit_c = 1;
        else if (!strcmp(argv[i], "--keep-c")) keep_c = 1;
        else if (!strcmp(argv[i], "--run")) run = 1;
        else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) usage();
        else if (argv[i][0] == '-') die("unknown option '%s'", argv[i]);
        else input = argv[i];
    }
    if (!input) usage();

    char *src = read_file(input);
    Lexer L; memset(&L, 0, sizeof L);
    L.src = src; L.len = strlen(src); L.line = 1;
    lex_run(&L);

    Parser P; memset(&P, 0, sizeof P);
    P.toks = L.toks; P.n = L.ntok;
    size_t nprog;
    Node **prog = parse_program(&P, &nprog);

    char *csrc = generate_c(prog, nprog);

    if (emit_c) { fputs(csrc, stdout); return 0; }

    /* default output name: input without extension */
    char outbuf[1024];
    if (!output) {
        strncpy(outbuf, input, sizeof outbuf - 1);
        outbuf[sizeof outbuf - 1] = 0;
        char *dot = strrchr(outbuf, '.');
        if (dot && strcmp(dot, ".sheng") == 0) *dot = 0;
        else strncat(outbuf, ".out", sizeof outbuf - strlen(outbuf) - 1);
        output = outbuf;
    }

    char cpath[1200];
    snprintf(cpath, sizeof cpath, "%s.c", output);
    write_file(cpath, csrc);

    const char *cc = getenv("CC");
    if (!cc || !cc[0]) cc = "cc";
    char cmd[4096];
    snprintf(cmd, sizeof cmd, "%s -O2 -std=c11 -w -o '%s' '%s'", cc, output, cpath);
    int rc = system(cmd);
    if (rc != 0) die("C backend compilation failed (cc rc=%d)", rc);

    if (!keep_c) remove(cpath);

    if (run) {
        char runcmd[1200];
        snprintf(runcmd, sizeof runcmd, "'%s'",
                 output[0]=='/' ? output : output);
        char rel[1210];
        if (output[0] != '/' && strchr(output, '/') == NULL) snprintf(rel, sizeof rel, "./%s", output);
        else snprintf(rel, sizeof rel, "%s", output);
        int r = system(rel);
        return r == 0 ? 0 : 1;
    }
    return 0;
}
