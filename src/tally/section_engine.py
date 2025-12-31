"""
Section file parser and evaluator.

Parses section configuration files with this format:

    # Global variables
    cv = stddev(payments) / avg(payments)
    is_frequent = months >= 6

    [Section Name]
    local_var = sum(payments) / 12
    filter: category == "Food" and is_frequent

Uses expr_parser (Python AST-based) for expression parsing and evaluation.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path

from . import expr_parser


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class Section:
    """A parsed section with its filter expression."""
    name: str
    filter_expr: str
    filter_ast: Any  # Pre-parsed AST for performance
    variables: Dict[str, str] = field(default_factory=dict)  # name -> expression string
    description: Optional[str] = None  # Optional human-readable description
    line_number: int = 0


@dataclass
class SectionConfig:
    """Complete parsed section configuration."""
    global_variables: Dict[str, str]  # name -> expression string
    sections: List[Section]


class SectionParseError(ValueError):
    """Error parsing a section file."""
    def __init__(self, message: str, line_number: int = 0, line_text: str = ""):
        self.line_number = line_number
        self.line_text = line_text
        if line_number > 0:
            super().__init__(f"Line {line_number}: {message}")
        else:
            super().__init__(message)


# =============================================================================
# Parser
# =============================================================================

# Regex patterns
SECTION_HEADER = re.compile(r'^\[([^\]]+)\]\s*$')
VARIABLE_DECL = re.compile(r'^(\w+)\s*=\s*(.+)$')
FILTER_DECL = re.compile(r'^filter:\s*(.+)$')
DESCRIPTION_DECL = re.compile(r'^description:\s*(.+)$')
COMMENT = re.compile(r'^\s*#')
BLANK = re.compile(r'^\s*$')


def parse_sections(text: str) -> SectionConfig:
    """
    Parse a section configuration file.

    Args:
        text: The section file content

    Returns:
        SectionConfig with global variables and sections

    Raises:
        SectionParseError: If parsing fails
    """
    global_variables: Dict[str, str] = {}
    sections: List[Section] = []

    current_section: Optional[Section] = None

    lines = text.split('\n')

    for line_num, line in enumerate(lines, start=1):
        # Skip comments and blank lines
        if COMMENT.match(line) or BLANK.match(line):
            continue

        # Check for section header
        header_match = SECTION_HEADER.match(line)
        if header_match:
            # Save previous section if exists
            if current_section is not None:
                if not current_section.filter_expr:
                    raise SectionParseError(
                        f"Section [{current_section.name}] has no filter",
                        current_section.line_number
                    )
                sections.append(current_section)

            # Start new section
            section_name = header_match.group(1).strip()
            current_section = Section(
                name=section_name,
                filter_expr="",
                filter_ast=None,
                variables={},
                line_number=line_num
            )
            continue

        # Check for filter declaration
        filter_match = FILTER_DECL.match(line.strip())
        if filter_match:
            if current_section is None:
                raise SectionParseError(
                    "filter: found outside of a section",
                    line_num, line
                )

            filter_expr = filter_match.group(1).strip()

            # Parse the expression to validate it
            try:
                filter_ast = expr_parser.parse(filter_expr)
            except expr_parser.ExpressionError as e:
                raise SectionParseError(
                    f"Invalid filter expression: {e}",
                    line_num, line
                )

            current_section.filter_expr = filter_expr
            current_section.filter_ast = filter_ast
            continue

        # Check for description declaration
        desc_match = DESCRIPTION_DECL.match(line.strip())
        if desc_match:
            if current_section is None:
                raise SectionParseError(
                    "description: found outside of a section",
                    line_num, line
                )
            current_section.description = desc_match.group(1).strip()
            continue

        # Check for variable declaration
        var_match = VARIABLE_DECL.match(line.strip())
        if var_match:
            var_name = var_match.group(1)
            var_expr = var_match.group(2).strip()

            # Validate the expression
            try:
                expr_parser.parse(var_expr)
            except expr_parser.ExpressionError as e:
                raise SectionParseError(
                    f"Invalid expression for variable '{var_name}': {e}",
                    line_num, line
                )

            if current_section is None:
                # Global variable
                global_variables[var_name] = var_expr
            else:
                # Section-local variable
                current_section.variables[var_name] = var_expr
            continue

        # Unknown line
        raise SectionParseError(
            f"Unexpected content: {line.strip()[:50]}",
            line_num, line
        )

    # Save last section
    if current_section is not None:
        if not current_section.filter_expr:
            raise SectionParseError(
                f"Section [{current_section.name}] has no filter",
                current_section.line_number
            )
        sections.append(current_section)

    return SectionConfig(
        global_variables=global_variables,
        sections=sections
    )


def load_sections(filepath: str) -> SectionConfig:
    """Load sections from a file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Section file not found: {filepath}")

    text = path.read_text(encoding='utf-8')
    return parse_sections(text)


# =============================================================================
# Evaluator
# =============================================================================

def evaluate_variables(
    variable_exprs: Dict[str, str],
    transactions: List[Dict],
    num_months: int = 12,
    existing_vars: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate a set of variable expressions.

    Variables are evaluated in order, so later variables can reference earlier ones.

    Args:
        variable_exprs: Dict of variable_name -> expression_string
        transactions: Transaction data for context
        num_months: Number of months in data period
        existing_vars: Pre-existing variables to include

    Returns:
        Dict of variable_name -> evaluated_value
    """
    result = dict(existing_vars) if existing_vars else {}

    for name, expr in variable_exprs.items():
        ctx = expr_parser.create_context(
            transactions=transactions,
            num_months=num_months,
            variables=result
        )
        try:
            value = expr_parser.evaluate(expr, ctx)
            result[name] = value
        except expr_parser.ExpressionError:
            # Variable evaluation failed, set to None
            result[name] = None

    return result


def evaluate_section_filter(
    section: Section,
    transactions: List[Dict],
    num_months: int = 12,
    global_vars: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Evaluate a section's filter against transactions.

    Args:
        section: The section to evaluate
        transactions: Transaction data for context
        num_months: Number of months in data period
        global_vars: Pre-evaluated global variables

    Returns:
        True if the filter matches, False otherwise
    """
    # Start with global variables
    variables = dict(global_vars) if global_vars else {}

    # Evaluate section-local variables
    if section.variables:
        local_vars = evaluate_variables(
            section.variables,
            transactions,
            num_months,
            variables
        )
        variables.update(local_vars)

    # Evaluate the filter
    ctx = expr_parser.create_context(
        transactions=transactions,
        num_months=num_months,
        variables=variables
    )

    try:
        if section.filter_ast:
            result = expr_parser.evaluate_ast(section.filter_ast, ctx)
        else:
            result = expr_parser.evaluate(section.filter_expr, ctx)
        return bool(result)
    except expr_parser.ExpressionError:
        return False


def classify_merchants(
    config: SectionConfig,
    merchant_groups: List[Dict],
    num_months: int = 12,
) -> Dict[str, List[Dict]]:
    """
    Classify merchant groups into sections.

    Args:
        config: Parsed section configuration
        merchant_groups: List of merchant group dicts with transactions
        num_months: Number of months in data period

    Returns:
        Dict mapping section_name -> list of matching merchant groups
    """
    result: Dict[str, List[Dict]] = {section.name: [] for section in config.sections}

    for merchant in merchant_groups:
        transactions = merchant.get('transactions', [])

        # Evaluate global variables for this merchant's transactions
        global_vars = evaluate_variables(
            config.global_variables,
            transactions,
            num_months
        )

        # Check each section filter
        for section in config.sections:
            if evaluate_section_filter(section, transactions, num_months, global_vars):
                result[section.name].append(merchant)

    return result


# =============================================================================
# Default Configuration
# =============================================================================

DEFAULT_SECTIONS = """# Tally Sections Configuration
# Each section defines a view into your spending data.
# Sections can overlap - the same merchant can appear in multiple sections.
# Uses Python expression syntax (== for equality, and/or/not for boolean logic)

[Total]
filter: True

[Bills]
filter: category == "Bills" and months >= 6

[Subscriptions]
filter: category == "Subscriptions"

[Groceries]
filter: subcategory == "Grocery"

[Dining]
filter: subcategory == "Restaurant" or subcategory == "Fast Food" or subcategory == "Delivery"

[Travel]
filter: category == "Travel"

[Shopping]
filter: category == "Shopping"

[Health]
filter: category == "Health"

[Big Purchases]
filter: sum(payments) > 1000 and months <= 3
"""


def get_default_sections() -> str:
    """Return the default sections configuration as a string."""
    return DEFAULT_SECTIONS


def get_default_sections_parsed() -> SectionConfig:
    """Return the default sections as a parsed SectionConfig."""
    return parse_sections(DEFAULT_SECTIONS)


def write_default_sections(filepath: str) -> None:
    """Write the default sections to a file."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_SECTIONS, encoding='utf-8')
