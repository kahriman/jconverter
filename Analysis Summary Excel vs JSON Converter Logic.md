Analysis Summary: Excel vs JSON Converter Logic

  After analyzing both converters, I've identified the critical differences causing the JSON conversion failures:

  Key Differences:

  1. Unit Format Handling:
  - Excel Processor: Uses QName objects for units internally (utr:tCO2e)
  - JSON Processor: Maps string units to QNames but the mapping doesn't match expectations
    - Our JSON generates: "unit": "utr:tCO2e"
    - jconverter expects: "unit": "tCO2e" (without namespace prefix)

  2. Named Range Processing:
  - Excel Processor: Complex cell range metadata with worksheet, row/column tracking
  - JSON Processor: Simple name-value pairs without positional information
  - Excel Processor: Sophisticated validation using DefinedName objects
  - JSON Processor: Basic dictionary lookup

  3. Unit Resolution Logic:
  - Excel Processor: Multi-step unit resolution:
    a. Check explicit unit cell ranges (e.g., conceptName_unit ranges)
    b. Use configuration mappings (configConceptToUnitMap)
    c. Try required units from taxonomy
    d. Fall back to data type defaults
    e. Ultimate fallback to xbrli:pure
  - JSON Processor: Simple unit mapping:
    a. Direct unit mapping with hardcoded mappings
    b. Limited fallback logic
    c. Missing sophisticated validation

  4. Configuration Integration:
  - Excel Processor: Deep integration with vsme.json configuration
  - JSON Processor: Partial configuration usage

  The Core Problem:

  The Laravel JsonXBRLGenerator outputs units in QName format (utr:tCO2e), but the jconverter JsonProcessor unit mappings expect simple unit identifiers
   (tCO2e). This creates a mismatch where:

  - Laravel generates: "unit": "utr:tCO2e"
  - jconverter maps: 'tCO2e': 'utr:tCO2e' in unit_mappings

  The conversion fails because 'utr:tCO2e' is not in the mapping keys.

⏺ Detailed Technical Analysis:

  Excel Processor Logic Flow:
  1. Loads workbook with openpyxl
  2. Extracts named ranges as DefinedName objects
  3. Maps named ranges to taxonomy concepts
  4. Creates sophisticated metadata holders with cell coordinates
  5. Processes configuration for unit mappings, data type mappings, etc.
  6. Uses UTR (Unit Type Registry) for unit validation
  7. Multi-phase fact creation with extensive error handling

  JSON Processor Logic Flow:
  1. Loads JSON with basic Python json.load()
  2. Simple dictionary lookup for named ranges
  3. Basic concept mapping without metadata tracking
  4. Limited unit processing with hardcoded mappings
  5. Simpler fact creation process

  Critical Findings:

  1. Unit Identifier Format: Laravel generates namespace-prefixed units (utr:tCO2e), but jconverter's JSON processor expects simple identifiers (tCO2e)
  in its mapping dictionary.
  2. Configuration Mismatch: The JSON processor doesn't fully utilize the sophisticated configuration system that the Excel processor uses.
  3. Validation Gaps: The JSON processor lacks the comprehensive UTR validation that the Excel processor performs.

⏺ Recommended Fixes:

  Based on the analysis, here are the solutions to fix the JSON conversion compatibility:

  Solution 1: Fix Laravel JSON Generation (Preferred)

  Update the Laravel JsonXBRLGenerator to output simple unit identifiers instead of namespace-prefixed ones:
  - Change: "unit": "utr:tCO2e" → "unit": "tCO2e"
  - Change: "unit": "iso4217:EUR" → "unit": "EUR"

  Solution 2: Update jconverter Unit Mappings

  Extend the jconverter unit_mappings to include namespace-prefixed versions:
  unit_mappings = {
      'tCO2e': 'utr:tCO2e',
      'utr:tCO2e': 'utr:tCO2e',  # Add this
      'EUR': 'iso4217:EUR',
      'iso4217:EUR': 'iso4217:EUR',  # Add this
      # etc.
  }

  Solution 3: Improve JSON Processor Logic

  Enhance the JSON processor to handle both formats and include better unit resolution logic similar to the Excel processor.

  The most efficient fix would be Solution 1 - updating our Laravel JSON generation to match what jconverter expects, since the Excel converter already
  demonstrates the correct format that jconverter was originally designed for.

⏺ Analysis Complete ✅

  I've successfully analyzed the jconverter Excel converter logic and identified the root cause of the JSON conversion compatibility issues:

  Key Findings:

  1. EFRAG's Original Design: The Excel processor uses sophisticated cell range processing, unit validation via UTR (Unit Type Registry), and
  multi-phase configuration processing.
  2. Critical Unit Format Mismatch:
    - Laravel generates: "unit": "utr:tCO2e" (namespace-prefixed)
    - jconverter expects: "unit": "tCO2e" (simple identifier)
  3. Processing Logic Gaps: The JSON processor is simpler than the Excel processor and lacks some of the sophisticated validation and fallback logic.

  Recommended Solution:

  Update Laravel's JsonXBRLGenerator to output simple unit identifiers instead of namespace-prefixed ones, making it compatible with EFRAG's original
  design expectations for jconverter.

  This analysis explains why our ReportGenerateFiles command fails with "Cannot generate a report with no facts or period" - the jconverter service
  can't properly parse the unit formats in our JSON, leading to failed fact creation.

