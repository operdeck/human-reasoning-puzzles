"""Model reports grouped by their expression-language source statements."""

from collections.abc import Sequence
from dataclasses import replace

from .core import DEFAULT_RULES, Rule
from .murdoku_lang import format_statement
from .murdoku_lower import ExpressionCompilation
from .report import describe as describe_model


def describe(compilation: ExpressionCompilation, rules: Sequence[Rule] = DEFAULT_RULES) -> str:
    """Describe each source statement and its emitted model primitives."""
    model = compilation.model
    lines = ["Expression statements", "---------------------"]
    for origin in compilation.origins:
        formula = format_statement(replace(origin.statement, wording=None))
        constraints = [
            model.constraints[index].name
            for index in sorted(compilation.constraint_origins)
            if origin in compilation.constraint_origins[index]
        ]
        relations = [
            model.relations[index].name
            for index in sorted(compilation.relation_origins)
            if origin in compilation.relation_origins[index]
        ]
        steps = sum(origin in sources for sources in compilation.initial_step_origins.values())
        lines.extend(("", f"{origin.label}: {formula}"))
        lines.append(
            f"  {len(constraints)} constraints, {len(relations)} relations, "
            f"{steps} initial deductions"
        )
        lines.extend(f"  constraint: {name}" for name in constraints)
        lines.extend(f"  relation: {name}" for name in relations)
    return "\n".join(lines) + "\n\n" + describe_model(model, rules)
