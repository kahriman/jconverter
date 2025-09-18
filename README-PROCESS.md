## The Excel-to-XBRL Conversion Process

1.  **Excel File Upload and Initialization**

    * The Excel file is uploaded via the Flask web app (`webapp.py`).
    * An `ExcelProcessor` is created with the file and default configuration (`VSME_DEFAULTS`).
    * The file is loaded and validated using `openpyxl`.

2.  **Excel Processing (`ExcelProcessor.populateReport()`)**
    The main process in `excelprocessor.py`:

    ```python
    def populateReport(self) -> InlineReport:
        self._loadWorkbook()            # Load Excel workbook
        self._verifyEntryPoint()        # Verify taxonomy entry point
        self.getAndValidateRequiredMetadata() # Extract metadata
        self._processConfiguration()    # Process configuration
        self._recordNamedRanges()       # Record named ranges
        self._processNamedRanges()      # Convert named ranges to XBRL facts
        self._processNamedRangeTables() # Process table structures
        self._createNamedPeriods()      # Create named periods
        self.createSimpleFacts()       # Create simple XBRL facts
        self.createTableFacts()        # Create table XBRL facts
        return self._report             # Return InlineReport
    ```

3.  **XBRL Fact Generation**

    * *Named Ranges* from the Excel file are converted into XBRL facts (`Fact` objects).
    * Each fact contains: Concept, Value, Context (Entity, Period, Dimensions), Unit.
    * The facts are collected in the `InlineReport` object.

4.  **Inline XBRL HTML Generation (`report.getInlineReportPackage()`)**

    * The `InlineReport` object generates an Inline XBRL HTML document.
    * Uses Jinja2 templates (`inline-report-presentation.html.jinja`).
    * **IMPORTANT**: This is **NOT** a separate XML XBRL file, but an HTML document with embedded XBRL data.
    * The HTML contains special XBRL attributes and namespaces.

5.  **ZIP Package Creation**

    * The generated Inline XBRL HTML is packed into a ZIP package.
    * The ZIP also contains CSS files and other assets.
    * This complies with the XBRL standard for *Report Packages*.

6.  **XBRL Validation with Arelle**

    * The generated package is validated with Arelle (XBRL-certified software).
    * Arelle checks for XBRL conformity and taxonomy compliance.

7.  **iXBRL Viewer Generation**

    * The iXBRL Viewer is used for display.
    * This is a JavaScript-based application for the interactive presentation of Inline XBRL.

-----

### Answer to Your Main Question:

**NO**, the software does **NOT** create a separate XML XBRL file.

Instead:

* It generates an **Inline XBRL HTML document** (`inline-report-presentation.html.jinja`).
* The XBRL data is embedded directly into the HTML with special attributes and namespaces.
* This is the modern XBRL standard – **Inline XBRL (iXBRL)** is both human-readable (as HTML) and machine-readable (as XBRL).

-----

### The Advantage of Inline XBRL:

* A single document that functions as both a business report (HTML) and structured XBRL data.
* No separate XML files are required.
* Direct rendering in the browser with the iXBRL Viewer for interactive features.

The generated ZIP package contains the Inline XBRL HTML document along with stylesheets and the iXBRL Viewer for interactive display.