The JSON to iXBRL conversion was failing with a generic error message due to an invalid entry point specification in the input JSON file. The conversion would abort early during taxonomy loading, preventing successful XBRL generation.

## Root Cause

The `entryPoint` field in the JSON metadata was set to `"template_reporting_schemaRef"`, which is a template reference used in Excel processing workflows. The JsonProcessor expects an actual VSME taxonomy schema URL to load the taxonomy definitions properly.

## Changes Made

**Fixed Entry Point Resolution**
- Changed `entryPoint` from `"template_reporting_schemaRef"` to `"https://xbrl.efrag.org/taxonomy/vsme/2025-07-30/vsme-all.xsd"`
- This allows the JsonProcessor to successfully load the VSME taxonomy during the `_verifyEntryPoint()` step

**Removed Redundant Template Ranges**
- Eliminated 8 template named ranges (`template_reporting_*`, `template_currency`) from the `namedRanges` section
- These template ranges duplicated information already provided in the metadata section and are unnecessary in JSON format
- The JsonProcessor correctly skips template ranges, but removing them avoids confusion and potential conflicts

## Before vs After

**Before (failing):**
```json
{
    "metadata": {
        "entryPoint": "template_reporting_schemaRef",
        // ... other metadata
    },
    "namedRanges": {
        "template_reporting_entity_name": "Example Corp",
        "template_reporting_entity_identifier": "12345",
        // ... 8 template ranges duplicating metadata
        "ScopeOneGrossGhgEmissions": { "value": 1250.5, "unit": "tCO2e" }
        // ... actual data
    }
}
```

**After (working):**
```json
{
    "metadata": {
        "entryPoint": "https://xbrl.efrag.org/taxonomy/vsme/2025-07-30/vsme-all.xsd",
        // ... other metadata
    },
    "namedRanges": {
        "ScopeOneGrossGhgEmissions": { "value": 1250.5, "unit": "tCO2e" }
        // ... only actual sustainability data
    }
}
```

## Validation

The corrected JSON file now passes all structural validation checks:
- ✅ Valid JSON syntax
- ✅ Proper VSME taxonomy entry point
- ✅ 23 clean named ranges with appropriate units
- ✅ Complete metadata structure
- ✅ No template/metadata conflicts

Fixes #3.

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
