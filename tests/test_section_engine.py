"""Tests for the section engine."""

import pytest
from datetime import date
from tally.section_engine import (
    parse_sections, load_sections, Section, SectionConfig, SectionParseError,
    evaluate_section_filter, evaluate_variables, classify_merchants,
    get_default_sections, get_default_sections_parsed,
)


# =============================================================================
# Test Data Helpers
# =============================================================================

def make_transactions(amounts, category="Food", subcategory="Grocery", tags=None):
    """Create test transactions with given amounts."""
    txns = []
    for i, amount in enumerate(amounts):
        txns.append({
            'amount': amount,
            'date': date(2025, (i % 12) + 1, 15),
            'category': category,
            'subcategory': subcategory,
            'merchant': 'Test Merchant',
            'tags': tags or [],
        })
    return txns


def make_merchant(name, amounts, category="Food", subcategory="Grocery", tags=None):
    """Create a merchant group with transactions."""
    return {
        'merchant': name,
        'category': category,
        'subcategory': subcategory,
        'transactions': make_transactions(amounts, category, subcategory, tags),
    }


# =============================================================================
# Parser Tests
# =============================================================================

class TestParseSections:
    """Test section file parsing."""

    def test_simple_section(self):
        config = parse_sections("""
[Bills]
filter: category == "Bills"
""")
        assert len(config.sections) == 1
        assert config.sections[0].name == "Bills"
        assert config.sections[0].filter_expr == 'category == "Bills"'

    def test_multiple_sections(self):
        config = parse_sections("""
[Bills]
filter: category == "Bills"

[Food]
filter: category == "Food"
""")
        assert len(config.sections) == 2
        assert config.sections[0].name == "Bills"
        assert config.sections[1].name == "Food"

    def test_global_variables(self):
        config = parse_sections("""
threshold = 1000
is_big = sum(payments) > threshold

[Big Purchases]
filter: is_big
""")
        assert len(config.global_variables) == 2
        assert "threshold" in config.global_variables
        assert "is_big" in config.global_variables
        assert len(config.sections) == 1

    def test_section_local_variables(self):
        config = parse_sections("""
[High Value]
avg_payment = sum(payments) / count(payments)
filter: avg_payment > 100
""")
        assert len(config.sections) == 1
        section = config.sections[0]
        assert "avg_payment" in section.variables
        assert section.variables["avg_payment"] == "sum(payments) / count(payments)"

    def test_comments_ignored(self):
        config = parse_sections("""
# This is a comment
[Section]
# Another comment
filter: True
""")
        assert len(config.sections) == 1
        assert config.sections[0].name == "Section"

    def test_blank_lines_ignored(self):
        config = parse_sections("""

[Section]

filter: True

""")
        assert len(config.sections) == 1

    def test_catch_all_filter(self):
        config = parse_sections("""
[Total]
filter: True
""")
        assert len(config.sections) == 1
        assert config.sections[0].filter_expr == "True"

    def test_complex_filter(self):
        config = parse_sections("""
[Monthly Bills]
filter: category == "Bills" and months >= 6
""")
        section = config.sections[0]
        assert 'category == "Bills"' in section.filter_expr
        assert "months >= 6" in section.filter_expr


class TestParseErrors:
    """Test parsing error handling."""

    def test_filter_outside_section(self):
        with pytest.raises(SectionParseError) as exc:
            parse_sections("""
filter: True
""")
        assert "outside of a section" in str(exc.value)

    def test_section_without_filter(self):
        with pytest.raises(SectionParseError) as exc:
            parse_sections("""
[Section]
""")
        assert "has no filter" in str(exc.value)

    def test_invalid_expression(self):
        with pytest.raises(SectionParseError) as exc:
            parse_sections("""
[Section]
filter: category = "Bills"
""")  # Using = instead of ==
        assert "Invalid filter expression" in str(exc.value)

    def test_invalid_variable_expression(self):
        with pytest.raises(SectionParseError) as exc:
            parse_sections("""
bad_var = [1, 2, 3]

[Section]
filter: True
""")
        assert "Invalid expression" in str(exc.value)


# =============================================================================
# Evaluation Tests
# =============================================================================

class TestEvaluateVariables:
    """Test variable evaluation."""

    def test_simple_variable(self):
        result = evaluate_variables(
            {"threshold": "500"},
            make_transactions([100, 200])
        )
        assert result["threshold"] == 500

    def test_variable_with_function(self):
        result = evaluate_variables(
            {"total": "sum(payments)"},
            make_transactions([100, 200, 300])
        )
        assert result["total"] == 600

    def test_chained_variables(self):
        result = evaluate_variables(
            {
                "total": "sum(payments)",
                "doubled": "total * 2"
            },
            make_transactions([100, 200])
        )
        assert result["total"] == 300
        assert result["doubled"] == 600

    def test_existing_variables(self):
        result = evaluate_variables(
            {"doubled": "threshold * 2"},
            make_transactions([100]),
            existing_vars={"threshold": 500}
        )
        assert result["doubled"] == 1000
        assert result["threshold"] == 500  # preserved


class TestEvaluateSectionFilter:
    """Test section filter evaluation."""

    def test_category_match(self):
        section = Section(
            name="Bills",
            filter_expr='category == "Bills"',
            filter_ast=None,
        )
        txns = make_transactions([100], category="Bills")
        assert evaluate_section_filter(section, txns) is True

    def test_category_no_match(self):
        section = Section(
            name="Bills",
            filter_expr='category == "Bills"',
            filter_ast=None,
        )
        txns = make_transactions([100], category="Food")
        assert evaluate_section_filter(section, txns) is False

    def test_catch_all(self):
        section = Section(
            name="Total",
            filter_expr='True',
            filter_ast=None,
        )
        txns = make_transactions([100], category="Anything")
        assert evaluate_section_filter(section, txns) is True

    def test_combined_filter(self):
        section = Section(
            name="Monthly Bills",
            filter_expr='category == "Bills" and months >= 3',
            filter_ast=None,
        )
        # 4 transactions in months 1, 2, 3, 4
        txns = make_transactions([100, 200, 300, 400], category="Bills")
        assert evaluate_section_filter(section, txns) is True

    def test_combined_filter_months_fail(self):
        section = Section(
            name="Monthly Bills",
            filter_expr='category == "Bills" and months >= 6',
            filter_ast=None,
        )
        # Only 2 transactions in months 1, 2
        txns = make_transactions([100, 200], category="Bills")
        assert evaluate_section_filter(section, txns) is False

    def test_tag_filter(self):
        section = Section(
            name="Recurring",
            filter_expr='"recurring" in tags',
            filter_ast=None,
        )
        txns = make_transactions([100], tags=["recurring", "monthly"])
        assert evaluate_section_filter(section, txns) is True

    def test_sum_filter(self):
        section = Section(
            name="Big",
            filter_expr='sum(payments) > 500',
            filter_ast=None,
        )
        txns = make_transactions([100, 200, 300])  # sum = 600
        assert evaluate_section_filter(section, txns) is True

    def test_with_global_variables(self):
        section = Section(
            name="Big",
            filter_expr='sum(payments) > threshold',
            filter_ast=None,
        )
        txns = make_transactions([100, 200, 300])
        assert evaluate_section_filter(section, txns, global_vars={"threshold": 500}) is True
        assert evaluate_section_filter(section, txns, global_vars={"threshold": 700}) is False

    def test_with_local_variables(self):
        section = Section(
            name="High Average",
            filter_expr='avg_payment > 100',
            filter_ast=None,
            variables={"avg_payment": "sum(payments) / count(payments)"}
        )
        txns = make_transactions([100, 200, 300])  # avg = 200
        assert evaluate_section_filter(section, txns) is True


# =============================================================================
# Classification Tests
# =============================================================================

class TestClassifyMerchants:
    """Test merchant classification into sections."""

    def test_simple_classification(self):
        config = parse_sections("""
[Bills]
filter: category == "Bills"

[Food]
filter: category == "Food"
""")
        merchants = [
            make_merchant("Electric Co", [100], category="Bills"),
            make_merchant("Grocery Store", [50], category="Food"),
        ]
        result = classify_merchants(config, merchants)

        assert len(result["Bills"]) == 1
        assert result["Bills"][0]["merchant"] == "Electric Co"
        assert len(result["Food"]) == 1
        assert result["Food"][0]["merchant"] == "Grocery Store"

    def test_overlapping_sections(self):
        config = parse_sections("""
[Total]
filter: True

[Bills]
filter: category == "Bills"
""")
        merchants = [
            make_merchant("Electric Co", [100], category="Bills"),
        ]
        result = classify_merchants(config, merchants)

        # Should appear in both sections
        assert len(result["Total"]) == 1
        assert len(result["Bills"]) == 1

    def test_empty_section(self):
        config = parse_sections("""
[Bills]
filter: category == "Bills"

[Travel]
filter: category == "Travel"
""")
        merchants = [
            make_merchant("Electric Co", [100], category="Bills"),
        ]
        result = classify_merchants(config, merchants)

        assert len(result["Bills"]) == 1
        assert len(result["Travel"]) == 0

    def test_with_global_variables(self):
        config = parse_sections("""
threshold = 500

[Big Purchases]
filter: sum(payments) > threshold
""")
        merchants = [
            make_merchant("Big Store", [300, 400]),  # sum = 700
            make_merchant("Small Store", [50, 60]),  # sum = 110
        ]
        result = classify_merchants(config, merchants)

        assert len(result["Big Purchases"]) == 1
        assert result["Big Purchases"][0]["merchant"] == "Big Store"


# =============================================================================
# Default Sections Tests
# =============================================================================

class TestDefaultSections:
    """Test default sections configuration."""

    def test_get_default_sections(self):
        text = get_default_sections()
        assert "[Total]" in text
        assert "[Bills]" in text
        assert "filter:" in text

    def test_parse_default_sections(self):
        config = get_default_sections_parsed()
        assert len(config.sections) >= 5  # At least 5 sections

        # Find specific sections
        section_names = [s.name for s in config.sections]
        assert "Total" in section_names
        assert "Bills" in section_names
        assert "Groceries" in section_names
