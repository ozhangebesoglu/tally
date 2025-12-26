"""Tests for the inline modifier parser."""

import pytest
from datetime import date, timedelta

from tally.modifier_parser import (
    parse_pattern_with_modifiers,
    evaluate_amount_condition,
    evaluate_date_condition,
    check_all_conditions,
    ParsedPattern,
    AmountCondition,
    DateCondition,
    ModifierParseError,
)


class TestParsePatternWithModifiers:
    """Tests for parse_pattern_with_modifiers function."""

    def test_simple_pattern_no_modifiers(self):
        """Pattern without modifiers should return unchanged."""
        result = parse_pattern_with_modifiers('COSTCO')
        assert result.regex_pattern == 'COSTCO'
        assert result.amount_conditions == []
        assert result.date_conditions == []

    def test_complex_regex_no_modifiers(self):
        """Complex regex without modifiers should return unchanged."""
        result = parse_pattern_with_modifiers('COSTCO(?!.*GAS)')
        assert result.regex_pattern == 'COSTCO(?!.*GAS)'
        assert result.amount_conditions == []
        assert result.date_conditions == []

    def test_regex_char_class_not_confused_with_modifier(self):
        """Regex character class [A-Z] should not be parsed as modifier."""
        result = parse_pattern_with_modifiers('[A-Z]+COSTCO')
        assert result.regex_pattern == '[A-Z]+COSTCO'
        assert result.amount_conditions == []
        assert result.date_conditions == []

    def test_empty_pattern(self):
        """Empty pattern should return empty regex."""
        result = parse_pattern_with_modifiers('')
        assert result.regex_pattern == ''
        assert result.amount_conditions == []
        assert result.date_conditions == []


class TestAmountModifiers:
    """Tests for amount modifier parsing."""

    def test_amount_greater_than(self):
        """Parse [amount>N] modifier."""
        result = parse_pattern_with_modifiers('COSTCO[amount>200]')
        assert result.regex_pattern == 'COSTCO'
        assert len(result.amount_conditions) == 1
        assert result.amount_conditions[0].operator == '>'
        assert result.amount_conditions[0].value == 200.0

    def test_amount_greater_than_or_equal(self):
        """Parse [amount>=N] modifier."""
        result = parse_pattern_with_modifiers('COSTCO[amount>=200]')
        assert result.regex_pattern == 'COSTCO'
        assert len(result.amount_conditions) == 1
        assert result.amount_conditions[0].operator == '>='
        assert result.amount_conditions[0].value == 200.0

    def test_amount_less_than(self):
        """Parse [amount<N] modifier."""
        result = parse_pattern_with_modifiers('STARBUCKS[amount<10]')
        assert result.regex_pattern == 'STARBUCKS'
        assert len(result.amount_conditions) == 1
        assert result.amount_conditions[0].operator == '<'
        assert result.amount_conditions[0].value == 10.0

    def test_amount_less_than_or_equal(self):
        """Parse [amount<=N] modifier."""
        result = parse_pattern_with_modifiers('STARBUCKS[amount<=10]')
        assert result.regex_pattern == 'STARBUCKS'
        assert len(result.amount_conditions) == 1
        assert result.amount_conditions[0].operator == '<='
        assert result.amount_conditions[0].value == 10.0

    def test_amount_equals(self):
        """Parse [amount=N] modifier."""
        result = parse_pattern_with_modifiers('BESTBUY[amount=499.99]')
        assert result.regex_pattern == 'BESTBUY'
        assert len(result.amount_conditions) == 1
        assert result.amount_conditions[0].operator == '='
        assert result.amount_conditions[0].value == 499.99

    def test_amount_range(self):
        """Parse [amount:MIN-MAX] modifier."""
        result = parse_pattern_with_modifiers('RESTAURANT[amount:20-100]')
        assert result.regex_pattern == 'RESTAURANT'
        assert len(result.amount_conditions) == 1
        assert result.amount_conditions[0].operator == ':'
        assert result.amount_conditions[0].min_value == 20.0
        assert result.amount_conditions[0].max_value == 100.0

    def test_amount_with_complex_pattern(self):
        """Amount modifier with complex regex pattern."""
        result = parse_pattern_with_modifiers('COSTCO(?!GAS)[amount>200]')
        assert result.regex_pattern == 'COSTCO(?!GAS)'
        assert len(result.amount_conditions) == 1
        assert result.amount_conditions[0].operator == '>'

    def test_invalid_amount_modifier(self):
        """Invalid amount modifier should raise error."""
        with pytest.raises(ModifierParseError):
            parse_pattern_with_modifiers('COSTCO[amount>>100]')


class TestDateModifiers:
    """Tests for date modifier parsing."""

    def test_date_exact(self):
        """Parse [date=YYYY-MM-DD] modifier."""
        result = parse_pattern_with_modifiers('BESTBUY[date=2025-01-15]')
        assert result.regex_pattern == 'BESTBUY'
        assert len(result.date_conditions) == 1
        assert result.date_conditions[0].operator == '='
        assert result.date_conditions[0].value == date(2025, 1, 15)

    def test_date_range(self):
        """Parse [date:START..END] modifier."""
        result = parse_pattern_with_modifiers('SUB[date:2025-01-01..2025-06-30]')
        assert result.regex_pattern == 'SUB'
        assert len(result.date_conditions) == 1
        assert result.date_conditions[0].operator == ':'
        assert result.date_conditions[0].start_date == date(2025, 1, 1)
        assert result.date_conditions[0].end_date == date(2025, 6, 30)

    def test_date_relative(self):
        """Parse [date:lastNdays] modifier."""
        result = parse_pattern_with_modifiers('PURCHASE[date:last30days]')
        assert result.regex_pattern == 'PURCHASE'
        assert len(result.date_conditions) == 1
        assert result.date_conditions[0].operator == 'relative'
        assert result.date_conditions[0].relative_days == 30

    def test_month_modifier(self):
        """Parse [month=N] modifier."""
        result = parse_pattern_with_modifiers('HOLIDAY[month=12]')
        assert result.regex_pattern == 'HOLIDAY'
        assert len(result.date_conditions) == 1
        assert result.date_conditions[0].operator == 'month'
        assert result.date_conditions[0].month == 12

    def test_invalid_month(self):
        """Invalid month should raise error."""
        with pytest.raises(ModifierParseError):
            parse_pattern_with_modifiers('HOLIDAY[month=13]')

    def test_invalid_date_format(self):
        """Invalid date format should raise error."""
        with pytest.raises(ModifierParseError):
            parse_pattern_with_modifiers('PURCHASE[date=01-15-2025]')


class TestCombinedModifiers:
    """Tests for combined amount and date modifiers."""

    def test_amount_and_date(self):
        """Parse pattern with both amount and date modifiers."""
        result = parse_pattern_with_modifiers('BESTBUY[amount=499.99][date=2025-01-15]')
        assert result.regex_pattern == 'BESTBUY'
        assert len(result.amount_conditions) == 1
        assert len(result.date_conditions) == 1
        assert result.amount_conditions[0].value == 499.99
        assert result.date_conditions[0].value == date(2025, 1, 15)

    def test_complex_pattern_with_both_modifiers(self):
        """Complex regex with both modifiers."""
        result = parse_pattern_with_modifiers('COSTCO(?!GAS)[amount>200][date=2025-01-15]')
        assert result.regex_pattern == 'COSTCO(?!GAS)'
        assert len(result.amount_conditions) == 1
        assert len(result.date_conditions) == 1

    def test_multiple_amount_conditions(self):
        """Multiple amount modifiers (AND logic)."""
        result = parse_pattern_with_modifiers('PURCHASE[amount>50][amount<200]')
        assert result.regex_pattern == 'PURCHASE'
        assert len(result.amount_conditions) == 2


class TestEvaluateAmountCondition:
    """Tests for evaluate_amount_condition function."""

    def test_greater_than_true(self):
        """Amount greater than threshold."""
        cond = AmountCondition(operator='>', value=100)
        assert evaluate_amount_condition(150, cond) is True

    def test_greater_than_false(self):
        """Amount not greater than threshold."""
        cond = AmountCondition(operator='>', value=100)
        assert evaluate_amount_condition(100, cond) is False
        assert evaluate_amount_condition(50, cond) is False

    def test_greater_than_or_equal(self):
        """Amount greater than or equal to threshold."""
        cond = AmountCondition(operator='>=', value=100)
        assert evaluate_amount_condition(100, cond) is True
        assert evaluate_amount_condition(150, cond) is True
        assert evaluate_amount_condition(99, cond) is False

    def test_less_than(self):
        """Amount less than threshold."""
        cond = AmountCondition(operator='<', value=50)
        assert evaluate_amount_condition(25, cond) is True
        assert evaluate_amount_condition(50, cond) is False

    def test_less_than_or_equal(self):
        """Amount less than or equal to threshold."""
        cond = AmountCondition(operator='<=', value=50)
        assert evaluate_amount_condition(50, cond) is True
        assert evaluate_amount_condition(25, cond) is True
        assert evaluate_amount_condition(51, cond) is False

    def test_equals_exact(self):
        """Amount equals exact value."""
        cond = AmountCondition(operator='=', value=99.99)
        assert evaluate_amount_condition(99.99, cond) is True

    def test_equals_with_epsilon(self):
        """Amount equals with floating point tolerance."""
        cond = AmountCondition(operator='=', value=99.99)
        assert evaluate_amount_condition(99.991, cond) is True  # Within epsilon
        assert evaluate_amount_condition(100.00, cond) is False  # Outside epsilon

    def test_range_inclusive(self):
        """Amount within range (inclusive)."""
        cond = AmountCondition(operator=':', min_value=50, max_value=200)
        assert evaluate_amount_condition(50, cond) is True  # Lower bound
        assert evaluate_amount_condition(200, cond) is True  # Upper bound
        assert evaluate_amount_condition(100, cond) is True  # Middle
        assert evaluate_amount_condition(49, cond) is False  # Below
        assert evaluate_amount_condition(201, cond) is False  # Above


class TestEvaluateDateCondition:
    """Tests for evaluate_date_condition function."""

    def test_exact_date_match(self):
        """Date equals exact date."""
        cond = DateCondition(operator='=', value=date(2025, 1, 15))
        assert evaluate_date_condition(date(2025, 1, 15), cond) is True
        assert evaluate_date_condition(date(2025, 1, 16), cond) is False

    def test_date_range(self):
        """Date within range."""
        cond = DateCondition(
            operator=':',
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31)
        )
        assert evaluate_date_condition(date(2025, 1, 1), cond) is True  # Start
        assert evaluate_date_condition(date(2025, 1, 31), cond) is True  # End
        assert evaluate_date_condition(date(2025, 1, 15), cond) is True  # Middle
        assert evaluate_date_condition(date(2024, 12, 31), cond) is False  # Before
        assert evaluate_date_condition(date(2025, 2, 1), cond) is False  # After

    def test_relative_days(self):
        """Date within last N days."""
        cond = DateCondition(operator='relative', relative_days=30)
        today = date.today()
        assert evaluate_date_condition(today, cond) is True
        assert evaluate_date_condition(today - timedelta(days=15), cond) is True
        assert evaluate_date_condition(today - timedelta(days=30), cond) is True
        assert evaluate_date_condition(today - timedelta(days=31), cond) is False

    def test_month_match(self):
        """Date in specific month."""
        cond = DateCondition(operator='month', month=12)
        assert evaluate_date_condition(date(2025, 12, 1), cond) is True
        assert evaluate_date_condition(date(2025, 12, 25), cond) is True
        assert evaluate_date_condition(date(2024, 12, 15), cond) is True  # Any year
        assert evaluate_date_condition(date(2025, 11, 30), cond) is False


class TestCheckAllConditions:
    """Tests for check_all_conditions function."""

    def test_no_conditions(self):
        """Pattern with no conditions always passes."""
        parsed = ParsedPattern(regex_pattern='COSTCO')
        assert check_all_conditions(parsed, None, None) is True
        assert check_all_conditions(parsed, 100, date(2025, 1, 15)) is True

    def test_amount_condition_passes(self):
        """Amount condition that passes."""
        parsed = parse_pattern_with_modifiers('COSTCO[amount>100]')
        assert check_all_conditions(parsed, 150, None) is True

    def test_amount_condition_fails(self):
        """Amount condition that fails."""
        parsed = parse_pattern_with_modifiers('COSTCO[amount>100]')
        assert check_all_conditions(parsed, 50, None) is False

    def test_amount_condition_no_amount_provided(self):
        """Amount condition with no amount provided fails."""
        parsed = parse_pattern_with_modifiers('COSTCO[amount>100]')
        assert check_all_conditions(parsed, None, date(2025, 1, 15)) is False

    def test_date_condition_passes(self):
        """Date condition that passes."""
        parsed = parse_pattern_with_modifiers('BESTBUY[date=2025-01-15]')
        assert check_all_conditions(parsed, None, date(2025, 1, 15)) is True

    def test_date_condition_fails(self):
        """Date condition that fails."""
        parsed = parse_pattern_with_modifiers('BESTBUY[date=2025-01-15]')
        assert check_all_conditions(parsed, None, date(2025, 1, 16)) is False

    def test_date_condition_no_date_provided(self):
        """Date condition with no date provided fails."""
        parsed = parse_pattern_with_modifiers('BESTBUY[date=2025-01-15]')
        assert check_all_conditions(parsed, 100, None) is False

    def test_combined_conditions_both_pass(self):
        """Combined conditions where both pass."""
        parsed = parse_pattern_with_modifiers('BESTBUY[amount=499.99][date=2025-01-15]')
        assert check_all_conditions(parsed, 499.99, date(2025, 1, 15)) is True

    def test_combined_conditions_amount_fails(self):
        """Combined conditions where amount fails."""
        parsed = parse_pattern_with_modifiers('BESTBUY[amount=499.99][date=2025-01-15]')
        assert check_all_conditions(parsed, 100, date(2025, 1, 15)) is False

    def test_combined_conditions_date_fails(self):
        """Combined conditions where date fails."""
        parsed = parse_pattern_with_modifiers('BESTBUY[amount=499.99][date=2025-01-15]')
        assert check_all_conditions(parsed, 499.99, date(2025, 1, 16)) is False
