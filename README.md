# Tally

**A local rule engine for transaction classification.** Pair it with an LLM to eliminate the manual work.

Works with Claude Code, Codex, Copilot, Cursor, or a local model.

👉 **[Website](https://tallyai.money)** · **[Releases](https://github.com/davidfowl/tally/releases)**

## Install

**Linux/macOS:**
```bash
curl -fsSL https://tallyai.money/install.sh | bash
```

**Windows PowerShell:**
```powershell
irm https://tallyai.money/install.ps1 | iex
```

**With uv:**
```bash
uv tool install git+https://github.com/davidfowl/tally
```

## Quick Start

```bash
tally init ./my-budget      # Create budget folder
cd my-budget
tally workflow              # See next steps
```

## Commands

| Command | Description |
|---------|-------------|
| `tally init [dir]` | Set up a new budget folder |
| `tally workflow` | Show next steps (detects setup state, unknown merchants) |
| `tally run` | Parse transactions and generate HTML report |
| `tally run --format json` | Output analysis as JSON with reasoning |
| `tally explain` | Explain why merchants are classified the way they are |
| `tally explain <merchant>` | Explain specific merchant's classification |
| `tally discover` | Find uncategorized transactions (`--format json` for LLMs) |
| `tally inspect <csv>` | Show CSV structure to build format string |
| `tally diag` | Debug config issues |
| `tally version` | Show version and check for updates |
| `tally update` | Update to latest version |

### Output Formats

Both `tally run` and `tally explain` support multiple output formats:

```bash
tally run --format json        # JSON with classification reasoning
tally run --format markdown    # Markdown report
tally run --format summary     # Text summary only
tally run -v                   # Verbose: include decision trace
tally run -vv                  # Very verbose: include thresholds, CV values
```

### Filtering

Filter output to specific classifications or categories:

```bash
tally run --format json --only monthly,variable   # Just these classifications
tally run --format json --category Food           # Just Food category
tally explain --classification monthly            # Explain all monthly merchants
tally explain --category Subscriptions            # Explain all subscriptions
```

## Configuration

### settings.yaml

```yaml
year: 2025
currency_format: "€{amount}"  # Optional: €1,234 or "{amount} zł" for 1,234 zł

data_sources:
  - name: AMEX
    file: data/amex.csv
    account_type: credit_card
    format: "{date:%m/%d/%Y},{description},{amount}"
  - name: Chase
    file: data/chase.csv
    account_type: credit_card
    format: "{date:%m/%d/%Y},{description},{amount}"
  - name: BofA Checking
    file: data/bofa.csv
    account_type: bank
    format: "{date:%m/%d/%Y},{description},{amount}"
  - name: German Bank
    file: data/german.csv
    account_type: bank
    format: "{date:%d.%m.%Y},{description},{amount}"
    decimal_separator: ","  # European format (1.234,56)
```

### Account Types

Use `account_type` to automatically handle sign conventions:

| Type | Behavior | Use For |
|------|----------|---------|
| `credit_card` | Keep signs as-is | Credit cards (charges positive, payments negative) |
| `bank` | Negate amounts, skip credits | Checking/savings (debits negative, deposits positive) |
| `brokerage` | Same as bank | Investment accounts |

The `account_type` sets sensible defaults that can be overridden:
- `negate_amount`: Flip the sign of amounts
- `skip_negative`: Skip negative amounts after negation (filters income/deposits)

Run `tally inspect <file>` to see suggested account type based on your data.

### Format Strings

| Token | Description |
|-------|-------------|
| `{date:%m/%d/%Y}` | Date with format |
| `{description}` | Transaction description |
| `{amount}` | Amount column |
| `{_}` | Skip column |
| `{custom_name}` | Capture column for use in description template |

> **Note:** Use `account_type` instead of `{-amount}` for sign handling. The `{-amount}` syntax is deprecated.

**Multi-column descriptions** - Some banks split info across columns:
```yaml
- name: European Bank
  file: data/bank.csv
  format: "{date:%d.%m.%Y},{_},{txn_type},{vendor},{_},{amount}"
  columns:
    description: "{vendor} ({txn_type})"  # Combines into "STORE NAME (Card payment)"
```

### merchant_categories.csv

```csv
Pattern,Merchant,Category,Subcategory,Tags
WHOLEFDS,Whole Foods,Food,Grocery,
UBER\s(?!EATS),Uber,Transport,Rideshare,business|reimbursable
UBER\s*EATS,Uber Eats,Food,Delivery,
NETFLIX,Netflix,Subscriptions,Streaming,entertainment|recurring
GITHUB,GitHub,Subscriptions,Software,business|recurring
COSTCO[amount>200],Costco Bulk,Shopping,Bulk,
```

Patterns are Python regex (case-insensitive). First match wins.

**Tags** are optional, pipe-separated labels for filtering:
- Use cases: `business`, `reimbursable`, `entertainment`, `recurring`, `tax-deductible`
- Filter in UI: Click tag badges or type `t:business` in search
- Filter in CLI: `tally explain --tags business,reimbursable`

**Inline modifiers** target specific transactions:
- `[amount>200]`, `[amount:50-100]` - Amount conditions
- `[date=2025-01-15]`, `[month=12]` - Date conditions

### sections.sections (Optional)

Define custom spending views using filter expressions. Create `config/sections.sections`:

```
[Every Month]
description: Consistent recurring (rent, utilities, subscriptions)
filter: months >= 6 and cv < 0.3

[Variable Recurring]
description: Frequent but inconsistent (groceries, shopping)
filter: months >= 6 and cv >= 0.3

[Periodic]
description: Quarterly or semi-annual (tuition, insurance)
filter: months >= 2 and months <= 5

[Large Purchases]
description: Big one-time expenses
filter: total > 1000 and months <= 2

[Tagged: Business]
description: Business expenses
filter: "business" in tags
```

**Primitives:**
| Name | Type | Description |
|------|------|-------------|
| `months` | int | Unique months with transactions |
| `total` | float | Sum of all payments |
| `cv` | float | Coefficient of variation (0 = consistent, >0.3 = variable) |
| `category` | str | Category (e.g., "Food") |
| `subcategory` | str | Subcategory (e.g., "Grocery") |
| `tags` | set | Tag strings from merchant rules |
| `payments` | list | All payment amounts |

**Functions:**
| Function | Description |
|----------|-------------|
| `sum(x)`, `avg(x)`, `count(x)` | Aggregation functions |
| `min(x)`, `max(x)`, `stddev(x)` | Statistical functions |
| `abs(x)`, `round(x)` | Math functions |
| `by(field)` | Group payments by field (month, year, week, day) |

**Grouping with `by()`:**

The `by()` function groups payments by time period. Aggregation functions auto-map over groups:
```
by("month")              # [[100, 200], [150], [175, 125]] - grouped payments
sum(by("month"))         # [300, 150, 300] - monthly totals
avg(sum(by("month")))    # 250 - average monthly spend
max(sum(by("month")))    # 300 - highest spending month
```

**Using variables for complex filters:**
```
# Global variables
monthly = sum(by("month"))
my_cv = stddev(monthly) / avg(monthly)
peak_ratio = max(monthly) / avg(monthly)

[Spiky Spending]
description: Months with unusually high spending
filter: peak_ratio > 2

[Consistent]
filter: my_cv < 0.3
```

**Advanced filter examples:**
```
# High-value inconsistent spending
filter: total > 5000 and cv >= 0.5

# Subscription-like (consistent, 6+ months)
filter: cv < 0.2 and months >= 6 and avg(payments) < 100

# Large single transactions
filter: max(payments) > 2000 and count(payments) <= 3

# Specific categories with thresholds
filter: category == "Food" and total > 500 and months >= 3

# Tag-based with amount filter
filter: "recurring" in tags and avg(payments) > 50

# Monthly analysis
filter: max(sum(by("month"))) > 1000
```

Sections can overlap - the same merchant can appear in multiple sections.

## For AI Agents

Run `tally workflow` at any time to see context-aware instructions:

```bash
tally workflow    # Shows next steps based on current state
```

The workflow command detects your setup state and shows relevant instructions:
- No config? → How to initialize
- No data sources? → How to configure them
- Unknown merchants? → Categorization workflow

**Key commands for agents:**
- `tally discover --format json` - Get unknown merchants with suggested patterns
- `tally run --format json -v` - Full analysis with classification reasoning
- `tally explain <merchant> -vv` - Why a merchant is classified (with rule info)
- `tally diag --format json` - Debug configuration issues

## Development Builds

Get the latest build from main branch:

**Update existing install:**
```bash
tally update --prerelease
```

**Fresh install (Linux/macOS):**
```bash
curl -fsSL https://tallyai.money/install.sh | bash -s -- --prerelease
```

**Fresh install (Windows):**
```powershell
iex "& { $(irm https://tallyai.money/install.ps1) } -Prerelease"
```

Dev builds are created automatically on every push to main. When running a dev version, `tally version` will notify you of newer dev builds.

## License

MIT
