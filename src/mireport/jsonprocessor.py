import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, BinaryIO, NamedTuple, Optional

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


class ComplexUnit(NamedTuple):
    """Complex unit structure for XBRL units."""
    numerator: list[QName]
    denominator: list[QName]


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
        self._configUnitIdsToMeasures: dict[str, ComplexUnit] = {}
        self._configCellValuesToTaxonomyLabels: dict[str, str] = {}
        self._configConceptToUnitMap: dict[Concept, QName] = {}
        self._configCellUnitReplacements: dict[str, str] = {}

        # Populated from JSON data
        self._jsonData: dict[str, Any] = {}
        self._namedRanges: dict[str, Any] = {}
        self._definedNameToXBRLMap: dict[str, Any] = {}

        # For passing through to inline report
        self._outputLocale: Optional[Locale] = outputLocale
        self._coverImage: Optional[bytes] = None

        # Not yet initialised. Need setting early
        self._report: InlineReport

    @property
    def taxonomy(self) -> Taxonomy:
        return self._report.taxonomy

    @property
    def unusedNames(self) -> list[str]:
        """Return list of unused named ranges."""
        return [name for name in self._namedRanges.keys() 
                if name not in self._definedNameToXBRLMap and not name.startswith(("enum_", "template_"))]

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
                self._report.setDefaultAspect("entity-identifier", entity_info['identifier'])
            if 'identifierScheme' in entity_info:
                # Map common scheme names to URIs
                scheme_mappings = {
                    "lei": "http://standards.iso.org/iso/17442",
                    "duns": "https://www.dnb.co.uk/duns-number",
                    "euid": "https://euid.eu/",
                    "permid": "https://permid.org/"
                }
                scheme = entity_info['identifierScheme'].lower()
                scheme_uri = scheme_mappings.get(scheme, scheme)
                self._report.setDefaultAspect("entity-scheme", scheme_uri)
            
            # Extract currency
            if 'currency' in metadata:
                self._report.setDefaultAspect("monetary-units", metadata['currency'])
            
            # Extract reporting period
            period_info = metadata.get('reportingPeriod', {})
            if 'start' in period_info and 'end' in period_info:
                start_date = parse_datetime(period_info['start']).date()
                end_date = parse_datetime(period_info['end']).date()
                # Add the duration period and set it as default
                period_name = "cur"  # Use same default name as Excel processor
                if self._report.addDurationPeriod(period_name, start_date, end_date):
                    self._report.setDefaultPeriodName(period_name)
            
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
                numerators: list[QName] = [
                    qname
                    for m in unitDict.get("numerator", [])
                    if (qname := self.taxonomy.UTR.getQNameForUnitId(m)) is not None
                ]
                denominators: list[QName] = [
                    qname
                    for m in unitDict.get("denominator", [])
                    if (qname := self.taxonomy.UTR.getQNameForUnitId(m)) is not None
                ]
                self._configUnitIdsToMeasures[unitId] = ComplexUnit(
                    numerator=numerators, denominator=denominators
                )

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
        self._definedNameToXBRLMap = {}
        
        for name, value in self._namedRanges.items():
            if name.startswith(("enum_", "template_")):
                continue
                
            concept = self.taxonomy.getConceptForName(name)
            if concept:
                # Create a holder for this named range similar to ExcelProcessor
                holder = type('JSONCellAndXBRLMetadataHolder', (), {
                    'concept': concept,
                    'name': name,
                    'value': value
                })()
                self._definedNameToXBRLMap[name] = holder
            else:
                self._results.addMessage(
                    f"No concept found for named range '{name}'",
                    Severity.WARNING,
                    MessageType.ExcelParsing,
                )

    def _processNamedRangeTables(self) -> None:
        """Process table structures from JSON."""
        tables = self._jsonData.get('tables', {})
        for table_name, table_data in tables.items():
            self._results.addMessage(
                f"Processing table '{table_name}' with {len(table_data)} rows",
                Severity.INFO,
                MessageType.ExcelParsing,
            )
            # TODO: Implement full table processing
            # For now, just log that tables are present

    def _createNamedPeriods(self) -> None:
        """Create named periods from metadata or configuration."""
        # Extract period information from metadata
        metadata = self._jsonData.get('metadata', {})
        period_info = metadata.get('reportingPeriod', {})
        
        if 'start' in period_info and 'end' in period_info:
            try:
                start_date = parse_datetime(period_info['start']).date()
                end_date = parse_datetime(period_info['end']).date()
                
                # Create named period (following ExcelProcessor pattern)
                self._report.addNamedPeriod("cur", start_date, end_date)
                
                self._results.addMessage(
                    f"Created reporting period from {start_date} to {end_date}",
                    Severity.INFO,
                    MessageType.ExcelParsing,
                )
            except Exception as e:
                self._results.addMessage(
                    f"Failed to parse reporting period: {e}",
                    Severity.ERROR,
                    MessageType.ExcelParsing,
                )

    def createSimpleFacts(self) -> None:
        """Create simple XBRL facts from named ranges."""
        for name, holder in self._definedNameToXBRLMap.items():
            concept = holder.concept
            
            if not concept.isReportable:
                continue
            
            # Get the value from the JSON data
            json_value = holder.value
            
            # Handle null or empty values
            if json_value is None or json_value == "" or json_value is False:
                continue
            
            # Extract value and unit for complex objects
            if isinstance(json_value, dict):
                value = json_value.get('value')
                unit = json_value.get('unit')
                dimensions = json_value.get('dimensions', {})
            else:
                value = json_value
                unit = None
                dimensions = {}
            
            if value is None:
                continue
            
            # Create fact builder
            fb = self._report.getFactBuilder()
            fb.setConcept(concept)
            
            try:
                # Handle different data types
                if concept.isDate:
                    if isinstance(value, str):
                        parsed_date = parse_datetime(value).date()
                        fb.setValue(parsed_date)
                    else:
                        raise ValueError(f"Date concept requires string value, got {type(value)}")
                
                elif concept.isNumeric:
                    if isinstance(value, (int, float)):
                        fb.setValue(value)
                        
                        # Handle unit setting
                        unit_set = False
                        
                        # 1. Try explicit unit from JSON
                        if unit:
                            try:
                                # Map common unit strings to QNames
                                unit_mappings = {
                                    'tCO2e': 'utr:tCO2e',
                                    'MWh': 'utr:MWh', 
                                    't': 'utr:t',
                                    'm3': 'utr:m3',
                                    'ha': 'utr:ha',
                                    '%': 'xbrli:pure',
                                    'EUR': 'iso4217:EUR',
                                    'USD': 'iso4217:USD'
                                }
                                unit_qname_str = unit_mappings.get(unit, unit)
                                unit_qname = self.taxonomy.QNameMaker.fromString(unit_qname_str)
                                
                                # Validate unit against concept's data type
                                if self.taxonomy.UTR.valid(concept.dataType, unit_qname):
                                    fb.setSimpleUnit(unit_qname)
                                    unit_set = True
                                else:
                                    self._results.addMessage(
                                        f"Unit '{unit}' is not valid for concept {concept.qname} with dataType {concept.dataType}",
                                        Severity.WARNING,
                                        MessageType.ExcelParsing,
                                    )
                            except Exception as e:
                                self._results.addMessage(
                                    f"Failed to set unit '{unit}' for concept {concept.qname}: {e}",
                                    Severity.WARNING,
                                    MessageType.ExcelParsing,
                                )
                        
                        # 2. Try monetary units
                        if not unit_set and concept.isMonetary:
                            currency = self._jsonData.get('metadata', {}).get('currency', 'EUR')
                            currency_qname = self.taxonomy.QNameMaker.fromString(f'iso4217:{currency}')
                            fb.setSimpleUnit(currency_qname)
                            unit_set = True
                        
                        # 3. Try concept-to-unit mapping from configuration
                        if not unit_set:
                            config_unit = self._configConceptToUnitMap.get(concept)
                            if config_unit:
                                if self.taxonomy.UTR.valid(concept.dataType, config_unit):
                                    fb.setSimpleUnit(config_unit)
                                    unit_set = True
                                else:
                                    self._results.addMessage(
                                        f"Configured unit {config_unit} is not valid for concept {concept.qname}",
                                        Severity.WARNING,
                                        MessageType.ExcelParsing,
                                    )
                        
                        # 4. Try required units from concept
                        if not unit_set:
                            required_units = concept.getRequiredUnitQNames()
                            if required_units and len(required_units) == 1:
                                fb.setSimpleUnit(next(iter(required_units)))
                                unit_set = True
                        
                        # 5. For pure numeric concepts (counts, ratios), use pure unit
                        if not unit_set and concept.dataType == self.taxonomy.QNameMaker.fromString("xbrli:decimalItemType"):
                            pure_unit = self.taxonomy.QNameMaker.fromString("xbrli:pure")
                            fb.setSimpleUnit(pure_unit)
                            unit_set = True
                        
                        # If still no unit, log error and skip this fact
                        if not unit_set:
                            self._results.addMessage(
                                f"No valid unit found for numeric concept {concept.qname} with dataType {concept.dataType}",
                                Severity.ERROR,
                                MessageType.ExcelParsing,
                            )
                            continue
                    else:
                        raise ValueError(f"Numeric concept requires numeric value, got {type(value)}")
                
                elif concept.isEnumerationSingle:
                    # Handle enumeration values
                    str_value = str(value)
                    enum_concept = self.taxonomy.getConceptForLabel(str_value)
                    
                    # Try fallback mapping
                    if enum_concept is None and str_value in self._configCellValuesToTaxonomyLabels:
                        fallback_label = self._configCellValuesToTaxonomyLabels[str_value]
                        enum_concept = self.taxonomy.getConceptForLabel(fallback_label)
                    
                    if enum_concept:
                        fb.setHiddenValue(enum_concept.expandedName)
                    else:
                        self._results.addMessage(
                            f"Could not find enumeration member for value '{str_value}' in concept {concept.qname}",
                            Severity.WARNING,
                            MessageType.ExcelParsing,
                        )
                        continue
                
                else:
                    # Text or other types
                    fb.setValue(str(value))
                
                # Handle dimensions if present
                for dim_name, dim_value in dimensions.items():
                    dim_concept = self.taxonomy.getConceptForName(dim_name)
                    dim_member = self.taxonomy.getConceptForLabel(str(dim_value))
                    if dim_concept and dim_member:
                        fb.addDimension(dim_concept, dim_member)
                
                # Add the fact to the report
                self._report.addFact(fb.buildFact())
                
                self._results.addMessage(
                    f"Created fact for {concept.qname} with value {value}",
                    Severity.INFO,
                    MessageType.ExcelParsing,
                )
                
            except Exception as e:
                self._results.addMessage(
                    f"Failed to create fact for {concept.qname}: {e}",
                    Severity.ERROR,
                    MessageType.ExcelParsing,
                )

    def createTableFacts(self) -> None:
        """Create table-based XBRL facts."""
        tables = self._jsonData.get('tables', {})
        for table_name, table_rows in tables.items():
            self._results.addMessage(
                f"Processing table '{table_name}' with {len(table_rows)} rows",
                Severity.INFO,
                MessageType.ExcelParsing,
            )
            
            # TODO: Implement full table fact creation
            # This would involve creating facts with dimensional data
            # based on the table structure
            
            for i, row in enumerate(table_rows):
                for column_name, cell_value in row.items():
                    # Try to map column name to concept
                    concept = self.taxonomy.getConceptForName(column_name)
                    if concept and concept.isReportable and cell_value is not None:
                        fb = self._report.getFactBuilder()
                        fb.setConcept(concept)
                        fb.setValue(cell_value)
                        
                        # TODO: Add table-specific dimensions
                        # This would require understanding the table structure
                        # and mapping row identifiers to dimensional members
                        
                        try:
                            self._report.addFact(fb.buildFact())
                        except Exception as e:
                            self._results.addMessage(
                                f"Failed to create table fact for {concept.qname}: {e}",
                                Severity.WARNING,
                                MessageType.ExcelParsing,
                            )

    def checkForUnhandledItems(self) -> None:
        """Check for unhandled items and warn."""
        # Check for named ranges that weren't processed
        unprocessed_ranges = []
        for name in self._namedRanges.keys():
            if not name.startswith(("enum_", "template_")) and name not in self._definedNameToXBRLMap:
                unprocessed_ranges.append(name)
        
        if unprocessed_ranges:
            self._results.addMessage(
                f"Unprocessed named ranges: {', '.join(unprocessed_ranges)}",
                Severity.WARNING,
                MessageType.ExcelParsing,
            )
        
        # Check for tables that weren't fully processed
        tables = self._jsonData.get('tables', {})
        if tables:
            self._results.addMessage(
                f"Table processing is not fully implemented. {len(tables)} tables found but may not be fully processed.",
                Severity.WARNING,
                MessageType.ExcelParsing,
            )

    def abortEarlyIfErrors(self) -> None:
        """Abort processing if there are critical errors."""
        if not self._results.conversionSuccessful:
            raise EarlyAbortException("Critical errors encountered")