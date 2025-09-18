import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from mireport.conversionresults import ConversionResultsBuilder
from mireport.jsonprocessor import JsonProcessor, VSME_DEFAULTS


class TestJsonProcessor(unittest.TestCase):
    """Test cases for JsonProcessor class."""

    def setUp(self):
        """Set up test fixtures."""
        self.sample_json_data = {
            "metadata": {
                "entryPoint": "template_reporting_schemaRef",
                "entity": {
                    "name": "Test Corporation Ltd",
                    "identifier": "12345678901234567890",
                    "identifierScheme": "lei"
                },
                "reportingPeriod": {
                    "start": "2024-01-01",
                    "end": "2024-12-31"
                },
                "title": "Test Sustainability Report 2024",
                "subtitle": "Test subtitle",
                "currency": "EUR"
            },
            "namedRanges": {
                "template_reporting_entity_name": "Test Corporation Ltd",
                "template_reporting_entity_identifier": "12345678901234567890",
                "template_reporting_period_startdate": "2024-01-01",
                "template_reporting_period_enddate": "2024-12-31",
                "ScopeOneGrossGhgEmissions": {
                    "value": 1250.5,
                    "unit": "tCO2e"
                },
                "NumberOfEmployees": 250
            }
        }

    def test_init(self):
        """Test JsonProcessor initialization."""
        json_string = json.dumps(self.sample_json_data)
        json_file_like = StringIO(json_string)
        results = ConversionResultsBuilder()
        
        processor = JsonProcessor(
            json_file_like,
            results,
            VSME_DEFAULTS
        )
        
        self.assertIsNotNone(processor)
        self.assertEqual(processor._defaults, VSME_DEFAULTS)

    def test_load_json_data_from_string_io(self):
        """Test loading JSON data from StringIO."""
        json_string = json.dumps(self.sample_json_data)
        json_file_like = StringIO(json_string)
        results = ConversionResultsBuilder()
        
        processor = JsonProcessor(
            json_file_like,
            results,
            VSME_DEFAULTS
        )
        
        processor._loadJsonData()
        self.assertEqual(processor._jsonData, self.sample_json_data)

    def test_load_json_data_from_file(self):
        """Test loading JSON data from file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_json_data, f)
            temp_path = Path(f.name)
        
        try:
            results = ConversionResultsBuilder()
            processor = JsonProcessor(
                temp_path,
                results,
                VSME_DEFAULTS
            )
            
            processor._loadJsonData()
            self.assertEqual(processor._jsonData, self.sample_json_data)
        finally:
            temp_path.unlink()

    def test_validate_json_structure_valid(self):
        """Test JSON structure validation with valid data."""
        json_string = json.dumps(self.sample_json_data)
        json_file_like = StringIO(json_string)
        results = ConversionResultsBuilder()
        
        processor = JsonProcessor(
            json_file_like,
            results,
            VSME_DEFAULTS
        )
        
        processor._loadJsonData()
        # Should not raise any exception
        processor._validateJsonStructure()

    def test_validate_json_structure_missing_metadata(self):
        """Test JSON structure validation with missing metadata."""
        invalid_data = {"namedRanges": {}}
        json_string = json.dumps(invalid_data)
        json_file_like = StringIO(json_string)
        results = ConversionResultsBuilder()
        
        processor = JsonProcessor(
            json_file_like,
            results,
            VSME_DEFAULTS
        )
        
        processor._jsonData = invalid_data
        processor._validateJsonStructure()
        
        # Should have error messages
        self.assertFalse(results.conversionSuccessful)

    def test_validate_json_structure_missing_named_ranges(self):
        """Test JSON structure validation with missing namedRanges."""
        invalid_data = {"metadata": {"entity": {}}}
        json_string = json.dumps(invalid_data)
        json_file_like = StringIO(json_string)
        results = ConversionResultsBuilder()
        
        processor = JsonProcessor(
            json_file_like,
            results,
            VSME_DEFAULTS
        )
        
        processor._jsonData = invalid_data
        processor._validateJsonStructure()
        
        # Should have error messages
        self.assertFalse(results.conversionSuccessful)

    def test_invalid_json_format(self):
        """Test handling of invalid JSON format."""
        invalid_json = "{ invalid json"
        json_file_like = StringIO(invalid_json)
        results = ConversionResultsBuilder()
        
        processor = JsonProcessor(
            json_file_like,
            results,
            VSME_DEFAULTS
        )
        
        with self.assertRaises(json.JSONDecodeError):
            processor._loadJsonData()

    def test_record_named_ranges(self):
        """Test recording named ranges from JSON."""
        json_string = json.dumps(self.sample_json_data)
        json_file_like = StringIO(json_string)
        results = ConversionResultsBuilder()
        
        processor = JsonProcessor(
            json_file_like,
            results,
            VSME_DEFAULTS
        )
        
        processor._loadJsonData()
        processor._recordNamedRanges()
        
        expected_named_ranges = self.sample_json_data["namedRanges"]
        self.assertEqual(processor._namedRanges, expected_named_ranges)

    def test_process_configuration(self):
        """Test configuration processing."""
        json_string = json.dumps(self.sample_json_data)
        json_file_like = StringIO(json_string)
        results = ConversionResultsBuilder()
        
        processor = JsonProcessor(
            json_file_like,
            results,
            VSME_DEFAULTS
        )
        
        # Mock taxonomy for testing
        class MockTaxonomy:
            class QNameMaker:
                @staticmethod
                def fromString(s):
                    return s
            
            class UTR:
                @staticmethod
                def getQNameForUnitId(unit_id):
                    return None
                    
                @staticmethod
                def valid(data_type, unit_qname):
                    return True
            
            def getConcept(self, name):
                return None
        
        processor._report = type('MockReport', (), {'taxonomy': MockTaxonomy()})()
        
        processor._processConfiguration()
        
        # Should have processed configuration without errors
        self.assertIsInstance(processor._configDataTypeToUnitMap, dict)
        self.assertIsInstance(processor._configCellValuesToTaxonomyLabels, dict)


if __name__ == '__main__':
    unittest.main()