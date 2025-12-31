"""
Configuration loader for spending analysis.

Loads settings from YAML config files.
"""

import os

from .format_parser import parse_format_string, is_special_parser_type, get_account_type_settings
from .classification_rules import load_rules, get_default_rules, write_default_rules, get_default_rules_parsed
from .section_engine import load_sections, get_default_sections_parsed, write_default_sections, SectionParseError

# Try to import yaml, fall back to simple parsing if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def load_yaml_simple(filepath):
    """Simple YAML parser for basic key-value configs (fallback if PyYAML not installed)."""
    config = {}
    current_list_key = None
    current_list = []
    current_item = {}

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            # Skip comments and empty lines
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            # Check indentation level
            indent = len(line) - len(line.lstrip())

            # Handle list items
            if stripped.startswith('- '):
                if current_list_key:
                    if current_item:
                        current_list.append(current_item)
                        current_item = {}
                    # Parse the item
                    item_content = stripped[2:].strip()
                    if ':' in item_content:
                        key, value = item_content.split(':', 1)
                        current_item[key.strip()] = value.strip()
                continue

            # Handle nested list item properties
            if indent > 2 and current_list_key and ':' in stripped:
                key, value = stripped.split(':', 1)
                current_item[key.strip()] = value.strip()
                continue

            # Handle top-level key-value pairs
            if ':' in stripped and indent == 0:
                # Save any pending list
                if current_list_key and current_list:
                    if current_item:
                        current_list.append(current_item)
                    config[current_list_key] = current_list
                    current_list = []
                    current_item = {}
                    current_list_key = None

                key, value = stripped.split(':', 1)
                key = key.strip()
                value = value.strip()

                if value:
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    config[key] = value
                else:
                    # This might be a list
                    current_list_key = key

    # Save any pending list
    if current_list_key:
        if current_item:
            current_list.append(current_item)
        if current_list:
            config[current_list_key] = current_list

    return config


def load_settings(config_dir, settings_file='settings.yaml'):
    """Load main settings from settings.yaml (or specified file)."""
    settings_path = os.path.join(config_dir, settings_file)

    if not os.path.exists(settings_path):
        raise FileNotFoundError(f"Settings file not found: {settings_path}")

    if HAS_YAML:
        with open(settings_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    else:
        return load_yaml_simple(settings_path)


def resolve_source_format(source, warnings=None):
    """
    Resolve the format specification for a data source.

    Handles two configuration styles:
    - type: 'amex' or 'boa' (predefined parsers, backward compatible)
    - format: '{date:%m/%d/%Y}, {description}, {amount}' (custom format string)

    For custom formats, also supports:
    - columns.description: Template for combining custom captures
      Example: "{merchant} ({type})" when format uses {type}, {merchant}

    Args:
        source: Data source configuration dict
        warnings: Optional list to append deprecation warnings to

    Returns the source dict with additional keys:
    - '_parser_type': 'amex', 'boa', or 'generic'
    - '_format_spec': FormatSpec object (for generic parser) or None
    """
    source = source.copy()
    source_name = source.get('name', 'unknown')

    if 'format' in source:
        # Custom format string provided
        format_str = source['format']

        # Check for deprecated {-amount} syntax
        if '{-amount}' in format_str and warnings is not None:
            warnings.append({
                'type': 'deprecated',
                'source': source_name,
                'feature': '{-amount}',
                'message': f"Source '{source_name}' uses deprecated {{-amount}} syntax.",
                'suggestion': "Use 'account_type: bank' instead, which handles sign negation and filters income.",
                'example': f"  - name: {source_name}\n    account_type: bank\n    format: \"{format_str.replace('{-amount}', '{amount}')}\"",
            })

        # Check for columns.description template
        columns = source.get('columns', {})
        description_template = columns.get('description') if isinstance(columns, dict) else None

        try:
            format_spec = parse_format_string(format_str, description_template)

            # Apply account_type preset first (can be overridden by explicit settings)
            if 'account_type' in source:
                preset = get_account_type_settings(source['account_type'])
                format_spec.negate_amount = preset['negate_amount']
                format_spec.skip_negative = preset['skip_negative']

            # Apply explicit settings (override account_type defaults)
            if 'delimiter' in source:
                format_spec.delimiter = source['delimiter']
            if 'has_header' in source:
                format_spec.has_header = source['has_header']
            if 'negate_amount' in source:
                format_spec.negate_amount = source['negate_amount']
            if 'skip_negative' in source:
                format_spec.skip_negative = source['skip_negative']

            source['_format_spec'] = format_spec
            source['_parser_type'] = 'generic'
        except ValueError as e:
            raise ValueError(f"Invalid format for source '{source_name}': {e}")

    elif 'type' in source:
        source_type = source['type'].lower()

        if is_special_parser_type(source_type):
            # Use legacy parser (amex, boa) - add deprecation warning
            if warnings is not None:
                warnings.append({
                    'type': 'deprecated',
                    'source': source_name,
                    'feature': f'type: {source_type}',
                    'message': f"Source '{source_name}' uses deprecated 'type: {source_type}'.",
                    'suggestion': "Use 'account_type' and 'format' instead for better control.",
                    'example': f"  - name: {source_name}\n    account_type: credit_card\n    format: \"{{date:%m/%d/%Y}}, {{description}}, {{amount}}\"",
                })
            source['_parser_type'] = source_type
            source['_format_spec'] = None
        else:
            raise ValueError(f"Unknown source type: '{source_type}'. Use 'account_type' with a 'format' string.")

    else:
        raise ValueError(
            f"Data source '{source.get('name', 'unknown')}' must specify "
            "'type' or 'format'. Use 'tally inspect <file>' to determine the format."
        )

    return source


def load_config(config_dir, settings_file='settings.yaml'):
    """Load all configuration files.

    Args:
        config_dir: Path to config directory containing settings.yaml and CSV files.
        settings_file: Name of the settings file to load (default: settings.yaml)

    Returns:
        dict with all configuration values
    """
    config_dir = os.path.abspath(config_dir)

    if not os.path.isdir(config_dir):
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    # Load main settings
    config = load_settings(config_dir, settings_file)

    # Collect deprecation warnings
    warnings = []

    # Process data sources to resolve format specs
    if config.get('data_sources'):
        config['data_sources'] = [
            resolve_source_format(source, warnings=warnings)
            for source in config['data_sources']
        ]
    else:
        config['data_sources'] = []

    # Store warnings for CLI to display
    config['_warnings'] = warnings

    # Normalize home_locations to a set of uppercase location codes
    # Support legacy home_state for backward compatibility
    home_locations = config.get('home_locations', [])
    if not home_locations and 'home_state' in config:
        home_locations = [config['home_state']]
    if isinstance(home_locations, str):
        home_locations = [home_locations]
    config['home_locations'] = {loc.upper() for loc in home_locations}

    # Normalize travel_labels to uppercase keys
    travel_labels = config.get('travel_labels', {})
    config['travel_labels'] = {k.upper(): v for k, v in travel_labels.items()}

    # Store config dir for reference
    config['_config_dir'] = config_dir

    # Currency format for display (default: USD)
    config['currency_format'] = config.get('currency_format', '${amount}')

    # Load classification rules
    rules_file = os.path.join(config_dir, 'classification_rules.txt')
    if os.path.exists(rules_file):
        try:
            config['classification_rules'] = load_rules(rules_file)
            config['_rules_file'] = rules_file
        except Exception as e:
            warnings.append({
                'type': 'error',
                'source': 'classification_rules.txt',
                'message': f"Error loading classification rules: {e}",
                'suggestion': "Fix the syntax error or delete the file to regenerate defaults.",
            })
            config['classification_rules'] = get_default_rules_parsed()
            config['_rules_file'] = None
    else:
        # Create default rules file
        write_default_rules(rules_file)
        config['classification_rules'] = get_default_rules_parsed()
        config['_rules_file'] = rules_file
        # Don't warn - this is expected on first run

    # Load section definitions
    sections_file = os.path.join(config_dir, 'sections.txt')
    if os.path.exists(sections_file):
        try:
            config['sections'] = load_sections(sections_file)
            config['_sections_file'] = sections_file
        except SectionParseError as e:
            warnings.append({
                'type': 'error',
                'source': 'sections.txt',
                'message': f"Error loading sections: {e}",
                'suggestion': "Fix the syntax error or delete the file to regenerate defaults.",
            })
            config['sections'] = get_default_sections_parsed()
            config['_sections_file'] = None
    else:
        # Create default sections file
        write_default_sections(sections_file)
        config['sections'] = get_default_sections_parsed()
        config['_sections_file'] = sections_file
        # Don't warn - this is expected on first run

    return config
