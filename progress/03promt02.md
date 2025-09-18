Debug JSON to iXBRL Conversion Failure

### **Context:**

We are implementing a feature to convert a JSON file into an iXBRL report. This process uses a custom `JsonProcessor` that is meant to work with the European VSME taxonomy. In our last session, we created the initial input file, `digital-templates/example-vsme-data.json`.

### **Problem:**

The conversion process is failing with a generic error message:

```
Conversion Results

Technical conversion to XBRL failed! Review the messages below and ensure the official template is used and correctly filled.
XBRL Report not validated due to conversion failure.
```

The conversion tool produced a log/output file that may contain clues.

### **Objective:**

Analyze the provided files to identify the root cause of the conversion failure and correct the input JSON file.

### **Files for Analysis:**

1.  **Input Data File:** `/digital-templates/example-vsme-data.json` (This is the file that needs to be corrected).
2.  **Output File (I have provided that excel converter produces):** `/output/output.json` (Analyze this file to find as reference specific errors or clues about the failure).
3.  **Reference Prompt & Report:** `/promts/promt01.md` and `/promts/report01.md` (Use these for background context on the expected structure and logic).

### **Task:**

1.  **Analyze the Error Log:** Examine `/output/output.json` to pinpoint the specific technical reasons for the conversion failure.
2.  **Identify Discrepancies:** Compare the input data in `example-vsme-data.json` against the requirements derived from the error log and our previous discussions. Look for issues like missing required fields, incorrect data types, or structural errors.
3.  **Propose Corrections:** Based on your analysis, detail the specific changes needed to fix `example-vsme-data.json`.
4.  ** Make the changes to fix the error.

### **Deliverables:**

Please provide a response in Markdown that includes:

* A clear, concise **summary of the root cause** of the error.
* A **bulleted list** of the specific corrections you made.
* A complete, corrected code block of the `example-vsme-data.json` file.