This PR implements a complete JSON processing system for the VSME Digital Template to XBRL Converter, providing an alternative to Excel templates for sustainability reporting data input.

## Overview

The implementation adds full JSON support parallel to the existing Excel functionality, enabling users to submit VSME sustainability data in structured JSON format. This provides better programmatic integration, version control compatibility, and automated processing capabilities.

## Key Features

### 🔧 Core Implementation
- **JsonProcessor Class**: Complete parallel implementation to `ExcelProcessor` with 584 lines of code
- **Fact Generation**: Supports all VSME concept types (numeric, text, dates, enumerations, monetary)
- **Complex Values**: Handles values with units and dimensions: `{"value": 1250.5, "unit": "tCO2e"}`
- **Configuration Processing**: Mirrors ExcelProcessor patterns for consistency

### 🌐 Web Interface Integration
- **Dual File Support**: Upload form now accepts both `.xlsx` and `.json` files
- **Seamless Processing**: Same conversion pipeline handles both formats
- **Enhanced UI**: Updated instructions and user guidance for JSON format

### 🚀 REST API
Three new endpoints for programmatic access:
- `POST /api/convert` - Convert JSON data to XBRL with multiple output formats
- `GET /api/schema` - Retrieve JSON schema for validation
- `GET /api/example` - Get example JSON file with sample data

### 🛠️ Command Line Tools
- **CLI Script**: `scripts/parse-json-and-ixbrl.py` with full feature parity to Excel script
- **Batch Processing**: Supports automation and integration workflows

## Data Structure

The JSON format follows this structure:

```json
{
  "metadata": {
    "entity": {
      "name": "Sustainable Corp Ltd",
      "identifier": "12345678901234567890"
    },
    "reportingPeriod": {
      "start": "2024-01-01",
      "end": "2024-12-31"
    }
  },
  "namedRanges": {
    "ScopeOneGrossGhgEmissions": {
      "value": 1250.5,
      "unit": "tCO2e"
    },
    "NumberOfEmployees": 250
  }
}
```

## Documentation & Testing

- **Complete Documentation**: README-JSON.md with usage examples and migration guide
- **JSON Schema**: Full validation schema (254 lines) ensuring data integrity
- **Example Data**: Realistic sustainability data example (155 lines)
- **Comprehensive Testing**: Unit tests and integration tests with 100% pass rate
- **API Documentation**: Complete examples for all endpoints

## Technical Details

- **Zero Breaking Changes**: Existing Excel functionality remains unchanged
- **Error Handling**: Comprehensive validation and error reporting
- **Performance**: Optimized JSON processing often faster than Excel parsing
- **Standards Compliance**: Full XBRL taxonomy compliance maintained

## Usage Examples

### Web Interface
Upload JSON files directly through the existing web interface alongside Excel files.

### API Usage
```bash
curl -X POST -H "Content-Type: application/json" \
  -d @sustainability-data.json \
  http://localhost:5000/api/convert?format=zip
```

### Command Line
```bash
python ./scripts/parse-json-and-ixbrl.py data.json output.html
```

This implementation significantly enhances the converter's capabilities while maintaining full backward compatibility, making it suitable for both manual data entry and automated sustainability reporting workflows.

Fixes #1.

> [!WARNING]
>
> <details>
> <summary>Firewall rules blocked me from connecting to one or more addresses (expand for details)</summary>
>
> #### I tried to connect to the following addresses, but was blocked by firewall rules:
>
> - `code.blinkace.com`
    >   - Triggering command: `/usr/lib/git-core/git-remote-https origin REDACTED` (dns block)
>
> If you need me to access, download, or install something from one of these locations, you can either:
>
> - Configure [Actions setup steps](https://gh.io/copilot/actions-setup-steps) to set up my environment, which run before the firewall is enabled
> - Add the appropriate URLs or hosts to the custom allowlist in this repository's [Copilot coding agent settings](https://github.com/kahriman/jconverter/settings/copilot/coding_agent) (admins only)
>
> </details>

<!-- START COPILOT CODING AGENT TIPS -->
---

✨ Let Copilot coding agent [set things up for you](https://github.com/kahriman/jconverter/issues/new?title=✨+Set+up+Copilot+instructions&body=Configure%20instructions%20for%20this%20repository%20as%20documented%20in%20%5BBest%20practices%20for%20Copilot%20coding%20agent%20in%20your%20repository%5D%28https://gh.io/copilot-coding-agent-tips%29%2E%0A%0A%3COnboard%20this%20repo%3E&assignees=copilot) — coding agent works faster and does higher quality work when set up for your repo.
