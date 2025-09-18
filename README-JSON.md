# JSON Implementation for VSME XBRL Converter

This document describes the JSON implementation for the VSME (Voluntary Sustainability Reporting Standard for non-listed SMEs) to XBRL converter.

## Overview

The JSON implementation allows users to submit sustainability data in a structured JSON format instead of using Excel templates. This provides several advantages:

- **Programmatic Access**: Easy integration with automated systems and APIs
- **Version Control**: JSON files can be easily tracked in version control systems
- **Validation**: JSON schema validation ensures data integrity
- **Flexibility**: Easier to generate from various data sources

## JSON Schema

The JSON input must conform to a specific schema that mirrors the structure of the Excel Digital Template. The schema includes:

### Required Sections

1. **metadata**: Report metadata including entity information and reporting period
2. **namedRanges**: Key-value pairs mapping VSME taxonomy elements to their values

### Optional Sections

3. **tables**: Tabular data for multi-dimensional facts

## JSON Structure

```json
{
    "metadata": {
        "entryPoint": "template_reporting_schemaRef",
        "entity": {
            "name": "Example Corporation Ltd",
            "identifier": "12345678901234567890",
            "identifierScheme": "lei"
        },
        "reportingPeriod": {
            "start": "2024-01-01",
            "end": "2024-12-31"
        },
        "title": "Annual Sustainability Report 2024",
        "subtitle": "Prepared in accordance with the EFRAG VSME standard",
        "currency": "EUR"
    },
    "namedRanges": {
        "ScopeOneGrossGhgEmissions": {
            "value": 1250.5,
            "unit": "tCO2e"
        },
        "NumberOfEmployees": 250,
        "ReportingOrganisationLegalForm": "private limited liability undertaking"
    },
    "tables": {
        "EmployeeBreakdownTable": [
            {
                "Category": "Management",
                "TotalEmployees": 25,
                "FemaleEmployees": 12,
                "MaleEmployees": 13
            }
        ]
    }
}
```

## Usage Methods

### 1. Web Interface

Upload a `.json` file through the web interface at `/` alongside Excel files:

1. Visit the converter web application
2. Select your JSON file (`.json` extension)
3. Configure optional settings (locale, logo)
4. Submit for conversion
5. Download the generated XBRL files

### 2. Command Line

Use the dedicated JSON processing script:

```bash
python ./scripts/parse-json-and-ixbrl.py input.json output/
```

Options:
- `--output-locale`: Specify output locale (e.g., `en-GB`, `fr-FR`)
- `--force`: Overwrite existing output files
- `--devinfo`: Show developer information messages

### 3. REST API

Use the programmatic API for integration:

#### Convert JSON Data

```bash
POST /api/convert
Content-Type: application/json

{
    "metadata": { ... },
    "namedRanges": { ... }
}
```

Query parameters:
- `locale`: Output locale (optional)
- `format`: Output format (`zip`, `json`, `viewer`, `all`)

#### Get JSON Schema

```bash
GET /api/schema
```

Returns the JSON schema for validation.

#### Get Example JSON

```bash
GET /api/example
```

Returns an example JSON file with sample data.

## Named Ranges Mapping

Named ranges in JSON correspond directly to VSME taxonomy elements:

### Simple Values

```json
"NumberOfEmployees": 250
"CompanyDescription": "A sustainable technology company"
```

### Values with Units

```json
"ScopeOneGrossGhgEmissions": {
    "value": 1250.5,
    "unit": "tCO2e"
}
```

### Values with Dimensions

```json
"WasteByType": {
    "value": 150,
    "unit": "t",
    "dimensions": {
        "WasteTypeDimension": "Paper"
    }
}
```

## Validation

The JSON processor performs several validation steps:

1. **JSON Syntax**: Valid JSON format
2. **Schema Validation**: Conformance to the expected structure
3. **Required Fields**: Presence of mandatory metadata and namedRanges
4. **Taxonomy Mapping**: Verification that named ranges map to valid VSME concepts
5. **Data Types**: Appropriate data types for numeric, text, and boolean values
6. **Units**: Valid units for quantitative facts

## Error Handling

The system provides detailed error messages for:

- Invalid JSON syntax
- Missing required sections or fields
- Unmapped named ranges (concepts not found in taxonomy)
- Invalid units or data types
- Date format issues
- Entity identifier validation

## Advanced Features

### Table Processing

Complex tabular data can be represented in the `tables` section:

```json
"tables": {
    "EmployeeBreakdownTable": [
        {
            "Category": "Management",
            "TotalEmployees": 25,
            "FemaleEmployees": 12,
            "MaleEmployees": 13
        },
        {
            "Category": "Technical Staff", 
            "TotalEmployees": 150,
            "FemaleEmployees": 75,
            "MaleEmployees": 75
        }
    ]
}
```

### Localization

The processor supports multiple output locales for number formatting and language-specific elements:

```bash
# Command line
python ./scripts/parse-json-and-ixbrl.py data.json output/ --output-locale=de-DE

# API
POST /api/convert?locale=de-DE
```

## Migration from Excel

To migrate from Excel Digital Templates to JSON:

1. **Extract Data**: Use the Excel template to identify required named ranges
2. **Map Values**: Create JSON namedRanges section with corresponding values
3. **Add Metadata**: Include entity and reporting period information
4. **Validate**: Test with the JSON schema and example files
5. **Convert**: Process through the JSON converter

## Performance Considerations

- JSON processing is typically faster than Excel parsing
- Large datasets should use streaming for memory efficiency
- API endpoint includes rate limiting for production use
- Batch processing is supported for multiple conversions

## Troubleshooting

### Common Issues

1. **"No concept found for named range 'X'"**
   - Verify the named range exists in the VSME taxonomy
   - Check for typos in concept names
   - Ensure you're using the correct taxonomy version

2. **"Invalid JSON format"**
   - Validate JSON syntax using online validators
   - Check for missing commas, quotes, or brackets
   - Ensure proper UTF-8 encoding

3. **"Missing required section 'metadata'"**
   - Include all required metadata fields
   - Verify nested structure is correct

4. **"No facts found in JSON data"**
   - Ensure namedRanges section contains valid mappings
   - Check that values are not null or empty
   - Verify taxonomy concepts are correctly referenced

### Debugging

Enable developer information for detailed processing logs:

```bash
# Command line
python ./scripts/parse-json-and-ixbrl.py data.json output/ --devinfo

# Web interface
Add ?show_developer_messages=true to the results URL
```

## File Locations

- **JSON Schema**: `src/mireport/data/json_schema.json`
- **Example JSON**: `digital-templates/example-vsme-data.json`
- **JSON Processor**: `src/mireport/jsonprocessor.py`
- **CLI Script**: `scripts/parse-json-and-ixbrl.py`
- **Unit Tests**: `tests/unitTests/test_jsonprocessor.py`

## Future Enhancements

- Support for JSON-LD format
- Enhanced validation with taxonomy-specific rules
- Automatic Excel-to-JSON conversion utility
- Extended API with CRUD operations for data management
- Real-time validation during JSON editing