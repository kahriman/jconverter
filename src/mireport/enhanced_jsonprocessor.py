import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, BinaryIO, NamedTuple, Optional, Self

from babel import Locale
from dateutil.parser import parse as parse_datetime
from dateutil.relativedelta import relativedelta

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

JSON_VALUES_TO_BE_TREATED_AS_NONE_VALUE = (None, "", "-", "n/a", "N/A", "null", False)


def cleanUnitTextFromJson(unitText: str, replacements: dict[str, str]) -> str:
    """Clean unit text similar to Excel processor's cleanUnitTextFromExcel."""
    new = unitText
    for original, replacement in replacements.items():
        new = new.replace(original, replacement)
    return new


def conceptsToText(concepts) -> str:
    """Convert concepts to text similar to Excel processor."""
    return ", ".join(sorted(str(c.qname) for c in concepts))


class ComplexUnit(NamedTuple):
    """Complex unit structure for XBRL units."""
    numerator: list[QName]
    denominator: list[QName]


@dataclass(slots=True, eq=True, frozen=True)
class JsonCellMetadata:
    """Metadata holder for JSON named range values, similar to CellRangeMetadata."""
    name: str
    value: Any
    unit: Optional[str] = None
    dimensions: Optional[dict[str, Any]] = None


@dataclass(slots=True, eq=True, frozen=True)
class JsonCellAndXBRLMetadataHolder:
    """JSON equivalent of CellAndXBRLMetadataHolder."""
    name: str
    value: Any
    concept: Concept
    unit: Optional[str] = None
    dimensions: Optional[dict[str, Any]] = None

    @classmethod
    def fromJsonCellMetadata(cls, holder: JsonCellMetadata, concept: Concept) -> Self:
        """Create from JsonCellMetadata and Concept."""
        return cls(
            name=holder.name,
            value=holder.value,
            concept=concept,
            unit=holder.unit,
            dimensions=holder.dimensions,
        )


class EnhancedJsonProcessor:
    """
    Enhanced JSON processor that closely matches ExcelProcessor architecture.
    Provides sophisticated unit resolution, validation, and error handling.
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

        # Configuration mappings (similar to ExcelProcessor)
        self._configDataTypeToUnitMap: dict[QName, QName] = {}
        self._configUnitIdsToMeasures: dict[str, ComplexUnit] = {}
        self._configCellValuesToTaxonomyLabels: dict[str, str] = {}
        self._configConceptToUnitMap: dict[Concept, QName] = {}
        self._configCellUnitReplacements: dict[str, str] = {}

        # JSON data structures
        self._jsonData: dict[str, Any] = {}
        self._namedRanges: dict[str, Any] = {}
        self._unusedNamedRanges: set[str] = set()
        self._definedNameToXBRLMap: dict[str, JsonCellAndXBRLMetadataHolder] = {}
        self._conceptToUnitHolderMap: dict[Concept, JsonCellAndXBRLMetadataHolder] = {}
        self._presetDimensions: dict[JsonCellAndXBRLMetadataHolder, dict[Concept, Concept]] = defaultdict(dict)

        # For passing through to inline report
        self._outputLocale: Optional[Locale] = outputLocale
        self._coverImage: Optional[bytes] = None

        # Not yet initialized
        self._report: InlineReport

    @property
    def taxonomy(self) -> Taxonomy:
        return self._report.taxonomy

    @property
    def unusedNames(self) -> list[str]:
        return sorted(self._unusedNamedRanges)

    def populateReport(self) -> InlineReport:
        """
        Add facts to InlineReport from JSON data.
        Follows same pattern as ExcelProcessor.populateReport()
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
                MessageType.ExcelParsing,
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
        """Validate JSON structure."""
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
        """Verify and set up taxonomy entry point."""
        metadata = self._jsonData.get('metadata', {})
        entry_point = metadata.get('entryPoint')

        if not entry_point:
            entry_point = self._defaults.get('entryPoint')
            if not entry_point:
                self._results.addMessage(
                    "No entry point specified in JSON metadata or defaults",
                    Severity.ERROR,
                    MessageType.ExcelParsing,
                )
                return

        valid_entry_points = set(listTaxonomies())
        if entry_point not in valid_entry_points:
            self._results.addMessage(
                f"JSON report is for an unsupported taxonomy. JSON wants: {entry_point}. We support: {sorted(valid_entry_points)}",
                Severity.ERROR,
                MessageType.ExcelParsing,
            )

        self.abortEarlyIfErrors()
        taxonomy = getTaxonomy(entry_point)
        self._determineOutputLocale(taxonomy)
        self._report = InlineReport(taxonomy, self._outputLocale)
        self._report.addSchemaRef(entry_point)

    def _determineOutputLocale(self, taxonomy: Taxonomy) -> None:
        """Determine output locale from JSON metadata."""
        if not taxonomy.defaultLanguage:
            return

        metadata = self._jsonData.get('metadata', {})
        output_language = metadata.get('outputLanguage')

        if not output_language:
            return

        best_output_locale = (
            taxonomy.getBestSupportedLanguage(output_language)
            or taxonomy.defaultLanguage
        )

        if output_language != best_output_locale:
            self._results.addMessage(
                f"JSON language specified as '{output_language}'. Using closest match supported by the taxonomy, '{best_output_locale}'",
                Severity.INFO,
                MessageType.Conversion,
            )

        new_output_locale = get_locale_from_str(best_output_locale)
        if (
            self._outputLocale
            and new_output_locale
            and self._outputLocale != new_output_locale
        ):
            self._results.addMessage(
                f"JSON requested output locale resolved to '{new_output_locale}'. Ignoring as already configured to use output locale: '{self._outputLocale}'",
                Severity.INFO,
                MessageType.Conversion,
            )
        else:
            self._outputLocale = new_output_locale

    def getAndValidateRequiredMetadata(self) -> None:
        """Extract and validate required metadata, matching ExcelProcessor logic."""
        defaults = self._defaults
        metadata = self._jsonData.get('metadata', {})

        # Entity identifier scheme mappings
        entity_identifier_scheme_to_uris: dict[str, str] = {
            k: v for k, v in defaults.get("entityIdentifierLabelsToSchemes", {}).items()
        }

        # Process AOIX metadata
        if "aoix" in defaults:
            for aoix_name, json_key in defaults["aoix"].items():
                if aoix_name == "entity-scheme":
                    entity_info = metadata.get('entity', {})
                    scheme_value = entity_info.get('identifierScheme', '').strip().replace(" ", "").lower()
                    aoix_value = entity_identifier_scheme_to_uris.get(scheme_value)
                elif aoix_name == "entity-identifier":
                    entity_info = metadata.get('entity', {})
                    aoix_value = entity_info.get('identifier', '').strip()
                elif aoix_name == "monetary-units":
                    aoix_value = metadata.get('currency', '').strip()
                else:
                    aoix_value = metadata.get(json_key, '').strip()

                if not aoix_value or aoix_value in JSON_VALUES_TO_BE_TREATED_AS_NONE_VALUE:
                    self._results.addMessage(
                        f"JSON report must have a valid value for {aoix_name}.",
                        Severity.ERROR,
                        MessageType.ExcelParsing,
                    )
                    continue

                self._report.setDefaultAspect(aoix_name, aoix_value)

        # Process periods
        if "periods" in defaults:
            for period in defaults["periods"]:
                failed = False
                period_info = metadata.get('reportingPeriod', {})

                try:
                    start_date = parse_datetime(period_info.get('start')).date()
                except Exception as e:
                    self._results.addMessage(
                        f"JSON report must have a valid start date. Exception: {e}",
                        Severity.ERROR,
                        MessageType.ExcelParsing,
                    )
                    failed = True

                try:
                    end_date = parse_datetime(period_info.get('end')).date()
                except Exception as e:
                    self._results.addMessage(
                        f"JSON report must have a valid end date. Exception: {e}",
                        Severity.ERROR,
                        MessageType.ExcelParsing,
                    )
                    failed = True

                if not failed and start_date > end_date:
                    self._results.addMessage(
                        f"Start date {start_date} is after end date {end_date}.",
                        Severity.ERROR,
                        MessageType.ExcelParsing,
                    )
                    failed = True

                name = period["name"]
                if not failed and self._report.addDurationPeriod(name, start_date, end_date):
                    self._report.setDefaultPeriodName(name)

        # Process report metadata
        if "report" in defaults:
            report_defaults = defaults["report"]
            self.setReportMetadata(report_defaults, "entity-name", self._report.setEntityName)
            self.setReportMetadata(report_defaults, "report-title", self._report.setReportTitle)
            self.setReportMetadata(report_defaults, "report-subtitle", self._report.setReportSubtitle)

    def setReportMetadata(self, report_defaults: dict, key: str, method) -> None:
        """Set report metadata from JSON or fallback."""
        config = report_defaults.get(key)
        if not isinstance(config, dict):
            self._results.addMessage(
                f"Missing or invalid configuration for report metadata key '{key}'.",
                Severity.ERROR,
                MessageType.ExcelParsing,
            )
            return

        metadata = self._jsonData.get('metadata', {})
        json_key = key.replace('-', '')  # Convert entity-name to entityname, etc.

        if json_key == 'entityname':
            entity_info = metadata.get('entity', {})
            value = entity_info.get('name', '')
        elif json_key == 'reporttitle':
            value = metadata.get('title', '')
        elif json_key == 'reportsubtitle':
            value = metadata.get('subtitle', '')
        else:
            value = metadata.get(json_key, '')

        if value:
            method(value)
        elif 'fallback' in config:
            method(config['fallback'])
        else:
            self._results.addMessage(
                f"JSON report must have a value for '{key}'.",
                Severity.ERROR,
                MessageType.ExcelParsing,
            )

    def _processConfiguration(self) -> None:
        """Process configuration mappings, matching ExcelProcessor logic."""
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
        self._unusedNamedRanges.update(
            name for name in self._namedRanges.keys()
            if name and not name.startswith(("enum_", "template_"))
        )

    def _processNamedRanges(self) -> None:
        """Process named ranges similar to ExcelProcessor."""
        for name in self._unusedNamedRanges.copy():
            if not name:
                self._results.addMessage(
                    "Named range has no name. Skipping.",
                    Severity.ERROR,
                    MessageType.DevInfo,
                )
                self._unusedNamedRanges.remove(name)
                continue

            concept = self.taxonomy.getConceptForName(name)

            # TODO FIXME Temporary fix for the VSME taxonomy (same as Excel processor)
            if name == "IdentifierOfSitesInBiodiversitySensitiveAreasTypedAxis":
                concept = self.taxonomy.getConceptForName("IdentifierOfSiteTypedAxis")

            if concept is not None:
                json_value = self._namedRanges[name]

                # Handle complex value structure
                if isinstance(json_value, dict):
                    value = json_value.get('value')
                    unit = json_value.get('unit')
                    dimensions = json_value.get('dimensions')
                else:
                    value = json_value
                    unit = None
                    dimensions = None

                cell_metadata = JsonCellMetadata(name=name, value=value, unit=unit, dimensions=dimensions)
                self._definedNameToXBRLMap[name] = JsonCellAndXBRLMetadataHolder.fromJsonCellMetadata(
                    cell_metadata, concept=concept
                )
            elif "_" in name:
                concept_name, _, member_name = name.partition("_")
                if "unit" == member_name:
                    if (concept := self._report.taxonomy.getConceptForName(concept_name)) is not None:
                        json_value = self._namedRanges[name]
                        cell_metadata = JsonCellMetadata(name=name, value=json_value)
                        self._conceptToUnitHolderMap[concept] = JsonCellAndXBRLMetadataHolder.fromJsonCellMetadata(
                            cell_metadata, concept
                        )
                        self._unusedNamedRanges.remove(name)
                else:
                    concept = self._report.taxonomy.getConceptForName(concept_name)
                    dim_value = self._report.taxonomy.getConceptForName(member_name)
                    if concept is not None and dim_value is not None:
                        json_value = self._namedRanges[name]
                        cell_metadata = JsonCellMetadata(name=name, value=json_value)
                        holder = JsonCellAndXBRLMetadataHolder.fromJsonCellMetadata(cell_metadata, concept=concept)
                        if (dim := self._report.taxonomy.getExplicitDimensionForDomainMember(concept, dim_value)) is not None:
                            self._definedNameToXBRLMap[name] = holder
                            self._presetDimensions[holder][dim] = dim_value
                        else:
                            self._results.addMessage(
                                f"Domain member qualification set in named range {name} but no dimension can be found for member.",
                                Severity.ERROR,
                                MessageType.DevInfo,
                            )

            if name in self._definedNameToXBRLMap:
                self._unusedNamedRanges.remove(name)

        self._results.addMessage(
            f"JSON file parsed ({len(self._namedRanges)} named ranges processed).",
            Severity.INFO,
            MessageType.ExcelParsing,
        )

    def _processNamedRangeTables(self) -> None:
        """Process table structures from JSON data."""
        # Similar to Excel processor but adapted for JSON structure
        tables = self._jsonData.get('tables', {})
        if tables:
            self._results.addMessage(
                f"Found {len(tables)} tables in JSON data",
                Severity.INFO,
                MessageType.ExcelParsing,
            )
            # TODO: Implement full table processing similar to ExcelProcessor

    def _createNamedPeriods(self) -> None:
        """Create named periods from JSON data."""
        # Extract period holders similar to Excel processor logic
        potential_period_holders = [
            holder
            for holder in self._definedNameToXBRLMap.values()
            if holder.concept.isAbstract
        ]

        members_with_potential_periods = {
            dim_value
            for dim_pair in self._presetDimensions.values()
            for dim_value in dim_pair.values()
        }

        period_holders = [
            p for p in potential_period_holders
            if p.concept in members_with_potential_periods
        ]

        for period_holder in period_holders:
            named_period = period_holder.name or ""
            year = period_holder.value

            if year is None or year in JSON_VALUES_TO_BE_TREATED_AS_NONE_VALUE:
                self._definedNameToXBRLMap.pop(period_holder.name)
                continue

            if isinstance(year, bool) or not isinstance(year, (float, int, str)):
                self._results.addMessage(
                    f"Unable to extract year for {period_holder.name}. Value '{year}'",
                    Severity.ERROR,
                    MessageType.ExcelParsing,
                    taxonomy_concept=period_holder.concept,
                )
                self._definedNameToXBRLMap.pop(period_holder.name)
                continue

            try:
                year_int = int(year)
                self.getOrAddNamedPeriodForYear(named_period, year_int)
                self._definedNameToXBRLMap.pop(period_holder.name)
            except ValueError:
                self._results.addMessage(
                    f"Unable to convert value '{year}' to an integer.",
                    Severity.ERROR,
                    MessageType.ExcelParsing,
                    taxonomy_concept=period_holder.concept,
                )

    def getOrAddNamedPeriodForYear(self, name: str, year: int) -> str:
        """Create named period for year, similar to Excel processor."""
        if self._report.hasNamedPeriod(name):
            return name

        # Need to add a new named period for the year
        end_of_default = self._report.defaultPeriod.end
        end = end_of_default + relativedelta(year=year)
        start = end + relativedelta(years=-1, days=+1)
        self._report.addDurationPeriod(name, start, end)
        return name

    def getSimpleUnit(self, unit_text: str, concept: Concept) -> Optional[QName]:
        """
        Get simple unit QName from unit text, with enhanced logic matching ExcelProcessor.

        This method handles both namespace-prefixed units (utr:tCO2e) and simple units (tCO2e).
        """
        if not unit_text:
            return None

        unit_text = str(unit_text).strip()
        candidates = [unit_text]

        # Extract content from parentheses (similar to Excel processor)
        candidates.extend(re.findall(r"\((.*?)\)", unit_text))

        # Handle namespace-prefixed units by trying both with and without prefix
        if ":" in unit_text:
            # Extract the local part after the colon
            candidates.append(unit_text.split(":")[-1])

        possible_units = [
            unit
            for c in candidates
            if (unit := self.taxonomy.UTR.getQNameForUnitId(c)) is not None
        ]

        if not possible_units:
            # Try with unit replacements
            candidates = [
                cleanUnitTextFromJson(c, self._configCellUnitReplacements)
                for c in candidates
            ]
            possible_units = [
                unit
                for c in candidates
                if (unit := self.taxonomy.UTR.getQNameForUnitId(c)) is not None
            ]

            if possible_units:
                self._results.addMessage(
                    f"Workaround performed for mislabelled unit for {concept.qname}. Unit text '{unit_text}'. Unit ids now guessed '{possible_units}'",
                    Severity.WARNING,
                    MessageType.DevInfo,
                    taxonomy_concept=concept,
                )

        match len(possible_units):
            case 1:
                return possible_units[0]
            case 0:
                return None
            case _:
                self._results.addMessage(
                    f"Ambiguous unit specified '{unit_text}'. Identified possible units: {possible_units}",
                    Severity.ERROR,
                    MessageType.ExcelParsing,
                )
                return None

    def setUnitForName(self, concept_holder: JsonCellAndXBRLMetadataHolder, fact_builder: FactBuilder) -> bool:
        """
        Set unit for concept, matching ExcelProcessor logic with enhanced JSON handling.
        """
        concept = concept_holder.concept

        # 1. Try explicit unit from JSON
        if concept_holder.unit:
            if (unit := self.getSimpleUnit(concept_holder.unit, concept)) is not None:
                if self.taxonomy.UTR.valid(concept.dataType, unit):
                    fact_builder.setSimpleUnit(unit)
                    return True
                else:
                    self._results.addMessage(
                        f"Unit '{concept_holder.unit}' is not valid for concept {concept.qname} with dataType {concept.dataType}.",
                        Severity.WARNING,
                        MessageType.Conversion,
                        taxonomy_concept=concept,
                    )

        # 2. Try concept-to-unit mapping
        if (unit_qname := self._configConceptToUnitMap.get(concept)) is not None:
            if self.taxonomy.UTR.valid(concept.dataType, unit_qname):
                fact_builder.setSimpleUnit(unit_qname)
                return True

        # 3. Try measurement guidance label
        if (units := concept.getRequiredUnitQNames()) is not None:
            if len(units) == 1:
                fact_builder.setSimpleUnit(next(iter(units)))
                return True
            else:
                self._results.addMessage(
                    f"No unit found for {concept_holder.name}. More than one unit specified as possible in the taxonomy. {units=}",
                    Severity.WARNING,
                    MessageType.Conversion,
                    taxonomy_concept=concept,
                )
                return False

        # 4. Try complex units
        candidate_unit_ids = list(self.taxonomy.UTR.getUnitIdsForDataType(concept.dataType))
        for c in candidate_unit_ids:
            complex_unit = self._configUnitIdsToMeasures.get(c)
            if complex_unit is not None:
                fact_builder.setComplexUnit(complex_unit.numerator, complex_unit.denominator)
                return True

        # 5. Fallback unit logic
        return self.setFallbackUnitForName(concept_holder.name, concept, fact_builder)

    def setFallbackUnitForName(self, name: str, concept: Concept, fact_builder: FactBuilder) -> bool:
        """Set fallback unit, matching ExcelProcessor logic."""
        if not concept.isNumeric:
            return False

        # If we have a default unit for the data type, use it if UTR valid
        if (unit := self._configDataTypeToUnitMap.get(concept.dataType)) is not None:
            if self.taxonomy.UTR.valid(concept.dataType, unit):
                fact_builder.setSimpleUnit(unit)
                return True

        # Otherwise pick the first unit from the UTR that is valid
        if units := self.taxonomy.UTR.getUnitsForDataType(concept.dataType):
            chosen = next(iter(units))
            self._results.addMessage(
                f"Picked fallback unit (from UTR) {chosen} for {name}",
                Severity.WARNING,
                MessageType.DevInfo,
            )
            fact_builder.setSimpleUnit(chosen)
        else:
            # Ultimate fallback to xbrli:pure
            ultimate_fallback = self.taxonomy.QNameMaker.fromString("xbrli:pure")
            self._results.addMessage(
                f"Used ultimate fallback unit {ultimate_fallback} for {name}",
                Severity.WARNING,
                MessageType.DevInfo,
            )
            fact_builder.setSimpleUnit(ultimate_fallback)
        return True

    def processNumeric(self, holder: JsonCellAndXBRLMetadataHolder, fact_builder: FactBuilder, value: Any = None) -> None:
        """Process numeric values, adapted from ExcelProcessor."""
        if value is None:
            value = holder.value

        if value is None:
            self._results.addMessage(
                f"Value is None for {holder.name}. Unable to process numeric value.",
                Severity.ERROR,
                MessageType.DevInfo,
            )
            return

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self._results.addMessage(
                f"Value {value=} {type(value)} is not numeric for {holder.name}. Unable to process numeric value.",
                Severity.ERROR,
                MessageType.DevInfo,
            )
            return

        # For JSON, we don't have cell formatting info, so use reasonable defaults
        # TODO: Could extract decimals from value precision if needed
        decimals = 2 if isinstance(value, float) else 0
        fact_builder.setDecimals(decimals)

    def createSimpleFacts(self) -> None:
        """Create simple XBRL facts, matching ExcelProcessor logic."""
        reportable = {
            name: holder
            for name, holder in self._definedNameToXBRLMap.items()
            if holder.concept and holder.concept.isReportable
        }

        for name, holder in reportable.copy().items():
            concept = holder.concept
            required_dims = self.taxonomy.getExplicitDimensionsForPrimaryItem(concept)
            preset_dims = frozenset(self._presetDimensions.get(holder, {}).keys())
            unset_dims = required_dims.difference(
                self.taxonomy.defaultedDimensions, preset_dims
            )

            if unset_dims:
                self._results.addMessage(
                    f"The named range {name} has required dimensions that have not been set.\n"
                    f"The required dimensions {conceptsToText(required_dims)}.\n"
                    f"Missing: {conceptsToText(unset_dims)}.",
                    Severity.ERROR,
                    MessageType.DevInfo,
                )
                reportable.pop(name)

        for name, holder in reportable.items():
            concept = holder.concept
            assert concept.isReportable

            fb = self._report.getFactBuilder()

            if concept.isEnumerationSet:
                self.createEESetFact(holder, fb)
                self._definedNameToXBRLMap.pop(name)
                continue

            value = holder.value
            if value is None or value is False:
                self._definedNameToXBRLMap.pop(name)
                continue
            if value in JSON_VALUES_TO_BE_TREATED_AS_NONE_VALUE:
                self._definedNameToXBRLMap.pop(name)
                continue

            if concept.isDate:
                try:
                    if isinstance(value, str):
                        value = parse_datetime(value).date()
                    elif isinstance(value, datetime):
                        value = value.date()
                    elif isinstance(value, date):
                        pass  # Already a date
                    else:
                        raise ValueError(f"Cannot convert {type(value)} to date")
                except Exception:
                    self._results.addMessage(
                        f"Unable to parse date from value '{value}' for {concept.qname}.",
                        Severity.ERROR,
                        MessageType.ExcelParsing,
                        taxonomy_concept=concept,
                    )
                    self._definedNameToXBRLMap.pop(name)
                    continue

            fb.setConcept(concept)
            if isinstance(value, FactValue):
                fb.setValue(value)
            else:
                if not isinstance(value, (str, int, float, bool, date)):
                    self._results.addMessage(
                        f"Complex object '{value}' {type(value).__name__} encountered as fact value for {concept}. Converting to string.",
                        Severity.WARNING,
                        MessageType.ExcelParsing,
                        taxonomy_concept=concept,
                    )
                    fb.setValue(str(value))
                else:
                    fb.setValue(value)

            if concept.isNumeric:
                self.processNumeric(holder, fb, value)

            if concept.isNumeric and not concept.isMonetary:
                if not self.setUnitForName(holder, fb):
                    self._definedNameToXBRLMap.pop(name)
                    continue
            elif concept.isMonetary:
                pass  # Monetary units are set via defaults
            elif concept.isEnumerationSingle:
                s_value = str(value)
                ee_value = self._report.taxonomy.getConceptForLabel(s_value)
                warn = False
                if (
                    ee_value is None
                    and (fake_value := self._configCellValuesToTaxonomyLabels.get(s_value)) is not None
                ):
                    ee_value = self._report.taxonomy.getConceptForLabel(fake_value)
                    warn = True
                if ee_value is not None:
                    fb.setHiddenValue(ee_value.expandedName)
                    if warn:
                        self._results.addMessage(
                            f"Workaround performed for EE member label mismatch when reporting {concept.qname}. Value '{value}'. Concept label '{ee_value.getStandardLabel()}'",
                            Severity.WARNING,
                            MessageType.DevInfo,
                            taxonomy_concept=concept,
                        )
                else:
                    self._results.addMessage(
                        f"Unable to find EE concept when reporting {concept.qname}. Value '{value}'.",
                        Severity.ERROR,
                        MessageType.Conversion,
                    )

            if (preset_dimensions := self._presetDimensions.get(holder)) is not None:
                for dim, dim_value in preset_dimensions.items():
                    default_value = self.taxonomy.getDimensionDefault(dim)
                    if default_value is None or dim_value != default_value:
                        fb.setExplicitDimension(dim, dim_value)

                    # Handle named periods for dimension values
                    named_period = dim_value.qname.localName
                    if self._report.hasNamedPeriod(named_period):
                        fb.setNamedPeriod(named_period)

            self._definedNameToXBRLMap.pop(name)
            self.addFactToReport(fb, holder)

    def createEESetFact(self, holder: JsonCellAndXBRLMetadataHolder, fb: FactBuilder) -> None:
        """Create enumeration set fact, adapted from ExcelProcessor."""
        concept = holder.concept
        assert concept.isEnumerationSet

        # For JSON, we expect enumeration sets to be provided as arrays or comma-separated strings
        value = holder.value
        if isinstance(value, list):
            values = [str(v) for v in value if v is not None]
        elif isinstance(value, str):
            values = [v.strip() for v in value.split(',') if v.strip()]
        else:
            values = [str(value)] if value is not None else []

        ee_set_value: set[Concept] = set()
        processed_values: list[str] = []

        for v in values:
            if v in JSON_VALUES_TO_BE_TREATED_AS_NONE_VALUE:
                continue

            warn = False
            e_label = v
            if v.startswith("NACE "):
                e_label = v.replace("NACE ", "")
                warn = True

            ee_concept = self._report.taxonomy.getConceptForLabel(e_label)
            if (
                ee_concept is None
                and (fake_value := self._configCellValuesToTaxonomyLabels.get(e_label)) is not None
            ):
                warn = True
                ee_concept = self._report.taxonomy.getConceptForLabel(fake_value)

            if ee_concept is not None:
                processed_values.append(str(v))
                ee_set_value.add(ee_concept)
                if warn:
                    self._results.addMessage(
                        f"Workaround performed for EE member label mismatch when reporting {concept.qname}. Value '{v}'. Concept label '{ee_concept.getStandardLabel()}'",
                        Severity.WARNING,
                        MessageType.DevInfo,
                        taxonomy_concept=concept,
                    )
            else:
                self._results.addMessage(
                    f"Unable to find EE member when reporting {concept.qname}. Value '{v}'.",
                    Severity.ERROR,
                    MessageType.ExcelParsing,
                    taxonomy_concept=concept,
                )

        if not ee_set_value:
            self._results.addMessage(
                f"No values found for {concept.qname} so not creating an empty XBRL fact. Values '{processed_values}'",
                Severity.INFO,
                MessageType.DevInfo,
                taxonomy_concept=concept,
            )
        else:
            fb.setConcept(concept).setHiddenValue(
                " ".join(sorted(e.expandedName for e in ee_set_value))
            ).setValue("\n".join(processed_values))
            self.addFactToReport(fb, holder)

    def addFactToReport(self, fact_builder: FactBuilder, holder: JsonCellAndXBRLMetadataHolder) -> bool:
        """Add fact to report with error handling."""
        try:
            self._report.addFact(fact_builder.buildFact())
            return True
        except InlineReportException as i:
            self._results.addMessage(
                f"Unable to add fact. Encountered error: {i}",
                Severity.WARNING,
                MessageType.Conversion,
            )
        return False

    def createTableFacts(self) -> None:
        """Create table-based XBRL facts."""
        tables = self._jsonData.get('tables', {})
        for table_name, table_rows in tables.items():
            self._results.addMessage(
                f"Processing table '{table_name}' with {len(table_rows)} rows",
                Severity.INFO,
                MessageType.ExcelParsing,
            )
            # TODO: Implement full table fact creation similar to ExcelProcessor
            # This would require understanding hypercubes and dimensional structures

    def checkForUnhandledItems(self) -> None:
        """Check for unhandled items."""
        unhandled = list(self._definedNameToXBRLMap.values())

        # FIXME: temporary workaround for VSME taxonomy (same as Excel processor)
        ignore_names = {"BreakdownOfEnergyConsumptionAxis"}

        for holder in unhandled:
            if holder.name in ignore_names:
                continue
            message = f"Failed to handle XBRL related JSON named range {holder.name}."
            self._results.addMessage(
                message,
                Severity.ERROR,
                MessageType.Conversion,
            )

    def abortEarlyIfErrors(self) -> None:
        """Abort processing if there are critical errors."""
        if self._results.hasErrors():
            raise EarlyAbortException(
                "JSON report has critical errors. Please check the report and try again."
            )