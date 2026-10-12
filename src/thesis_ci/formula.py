"""The formula language of ``data: xbrl`` metric definitions (SPEC 9.1), parsed without ``eval``.

``parse(text)`` turns a formula such as ``sum_4q(operating_cash_flow - capex) / sum_4q(revenue)`` into a tree of
``Number``, ``Name``, ``Negate``, ``Binary``, ``Sum`` and ``At`` nodes, or raises ``FormulaError`` saying where the
text stops being a formula. This module knows the syntax only; ``metrics.py`` gives the names their meaning and
evaluates the tree over a companyfacts document.

The language:

- numbers (``1``, ``0.5``), names of quantities (``revenue``), ``+ - * /`` with the usual precedence, unary minus
  and parentheses;
- ``sum_4q(expr)``, the sum of ``expr`` over the trailing four fiscal quarters, and ``sum_<n>y(expr)``, its sum over
  the trailing n fiscal years (1 to 99);
- a time subscript after a name, a parenthesised expression or a sum: ``_t`` is the reading's own period, and
  ``_{t-4q}`` and ``_{t-1y}`` are the same period one fiscal year earlier. The growth forms ``x_t / x_{t-4q} - 1``
  and ``(a + b)_t / (a + b)_{t-1y} - 1`` are written with them, so a name never ends in ``_t``.

A formula is at most 1,000 characters long and nests parentheses, sums and signs at most 50 levels deep.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Union

MAX_LENGTH = 1000  # characters; formulas in real theses run to a few hundred
MAX_DEPTH = 50  # nested parentheses, sums and signs
SUM_RE = re.compile(r"^sum_(?:(4)q|([1-9][0-9]?)y)$")
TIME_RE = re.compile(r"^_(?:t|\{\s*t\s*(?:-\s*(\d+)\s*([qy])\s*)?\})$")
_SUBSCRIPT = r"_t(?![A-Za-z0-9_{])|_\{[^{}]*\}"
_TOKEN = re.compile(rf"""
    (?P<space>\s+)
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<stem>[A-Za-z][A-Za-z0-9_]*?)(?P<stem_time>{_SUBSCRIPT})
  | (?P<name>[A-Za-z][A-Za-z0-9_]*)
  | (?P<time>{_SUBSCRIPT})
  | (?P<op>[-+*/()])
""", re.VERBOSE)


class FormulaError(ValueError):
    """A formula that cannot be parsed, or that a definition cannot compute (with the reason)."""


@dataclass(frozen=True)
class Number:
    value: float
    text: str = field(compare=False)  # as written, for messages and bases


@dataclass(frozen=True)
class Name:
    name: str


@dataclass(frozen=True)
class Negate:
    operand: Node


@dataclass(frozen=True)
class Binary:
    op: str  # "+" | "-" | "*" | "/"
    left: Node
    right: Node


@dataclass(frozen=True)
class Sum:
    """``sum_4q(body)`` (count 4, unit "quarter") or ``sum_<n>y(body)`` (count n, unit "year")."""

    function: str
    count: int
    unit: str
    body: Node


@dataclass(frozen=True)
class At:
    """``body`` read ``years_back`` fiscal years before the period it is evaluated for (0 for ``_t``)."""

    body: Node
    years_back: int
    text: str = field(compare=False)  # as written: _{t-4q} and _{t-1y} mean the same


Node = Union[Number, Name, Negate, Binary, Sum, At]


@dataclass(frozen=True)
class _Token:
    kind: str  # "number" | "name" | "time" | "op" | "bad" (a character no token starts with) | "end"
    text: str
    pos: int  # 1-based character position in the formula


def _tokens(text: str) -> list[_Token]:
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:  # the parser reports it when it gets there, after any earlier mistake
            out.append(_Token("bad", text[pos], pos + 1))
            break
        if m.group("stem"):
            out.append(_Token("name", m.group("stem"), pos + 1))
            out.append(_Token("time", m.group("stem_time"), m.start("stem_time") + 1))
        elif m.lastgroup != "space":
            out.append(_Token(m.lastgroup or "op", m.group(), pos + 1))
        pos = m.end()
    out.append(_Token("end", "", len(text) + 1))
    return out


def _years_back(token: _Token) -> int:
    m = TIME_RE.match(re.sub(r"\s+", "", token.text))
    if m and m.group(1) is None:
        return 0
    if m and (m.group(1), m.group(2)) in (("4", "q"), ("1", "y")):
        return 1
    raise FormulaError(f"time subscript {token.text} at character {token.pos} is not one of _t, _{{t-4q}}, _{{t-1y}}")


class _Parser:
    """Recursive descent over this grammar::

        sum      := product (("+" | "-") product)*
        product  := unary (("*" | "/") unary)*
        unary    := ("-" | "+") unary | postfix
        postfix  := primary [time]
        primary  := number | name | function "(" sum ")" | "(" sum ")"
    """

    def __init__(self, text: str):
        self.tokens = _tokens(text)
        self.i = 0
        self.depth = 0

    def nest(self, token: _Token) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise FormulaError(f"the formula nests more than {MAX_DEPTH} levels deep at character {token.pos}")

    def peek(self) -> _Token:
        return self.tokens[self.i]

    def take(self) -> _Token:
        token = self.tokens[self.i]
        self.i += 1
        return token

    def expect_close(self, opened: _Token) -> None:
        token = self.take()
        if token.text != ")":
            raise FormulaError(f"{_describe(token)}: expected ')' to close the '(' at character {opened.pos}")

    def formula(self) -> Node:
        if self.peek().kind == "end":
            raise FormulaError("the formula is empty")
        node = self.additive()
        if self.peek().kind != "end":
            raise FormulaError(f"{_describe(self.peek())}: expected an operator or the end of the formula")
        return node

    def additive(self) -> Node:
        node = self.multiplicative()
        while self.peek().text in ("+", "-") and self.peek().kind == "op":
            op = self.take().text
            node = Binary(op, node, self.multiplicative())
        return node

    def multiplicative(self) -> Node:
        node = self.unary()
        while self.peek().text in ("*", "/") and self.peek().kind == "op":
            op = self.take().text
            node = Binary(op, node, self.unary())
        return node

    def unary(self) -> Node:
        if self.peek().kind == "op" and self.peek().text in ("-", "+"):
            sign = self.take()
            self.nest(sign)
            operand = self.unary()
            self.depth -= 1
            return Negate(operand) if sign.text == "-" else operand
        return self.postfix()

    def postfix(self) -> Node:
        node = self.primary()
        if self.peek().kind == "time":
            token = self.take()
            node = At(node, _years_back(token), token.text)
        return node

    def primary(self) -> Node:
        token = self.take()
        if token.kind == "number":
            return Number(float(token.text), token.text)
        if token.kind == "name":
            if self.peek().text == "(" and self.peek().kind == "op":
                m = SUM_RE.match(token.text)
                if m is None:
                    raise FormulaError(f"unknown function {token.text}() at character {token.pos}: the functions are "
                                       "sum_4q() and sum_<n>y()")
                opened = self.take()
                self.nest(opened)
                body = self.additive()
                self.expect_close(opened)
                self.depth -= 1
                count, unit = (4, "quarter") if m.group(1) else (int(m.group(2)), "year")
                return Sum(token.text, count, unit, body)
            return Name(token.text)
        if token.kind == "op" and token.text == "(":
            self.nest(token)
            body = self.additive()
            self.expect_close(token)
            self.depth -= 1
            return body
        raise FormulaError(f"{_describe(token)}: expected a number, a name, a function or '('")


def _describe(token: _Token) -> str:
    if token.kind == "end":
        return "the formula ends too early"
    return f"unexpected {token.text!r} at character {token.pos}"


def parse(text: str) -> Node:
    """The tree of a formula; raises FormulaError, with the position, when the text is not a formula."""
    if not isinstance(text, str):
        raise FormulaError("the formula is not a string")
    if len(text) > MAX_LENGTH:
        raise FormulaError(f"the formula is longer than {MAX_LENGTH:,} characters")
    return _Parser(text).formula()


def _nodes(node: Node) -> list[Node]:
    """Every node of a tree, parents before their children, left to right."""
    out = [node]
    if isinstance(node, Negate):
        out += _nodes(node.operand)
    elif isinstance(node, Binary):
        out += _nodes(node.left) + _nodes(node.right)
    elif isinstance(node, (Sum, At)):
        out += _nodes(node.body)
    return out


def names(node: Node) -> list[str]:
    """The names of quantities a tree reads, in the order they first appear."""
    return list(dict.fromkeys(n.name for n in _nodes(node) if isinstance(n, Name)))


def sums(node: Node) -> list[Sum]:
    """The sums in a tree, outermost first."""
    return [n for n in _nodes(node) if isinstance(n, Sum)]


def text(node: Node) -> str:
    """A tree written back as a formula, with only the parentheses it needs (for messages)."""

    def render(n: Node) -> tuple[str, int]:  # (text, precedence: 1 for + -, 2 for * /, 3 unary, 4 atom)
        if isinstance(n, Number):
            return n.text, 4
        if isinstance(n, Name):
            return n.name, 4
        if isinstance(n, Negate):
            inner, prec = render(n.operand)
            return "-" + (f"({inner})" if prec < 3 else inner), 3
        if isinstance(n, Sum):
            return f"{n.function}({render(n.body)[0]})", 4
        if isinstance(n, At):
            inner, prec = render(n.body)
            return (f"({inner})" if prec < 4 else inner) + n.text, 4
        prec = 1 if n.op in "+-" else 2
        (left, lp), (right, rp) = render(n.left), render(n.right)
        if lp < prec:
            left = f"({left})"
        if rp < prec or (rp == prec and n.op in "-/"):
            right = f"({right})"
        return f"{left} {n.op} {right}", prec

    return render(node)[0]
