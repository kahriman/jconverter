import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, BinaryIO, Optional

from babel import Locale
from dateutil.parser import parse as parse_datetime

from mireport.conversionresults import (
    ConversionResultsBuilder,
    MessageType,
    Severity,
)
from mireport.data import excel_templates
from mireport.exceptions import EarlyAbortException, InlineReportException
from mireport.json import getObject, getResource
from mireport.localise import get_locale_from_str
from mireport.taxonomy import (
    Concept,
    QName,
    Taxonomy,
    getTaxonomy,
    listTaxonomies,
)
from mireport.xbrlreport import FactBuilder, FactValue, InlineReport

L = logging.getLogger(__name__)

# Use the same defaults as Excel processor
VSME_DEFAULTS: dict = getObject(getResource(excel_templates, "vsme.json"))


class JsonProcessor:
    """
    JSON processor for converting structured JSON data to XBRL facts.
    Parallel implementation to ExcelProcessor but for JSON input.
    """

    def __init__(
        self,
        jsonPathOrFileLike: Path | BinaryIO,
        results: ConversionResultsBuilder,
        defaults: dict,
        /,
        outputLocale: Optional[Locale] = None,
    ):
        self._results = results
        self._defaults = defaults
        self._jsonPathOrFileLike: Path | BinaryIO = jsonPathOrFileLike

        # Populated from config file (similar to ExcelProcessor)
        self._configDataTypeToUnitMap: dict[QName, QName] = {}
        self._configUnitIdsToMeasures: dict[str, Any] = {}
        self._configCellValuesToTaxonomyLabels: dict[str, str] = {}
        self._configConceptToUnitMap: dict[Concept, QName] = {}
        self._configCellUnitReplacements: dict[str, str] = {}

        # Populated from JSON data
        self._jsonData: dict[str, Any] = {}
        self._namedRanges: dict[str, Any] = {}

        # For passing through to inline report
        self._outputLocale: Optional[Locale] = outputLocale
        self._coverImage: Optional[bytes] = None

        # Not yet initialised. Need setting early
        self._report: InlineReport

    @property
    def taxonomy(self) -> Taxonomy:
        return self._report.taxonomy

    def populateReport(self) -> InlineReport:
        """
        Add facts to InlineReport from the provided JSON data.
        Follows similar pattern to ExcelProcessor.populateReport()
        """
        try:
            self._loadJsonData()
            
            self._verifyEntryPoint()
            self.abortEarlyIfErrors()
            assert self._report

            self.getAndValidateRequiredMetadata()
            self._processConfiguration()
            self.abortEarlyIfErrors()

            self._recordNamedRanges()
            self._processNamedRanges()
            self._processNamedRangeTables()
            self._createNamedPeriods()
            self.createSimpleFacts()
            self.createTableFacts()
            self.checkForUnhandledItems()
            return self._report
        except EarlyAbortException as eae:
            self._results.addMessage(
                f"JSON conversion aborted early. {eae}",
                Severity.ERROR,
                MessageType.ExcelParsing,  # Reuse existing message type
            )
            raise
        except Exception as e:
            self._results.addMessage(
                f"Exception encountered during JSON processing. {e}",
                Severity.ERROR,
                MessageType.ExcelParsing,
            )
            L.exception("Exception encountered", exc_info=e)
            raise

    def _loadJsonData(self) -> None:
        """Load and validate JSON data from file or file-like object."""
        try:
            if isinstance(self._jsonPathOrFileLike, Path):
                with open(self._jsonPathOrFileLike, 'r', encoding='utf-8') as f:
                    self._jsonData = json.load(f)
            else:
                # File-like object
                content = self._jsonPathOrFileLike.read()
                if isinstance(content, bytes):
                    content = content.decode('utf-8')
                self._jsonData = json.loads(content)
                
            self._validateJsonStructure()
            
        except json.JSONDecodeError as e:
            self._results.addMessage(
                f"Invalid JSON format: {e}",
                Severity.ERROR,
                MessageType.ExcelParsing,
            )
            raise
        except Exception as e:
            self._results.addMessage(
                f"Failed to load JSON data: {e}",
                Severity.ERROR,
                MessageType.ExcelParsing,
            )
            raise

    def _validateJsonStructure(self) -> None:
        """Validate that JSON has expected structure for XBRL conversion."""
        if not isinstance(self._jsonData, dict):
            raise ValueError("JSON root must be an object")
        
        # Check for required sections
        required_sections = ['metadata', 'namedRanges']
        for section in required_sections:
            if section not in self._jsonData:
                self._results.addMessage(
                    f"Missing required section '{section}' in JSON",
                    Severity.ERROR,
                    MessageType.ExcelParsing,
                )

    def _verifyEntryPoint(self) -> None:
        """Verify and set up taxonomy entry point from JSON metadata."""
        try:
            # Get entry point from JSON metadata or use default
            metadata = self._jsonData.get('metadata', {})
            entry_point = metadata.get('entryPoint')
            
            if not entry_point:
                # Use default from config
                entry_point = self._defaults.get('entryPoint')
                if not entry_point:
                    self._results.addMessage(
                        "No entry point specified in JSON metadata or defaults",
                        Severity.ERROR,
                        MessageType.ExcelParsing,
                    )
                    return

            # Set up taxonomy and inline report
            taxonomy = getTaxonomy(entry_point)
            self._report = InlineReport(taxonomy, outputLocale=self._outputLocale)
            
            # Add schema reference
            self._report.addSchemaRef(entry_point)
            
        except Exception as e:
            self._results.addMessage(
                f"Failed to verify entry point: {e}",
                Severity.ERROR,
                MessageType.ExcelParsing,
            )
            raise

    def getAndValidateRequiredMetadata(self) -> None:
        """Extract and validate required metadata from JSON."""
        try:
            metadata = self._jsonData.get('metadata', {})
            
            # Extract entity information
            entity_info = metadata.get('entity', {})
            if 'name' in entity_info:
                self._report.setEntityName(entity_info['name'])
            if 'identifier' in entity_info:
                self._report.setEntityIdentifier(entity_info['identifier'])
            
            # Extract reporting period
            period_info = metadata.get('reportingPeriod', {})
            if 'start' in period_info and 'end' in period_info:
                start_date = parse_datetime(period_info['start']).date()
                end_date = parse_datetime(period_info['end']).date()
                self._report.setReportingPeriod(start_date, end_date)
            
            # Extract report title and subtitle
            if 'title' in metadata:
                self._report.setReportTitle(metadata['title'])
            if 'subtitle' in metadata:
                self._report.setReportSubtitle(metadata['subtitle'])
                
        except Exception as e:
            self._results.addMessage(
                f"Failed to extract metadata: {e}",
                Severity.WARNING,
                MessageType.ExcelParsing,
            )

    def _processConfiguration(self) -> None:
        """Process configuration similar to ExcelProcessor."""
        # This mirrors the configuration processing from ExcelProcessor
        defaults = self._defaults
        
        if "dataTypesToUnits" in defaults:
            for dataType, unitType in defaults["dataTypesToUnits"].items():
                self._configDataTypeToUnitMap[
                    self.taxonomy.QNameMaker.fromString(dataType)
                ] = self.taxonomy.QNameMaker.fromString(unitType)

        if "unitIdsToMeasures" in defaults:
            for unitId, unitDict in defaults["unitIdsToMeasures"].items():
                self._configUnitIdsToMeasures[unitId] = unitDict

        if "conceptsToUnits" in defaults:
            for conceptQname, unitQname in defaults["conceptsToUnits"].items():
                concept = self.taxonomy.getConcept(conceptQname)
                if concept:
                    self._configConceptToUnitMap[concept] = (
                        self.taxonomy.QNameMaker.fromString(unitQname)
                    )

        if "cellValuesToTaxonomyLabels" in defaults:
            self._configCellValuesToTaxonomyLabels.update(
                defaults["cellValuesToTaxonomyLabels"]
            )

        if "cellUnitReplacements" in defaults:
            self._configCellUnitReplacements.update(defaults["cellUnitReplacements"])

    def _recordNamedRanges(self) -> None:
        """Record named ranges from JSON data."""
        self._namedRanges = self._jsonData.get('namedRanges', {})
        
        if not self._namedRanges:
            self._results.addMessage(
                "No named ranges found in JSON data",
                Severity.WARNING,
                MessageType.ExcelParsing,
            )

    def _processNamedRanges(self) -> None:
        """Process named ranges and convert to XBRL concepts."""
        for name, value in self._namedRanges.items():
            if name.startswith(("enum_", "template_")):
                continue
                
            concept = self.taxonomy.getConceptForName(name)
            if concept:
                # Store the value for later fact creation
                # This is a simplified version - real implementation would need
                # to handle complex data types, dimensions, etc.
                pass
            else:
                self._results.addMessage(
                    f"No concept found for named range '{name}'",
                    Severity.WARNING,
                    MessageType.ExcelParsing,
                )

    def _processNamedRangeTables(self) -> None:
        """Process table structures from JSON (placeholder)."""
        # TODO: Implement table processing for JSON
        pass

    def _createNamedPeriods(self) -> None:
        """Create named periods from configuration."""
        # TODO: Implement period creation
        pass

    def createSimpleFacts(self) -> None:
        """Create simple XBRL facts from named ranges."""
        # TODO: Implement fact creation from named ranges
        pass

    def createTableFacts(self) -> None:
        """Create table-based XBRL facts."""
        # TODO: Implement table fact creation
        pass

    def checkForUnhandledItems(self) -> None:
        """Check for unhandled items and warn."""
        # TODO: Implement validation of unused named ranges
        pass

    def abortEarlyIfErrors(self) -> None:
        """Abort processing if there are critical errors."""
        if not self._results.conversionSuccessful:
            raise EarlyAbortException("Critical errors encountered")