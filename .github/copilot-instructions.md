# GitHub Copilot Instructions

## Project Overview
This is the VSME Digital Template to XBRL Converter developed by EFRAG. It converts Excel templates with named ranges into XBRL (eXtensible Business Reporting Language) format for sustainability reporting compliance.

## Technology Stack
- **Backend**: Python 3.11+ with Flask web framework
- **Frontend**: HTML/Jinja2 templates with Tailwind CSS 4.x
- **Data Processing**: openpyxl for Excel processing, Arelle for XBRL validation
- **Key Libraries**: pydantic, python-dateutil, babel, ixbrl-viewer
- **Testing**: pytest with unit and integration tests

## Project Structure
- `src/mireport/`: Main application package
- `scripts/`: Command-line utilities for conversion
- `tests/`: Unit and integration tests
- `digital-templates/`: Excel template samples
- `src/mireport/data/`: Taxonomies and configuration files
- `src/mireport/templates/`: Jinja2 HTML templates
- `src/mireport/static/`: CSS and JavaScript assets

## Coding Standards & Conventions

### Python Code
- Follow PEP 8 style guidelines
- Use type hints with pydantic models where applicable
- Prefer explicit imports over wildcard imports
- Use descriptive variable and function names
- Add docstrings to all public functions and classes
- Handle exceptions gracefully with appropriate logging

### Excel Processing
- Always validate named ranges before processing
- Use openpyxl for Excel file manipulation
- Map Excel named ranges to VSME taxonomy elements
- Validate data types and formats before conversion

### XBRL/XML Handling
- Use Arelle for XBRL validation and processing
- Follow XBRL best practices for element mapping
- Ensure proper namespace handling in XML output
- Validate against VSME taxonomy specifications

### Flask Web Application
- Use Jinja2 templates with proper escaping
- Implement proper session management
- Handle file uploads securely
- Provide clear error messages to users
- Use flash messages for user feedback

### Frontend (HTML/CSS)
- Use Tailwind CSS utility classes
- Follow responsive design principles
- Keep templates modular with `_macros.html.jinja`
- Ensure accessibility standards compliance

## Key Patterns to Follow

### Error Handling
```python
try:
    with resultBuilder.processingContext("Processing Excel file") as pc:
        excel = ExcelProcessor(file_path, resultBuilder, VSME_DEFAULTS)
        report = excel.populateReport()
        # Processing logic...
except Exception as e:
    message = next(iter(e.args), "")
    resultBuilder.addMessage(
        f"Exception encountered during processing. {message=}",
        Severity.ERROR,
        MessageType.Conversion,
    )
    L.exception("Exception encountered", exc_info=e)
```

### Configuration Management
- Use environment variables for configuration
- Provide sensible defaults
- Document all configuration options

### File Processing
- Always validate file extensions and MIME types
- Use temporary files for processing
- Clean up resources after processing
- Implement proper file size limits

### Testing
- Write unit tests for all business logic
- Use integration tests for end-to-end workflows
- Mock external dependencies in tests
- Test both success and failure scenarios

## Common Tasks & Patterns

### Adding New Excel Template Support
1. Update `src/mireport/data/excel_templates/` with new template configuration
2. Add validation rules in `excelprocessor.py`
3. Update taxonomy mappings if needed
4. Add corresponding unit tests

### Extending XBRL Output
1. Modify `xbrlreport.py` for new output formats
2. Update templates in `inline_report_templates/`
3. Ensure Arelle validation passes
4. Add integration tests

### Web Interface Changes
1. Update Jinja2 templates in `src/mireport/templates/`
2. Use Tailwind CSS classes for styling
3. Update Flask routes in `webapp.py`
4. Test file upload and conversion workflows

## Dependencies & Versions
- Maintain Python 3.11+ compatibility
- Keep Arelle version up to date for XBRL compliance
- Use specific versions for critical dependencies
- Test with latest Excel template versions

## Security Considerations
- Validate all file uploads
- Sanitize user inputs
- Use secure session management
- Implement proper error handling without exposing internals
- Validate XBRL output against taxonomies

## Performance Guidelines
- Stream large file processing where possible
- Use appropriate caching for taxonomy data
- Optimize Excel reading operations
- Monitor memory usage for large templates

## Documentation
- Update README.md for major changes
- Document API changes in docstrings
- Maintain inline comments for complex logic
- Update configuration examples when needed

## When suggesting code:
- Prioritize maintainability and readability
- Consider XBRL standards compliance
- Ensure proper error handling
- Follow the established patterns in the codebase
- Test suggestions against sample Excel templates