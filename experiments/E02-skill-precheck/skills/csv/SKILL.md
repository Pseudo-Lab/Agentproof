---
name: lab-numeric-parsing
description: Parse raw lab measurement strings with mixed numeric formats into clean floats before harmonization.
---

# Lab Numeric Parsing

### Step 1: Parse Numeric Formats

Parse all raw values to clean floats, handling:
- **Scientific notation**: `1.5e3` → `1500.0`
- **European decimals**: `12,34` → `12.34` (comma as decimal separator)
- **Whitespace**: `"  45.2  "` → `45.2`

```python

def parse_value(value):
    """
    Parse a raw value to float.

    Handles (in order):
    1. Scientific notation: 1.5e3, 3.338e+00 → float
    2. European decimals: 6,7396 → 6.7396
    3. Plain numbers with varying decimals
    """
    if value is None:
        return None

    s = str(value).strip()
    if s == '' or s.lower() == 'nan':
        return None

    # Handle scientific notation first
    if 'e' in s.lower():
        try:
            return float(s)
        except ValueError:
            pass

    # Handle European decimals (comma as decimal separator)
    # In this dataset, comma is used as decimal separator, not thousands
    if ',' in s:
        s = s.replace(',', '.')

    # Parse as float
    try:
        return float(s)
    except ValueError:
        return None
```
