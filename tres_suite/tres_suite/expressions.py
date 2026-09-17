"""Restricted arithmetic expressions over spectral intensities.

Grammar (Python-like, parsed with :mod:`ast`, never executed with ``eval``)::

    expr := number | I(<wavelength_nm>) | (expr) | -expr
          | expr + expr | expr - expr | expr * expr | expr / expr

``I(x)`` is the intensity of the chosen source spectrum at ``x`` nm, obtained
by linear interpolation **inside** the measured wavelength range only.  A
wavelength outside the range, or a division by zero, makes the whole metric
*unavailable* with an explicit reason; no endpoint value or zero is fabricated.

Examples::

    GP        "(I(440) - I(490)) / (I(440) + I(490))"
    ratio     "I(510) / I(430)"
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

_ALLOWED_BINOPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}


class ExpressionError(ValueError):
    pass


@dataclass
class MetricResult:
    name: str
    expression: str
    value: Optional[float]
    available: bool
    reason: Optional[str] = None
    wavelengths_nm: List[float] = field(default_factory=list)
    intensities: Dict[str, Optional[float]] = field(default_factory=dict)
    interpolation: str = "linear, inside measured range only"
    source: str = "total_counts"

    def to_record(self) -> Dict[str, object]:
        return {
            "metric": self.name, "expression": self.expression, "value": self.value,
            "available": self.available, "reason": self.reason,
            "wavelengths_nm": list(self.wavelengths_nm), "intensities": dict(self.intensities),
            "interpolation": self.interpolation, "source": self.source,
        }


def parse_expression(text: str) -> ast.AST:
    """Parse and validate; raises :class:`ExpressionError` for anything outside the grammar."""
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"cannot parse expression {text!r}: {exc.msg}") from exc

    def check(node: ast.AST) -> None:
        if isinstance(node, ast.Expression):
            check(node.body)
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
                raise ExpressionError(f"only numeric constants are allowed, got {node.value!r}")
        elif isinstance(node, ast.BinOp):
            if type(node.op) not in _ALLOWED_BINOPS:
                raise ExpressionError("only +, -, * and / are allowed")
            check(node.left)
            check(node.right)
        elif isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.USub, ast.UAdd)):
                raise ExpressionError("only unary + and - are allowed")
            check(node.operand)
        elif isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id == "I"):
                raise ExpressionError("the only function allowed is I(<wavelength_nm>)")
            if len(node.args) != 1 or node.keywords:
                raise ExpressionError("I() takes exactly one positional wavelength argument")
            arg = node.args[0]
            if isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub) and isinstance(arg.operand, ast.Constant):
                arg = arg.operand
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)) and not isinstance(arg.value, bool)):
                raise ExpressionError("I() requires a numeric wavelength literal")
        else:
            raise ExpressionError(f"unsupported syntax: {type(node).__name__}")

    check(tree)
    return tree


def expression_wavelengths(text: str) -> List[float]:
    tree = parse_expression(text)
    out: List[float] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            arg = node.args[0]
            if isinstance(arg, ast.UnaryOp):
                out.append(-float(arg.operand.value))  # type: ignore[attr-defined]
            else:
                out.append(float(arg.value))  # type: ignore[attr-defined]
    return sorted(set(out))


def intensity_at(wavelengths_nm: np.ndarray, spectrum: np.ndarray, target_nm: float) -> Tuple[Optional[float], Optional[str]]:
    """Linear interpolation strictly inside the measured range; (None, reason) otherwise."""
    wl = np.asarray(wavelengths_nm, float)
    sp = np.asarray(spectrum, float)
    order = np.argsort(wl)
    wl, sp = wl[order], sp[order]
    if len(wl) == 0:
        return None, "no wavelengths"
    if target_nm < wl[0] or target_nm > wl[-1]:
        return None, f"wavelength {target_nm:g} nm is outside the measured range {wl[0]:g}-{wl[-1]:g} nm"
    good = np.isfinite(sp)
    if not np.all(good):
        # only the two bracketing points matter
        i = int(np.searchsorted(wl, target_nm))
        lo, hi = max(i - 1, 0), min(i, len(wl) - 1)
        if not (good[lo] and good[hi]):
            return None, f"intensity near {target_nm:g} nm is not finite"
    return float(np.interp(target_nm, wl, sp)), None


def evaluate_expression(name: str, text: str, wavelengths_nm: np.ndarray, spectrum: np.ndarray,
                        source: str = "total_counts") -> MetricResult:
    tree = parse_expression(text)
    needed = expression_wavelengths(text)
    intens: Dict[str, Optional[float]] = {}
    for w in needed:
        v, reason = intensity_at(wavelengths_nm, spectrum, w)
        intens[f"I({w:g})"] = v
        if v is None:
            return MetricResult(name, text, None, False, reason, needed, intens, source=source)

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.Call):
            arg = node.args[0]
            w = -float(arg.operand.value) if isinstance(arg, ast.UnaryOp) else float(arg.value)  # type: ignore[attr-defined]
            return float(intens[f"I({w:g})"])  # type: ignore[arg-type]
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if b == 0:
                raise ZeroDivisionError
            return a / b
        raise ExpressionError("unreachable")  # pragma: no cover

    try:
        val = ev(tree)
    except ZeroDivisionError:
        return MetricResult(name, text, None, False, "zero denominator", needed, intens, source=source)
    if not np.isfinite(val):
        return MetricResult(name, text, None, False, "non-finite result", needed, intens, source=source)
    return MetricResult(name, text, float(val), True, None, needed, intens, source=source)


def gp_expression(blue_nm: float = 440.0, red_nm: float = 490.0) -> str:
    return f"(I({blue_nm:g}) - I({red_nm:g})) / (I({blue_nm:g}) + I({red_nm:g}))"
