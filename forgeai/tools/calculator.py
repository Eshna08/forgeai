"""Safe arithmetic via AST walking. Never eval()."""
from __future__ import annotations

import ast
import operator as op
import re

_BIN = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
        ast.FloorDiv: op.floordiv, ast.Mod: op.mod, ast.Pow: op.pow}
_UN = {ast.UAdd: op.pos, ast.USub: op.neg}
_FUNCS = {"round": round, "min": min, "max": max, "abs": abs}


def evaluate(expr: str) -> float:
    if not isinstance(expr, str) or len(expr) > 200:
        raise ValueError("expression must be a string of at most 200 characters")
    expr = re.sub(r"(?<=\d),(?=\d{3}\b)", "", expr).replace("^", "**").replace("×", "*")
    tree = ast.parse(expr, mode="eval")

    def ev(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and (abs(b) > 100 or abs(a) > 1e6):
                raise ValueError("exponent too large")
            return _BIN[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UN:
            return _UN[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError(f"unsupported expression element: {type(n).__name__}")

    result = ev(tree)
    return round(float(result), 6)


def run(args: dict, ctx: dict) -> dict:
    expr = args.get("expression") or args.get("expr") or ""
    return {"expression": expr, "result": evaluate(expr)}


SPEC = {
    "name": "calculator",
    "description": "Evaluate an arithmetic expression (+ - * / ** % round min max abs). Use for totals, discounts, quantities.",
    "args": {"expression": "string, e.g. '4 * 412.50 * 0.95'"},
    "run": run,
}
