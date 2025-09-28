import argparse
import logging
from pathlib import Path

import rich.traceback
from rich.logging import RichHandler

import mireport
import mireport.taxonomy
from mireport.arelle.report_info import (
    ARELLE_VERSION_INFORMATION,
    ArelleReportProcessor,
)
from mireport.cli import validateTaxonomyPackages
from mireport.conversionresults import ConversionResults, ConversionResultsBuilder
from mireport.jsonprocessor import (
    VSME_DEFAULTS,
    JsonProcessor,
)
from mireport.localise import EU_LOCALES, argparse_locale


def createArgParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract facts from JSON and generate XBRL HTML."
    )
    parser.add_argument("json_file", type=Path, help="Path to the JSON file")
    parser.add_argument(
        "output_path",
        type=Path,
        help="Path to save the output. Can be a directory or a file. Automatically creates directories and warns before overwriting files.",
    )
    parser.add_argument(
        "--output-locale",
        type=argparse_locale,
        default=None,
        help=f"Locale to use when formatting the output XBRL report (default: None). Examples:\n{sorted(EU_LOCALES)}",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Suppress overwrite warnings and force file replacement.",
    )
    parser.add_argument(
        "--devinfo",
        action=argparse.BooleanOptionalAction,
        help="Enable display of developer information issues (not normally visible to users)",
    )
    parser.add_argument(
        "--taxonomy-packages",
        type=str,
        nargs="*",
        default=None,
        help="Taxonomy packages to validate before conversion",
    )
    return parser


def parseArgs(parser: argparse.ArgumentParser) -> argparse.Namespace:
    """Parse command line arguments and validate inputs."""
    args = parser.parse_args()

    if args.taxonomy_packages:
        args.taxonomy_packages = validateTaxonomyPackages(
            args.taxonomy_packages,
            parser,
        )

    # Validate JSON file exists
    if not args.json_file.exists():
        parser.error(f"JSON file not found: {args.json_file}")
    
    if not args.json_file.suffix.lower() == '.json':
        parser.error(f"Input file must have .json extension: {args.json_file}")
    
    return args


def prepare_output_path(path: Path, force: bool) -> tuple[Path, bool]:
    """Prepare output path, handling directories and file conflicts."""
    dir_specified = path.is_dir() or (not path.exists() and not path.suffix)
    
    if dir_specified:
        path.mkdir(parents=True, exist_ok=True)
        path = path / "report.html"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    
    if path.exists() and not force:
        response = input(f"File {path} already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Conversion cancelled.")
            exit(1)
    
    return path, dir_specified


def doConversion(args: argparse.Namespace) -> tuple[ConversionResults, JsonProcessor]:
    resultsBuilder = ConversionResultsBuilder(consoleOutput=True)
    with resultsBuilder.processingContext(
        "mireport JSON to validated Inline Report"
    ) as pc:
        pc.mark("Loading taxonomy metadata")
        mireport.loadTaxonomyJSON()
        pc.addDevInfoMessage(
            f"Taxonomies available: {', '.join(mireport.taxonomy.listTaxonomies())}"
        )
        pc.mark(
            "Extracting data from JSON",
            additionalInfo=f"Using file: {args.json_file}",
        )
        json_processor = JsonProcessor(
            args.json_file,
            resultsBuilder,
            VSME_DEFAULTS,
            outputLocale=args.output_locale,
        )
        report = json_processor.populateReport()
        pc.mark("Generating Inline Report")
        reportFile = report.getInlineReport()
        reportPackage = report.getInlineReportPackage()

        output_path, dir_specified = prepare_output_path(args.output_path, args.force)
        if dir_specified:
            pc.addDevInfoMessage(
                f"Output directory specified. Saving main report as {output_path}"
            )

        # Save main HTML file
        with open(output_path, "wb") as f:
            f.write(reportFile.fileContent)
        pc.addDevInfoMessage(f"Inline Report saved to {output_path}")

        # Save ZIP package
        zip_path = output_path.with_suffix(".zip")
        with open(zip_path, "wb") as f:
            f.write(reportPackage.fileContent)
        pc.addDevInfoMessage(f"Report package saved to {zip_path}")

        pc.mark(
            "Validating Inline Report",
            additionalInfo=f"Using Arelle (XBRL Certified Software™) [{ARELLE_VERSION_INFORMATION}]",
        )
        arelle = ArelleReportProcessor(
            taxonomyPackages=args.taxonomy_packages,
        )
        arelle_results = arelle.validateReportPackage(reportPackage)
        resultsBuilder.addMessages(arelle_results.messages)

    return resultsBuilder.build(), json_processor


def outputMessages(
    args: argparse.Namespace, result: ConversionResults, json_processor: JsonProcessor
) -> None:
    """Output conversion messages and summary."""
    hasMessages = result.hasMessages(userOnly=True)
    messages = result.userMessages
    if args.devinfo:
        hasMessages = result.hasMessages()
        messages = result.developerMessages

    if hasMessages:
        print()
        print(f"Information and issues encountered ({len(messages)} messages):")
        for message in messages:
            print(f"\t{message}")

    if args.devinfo and json_processor.unusedNames:
        max_output = 40
        unused = json_processor.unusedNames
        if (num := len(unused)) > max_output:
            size = int(max_output / 2)
            unused = (
                unused[:size]
                + [f"... supressed {num - max_output} rows..."]
                + unused[-size:]
            )

        print(
            f"Unused names ({num}) from JSON data:",
            *unused,
            sep="\n\t",
        )
    
    if result.conversionSuccessful:
        print(f"\n✅ Conversion completed successfully!")
        print(f"📊 Generated facts from JSON data")
    else:
        print(f"\n❌ Conversion failed with errors.")
        exit(1)


def main() -> None:
    """Main entry point for JSON to XBRL conversion."""
    rich.traceback.install()
    logging.basicConfig(
        level=logging.WARNING,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )
    
    parser = createArgParser()
    args = parseArgs(parser)
    
    try:
        result, json_processor = doConversion(args)
        outputMessages(args, result, json_processor)
    except KeyboardInterrupt:
        print("\n🛑 Conversion interrupted by user.")
        exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        if args.devinfo:
            raise
        exit(1)


if __name__ == "__main__":
    main()
