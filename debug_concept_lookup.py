#!/usr/bin/env python3

import json
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

import mireport
from mireport.taxonomy import getTaxonomy

def debug_concept_lookup(json_file_path):
    """Debug concept lookup for the JSON file."""
    print(f"=== Debugging Concept Lookup for {json_file_path} ===\n")

    # Load JSON data
    with open(json_file_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    # Load taxonomy metadata
    print("Loading taxonomy metadata...")
    mireport.loadTaxonomyJSON()

    # Get entry point
    metadata = json_data.get('metadata', {})
    entry_point = metadata.get('entryPoint', 'https://xbrl.efrag.org/taxonomy/vsme/2025-07-30/vsme-all.xsd')
    print(f"Entry point: {entry_point}")

    # Load taxonomy
    print("Loading taxonomy...")
    try:
        taxonomy = getTaxonomy(entry_point)
        print(f"Taxonomy loaded successfully")
    except Exception as e:
        print(f"Failed to load taxonomy: {e}")
        return

    # Get named ranges
    named_ranges = json_data.get('namedRanges', {})
    print(f"\nFound {len(named_ranges)} named ranges")

    # Test concept lookup for each named range
    found_concepts = 0
    missing_concepts = []

    for name, value in list(named_ranges.items())[:20]:  # Test first 20
        if name.startswith(("enum_", "template_")):
            continue

        concept = taxonomy.getConceptForName(name)
        if concept:
            found_concepts += 1
            print(f"✓ {name} -> {concept.name} (reportable: {concept.isReportable})")
        else:
            missing_concepts.append(name)
            print(f"✗ {name} -> NOT FOUND")

    print(f"\nSummary:")
    print(f"- Total named ranges checked: {min(20, len([n for n in named_ranges.keys() if not n.startswith(('enum_', 'template_'))]))}")
    print(f"- Found concepts: {found_concepts}")
    print(f"- Missing concepts: {len(missing_concepts)}")

    if missing_concepts:
        print(f"\nFirst 10 missing concepts:")
        for name in missing_concepts[:10]:
            print(f"  - {name}")

    # Check period info
    print(f"\nPeriod information:")
    period_info = metadata.get('reportingPeriod', {})
    if period_info:
        print(f"- Start: {period_info.get('start')}")
        print(f"- End: {period_info.get('end')}")
    else:
        print("- No reporting period found in metadata")

    # Try some alternative concept name formats
    if missing_concepts:
        print(f"\nTesting alternative name formats for first missing concept:")
        test_name = missing_concepts[0]
        print(f"Testing variations of: {test_name}")

        # Strip namespace prefix
        if ':' in test_name:
            simple_name = test_name.split(':', 1)[1]
            concept = taxonomy.getConceptForName(simple_name)
            if concept:
                print(f"✓ Found with simple name: {simple_name}")
            else:
                print(f"✗ Not found with simple name: {simple_name}")

        # Try with different prefixes
        for prefix in ['vsme', 'esrs', 'ifrs']:
            alt_name = f"{prefix}:{test_name.split(':', 1)[-1]}"
            if alt_name != test_name:
                concept = taxonomy.getConceptForName(alt_name)
                if concept:
                    print(f"✓ Found with prefix {prefix}: {alt_name}")
                    break
        else:
            print("✗ No alternative format worked")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python debug_concept_lookup.py <json_file>")
        sys.exit(1)

    debug_concept_lookup(sys.argv[1])