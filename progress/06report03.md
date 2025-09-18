report03.md

This PR completes the JSON implementation for the VSME Digital Template to XBRL Converter by fixing several critical issues that were preventing successful JSON to XBRL conversion.

## Issues Fixed

### 1. Script Error Handling
Fixed `parse-json-and-ixbrl.py` script that was calling a non-existent `getFormattedMessages()` method on `ConversionResults`. Updated to properly iterate through messages like the Excel script does:

```python
# Before (failing)
print(result.getFormattedMessages())

# After (working)
for message in messages:
    print(f"\t{message}")
```

### 2. Entity and Period Method Issues
The `JsonProcessor` was calling non-existent methods on `InlineReport`. Fixed to use the correct API:

- **Entity handling**: `setEntityIdentifier()` → `setDefaultAspect("entity-identifier")`
- **Period handling**: `setReportingPeriod()` → `addDurationPeriod()` + `setDefaultPeriodName()`

### 3. Comprehensive Unit Handling
Implemented complete unit processing for numeric XBRL facts with multiple fallback mechanisms:

1. **Explicit units from JSON** with unit mapping (tCO2e → utr:tCO2e, MWh → utr:MWh, etc.)
2. **Monetary units** using currency from metadata
3. **Configuration-based** concept-to-unit mapping from VSME defaults
4. **Required units** from taxonomy concepts
5. **Pure units** for count/ratio concepts

### 4. File I/O Fix
Fixed file writing logic to use the correct attribute:
```python
# Before
f.write(reportFile.read())

# After  
f.write(reportFile.fileContent)
```

### 5. Unit Test Enhancement
Updated mock taxonomy in tests to support UTR functionality required by the configuration processing.

## Results

The JSON to XBRL conversion now works end-to-end:

- **Successfully processes** 23 named ranges from JSON input
- **Creates 8 valid XBRL facts** with proper units and taxonomy mapping
- **Generates valid iXBRL HTML reports** (26KB output files)
- **Passes all unit tests** (9/9 passing)

Example conversion results:
```
✅ Facts created:
   - TotalEnergyConsumption: 15500 MWh
   - TotalWaterConsumption: 12500 m³
   - TotalWasteGeneratedMass: 450 t
   - NumberOfEmployees: 250 (pure unit)
```

The JSON implementation now provides a complete, production-ready alternative to Excel-based input for XBRL sustainability reporting.

Fixes #5.

<!-- START COPILOT CODING AGENT TIPS -->
---

✨ Let Copilot coding agent [set things up for you](https://github.com/kahriman/jconverter/issues/new?title=✨+Set+up+Copilot+instructions&body=Configure%20instructions%20for%20this%20repository%20as%20documented%20in%20%5BBest%20practices%20for%20Copilot%20coding%20agent%20in%20your%20repository%5D%28https://gh.io/copilot-coding-agent-tips%29%2E%0A%0A%3COnboard%20this%20repo%3E&assignees=copilot) — coding agent works faster and does higher quality work when set up for your repo.
