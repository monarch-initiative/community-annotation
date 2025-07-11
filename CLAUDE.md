# Community Annotation Validator

An MCP server for validating disease annotations against source publications using aurelian's pubmed utilities.

## Overview

This project provides tools for validating supporting text in disease annotations against their referenced publications. It uses:

- **Aurelian's pubmed utilities** for robust paper fetching (full text + fallback to abstracts)
- **YAML-based annotation format** for rich evidence tracking
- **MCP server** for real-time validation during curation
- **Text matching with confidence scoring** for validation

## Installation

```bash
# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

## Annotation Format

We use YAML format for annotations with the following structure:

```yaml
disease_id: "MONDO:0018484"
disease_name: "Semicircular Canal Dehiscence Syndrome"
last_updated: "2025-01-10"

phenotypic_features:
  - hpo_id: "HP:0002321"
    hpo_name: "Vertigo"
    evidence_code: "PCS"
    references: ["PMID:9525507", "PMID:33522990"]
    frequency: "60/65"
    frequency_supporting_text: 
      - text: "Vestibular manifestations were present in 60 (92.3%) patients"
        reference: "PMID:25992092"
        page_section: "Results"
    supporting_text:
      - text: "Eight patients with vertigo, oscillopsia, and/or disequilibrium"
        reference: "PMID:9525507"
        page_section: "Abstract"
    curator_notes: "Vertigo is the most common manifestation"
    curator: "ORCID:0000-0003-3311-7320"
    curation_date: "2025-01-10"
```

### Key Fields:
- `supporting_text`: List of text evidence with references and page sections
- `frequency_supporting_text`: Evidence for frequency claims
- `curator`: ORCID ID with "ORCID:" prefix
- `evidence_code`: "PCS" for Published Clinical Study

## MCP Server Usage

### Configuration

This repo is configured with MCP servers in `.claude_code/mcp_settings.json`:

- **annotation-validator** - Our custom validator using aurelian's pubmed utilities

### Manual Usage

You can also start the MCP server manually:

```bash
uv run simple-aurelian-annotation-validator-mcp
```

### Available Tools:

1. **fetch_paper** - Fetch paper content using aurelian
2. **validate_supporting_text** - Validate individual supporting text
3. **validate_hpo_annotation** - Validate complete HPO annotations
4. **validate_annotation_file** - Validate entire annotation files
5. **cache_papers_from_annotation** - Pre-fetch papers for faster validation

### Example Validation Results:

```
HPO Annotation Validation: HP:0002321 (Vertigo)

📊 Summary:
- Total supporting texts: 4
- Found in papers: 4/4 (100.0%)
- High confidence (>0.8): 4/4 (100.0%)
- Average confidence: 0.993
```

## Validation Logic

The system:

1. **Fetches papers** using aurelian's `get_pmid_text` (full text when available)
2. **Performs text matching** with confidence scoring:
   - Exact matches = 1.0 confidence
   - Word-based similarity for partial matches
   - Context extraction around matches
3. **Reports results** with confidence thresholds:
   - 🟢 High confidence (>0.8)
   - 🟡 Medium confidence (0.5-0.8) 
   - 🔴 Low confidence (<0.5)

## File Structure

```
├── src/annotation_validator/
│   ├── __init__.py
│   └── simple_aurelian_mcp.py          # Main MCP server
├── semicircular_canal_dehiscence_syndrome.annotations.yaml
├── pyproject.toml
├── CLAUDE.md
└── README.md
```

## Quality Control Checklist

When curating annotations:

1. ✅ Use exact quotes from papers as supporting text
2. ✅ Include page section information when possible
3. ✅ Use ORCID with "ORCID:" prefix for curator field
4. ✅ Validate all supporting text achieves >0.8 confidence
5. ✅ Ensure papers are relevant to the disease being annotated
6. ✅ Use PCS evidence code for clinical studies
7. ✅ Represent frequencies as fractions when possible

## Curation Guidelines

- Never guess at or make up PMIDs

## Performance

Current validation results on SCDS annotation:
- **16/16 supporting texts validated (100%)**
- **All entries >0.8 confidence**
- **Average confidence: 0.993**
- **Full text retrieval for 3/3 papers**

## Dependencies

- `mcp>=1.0.0` - Model Context Protocol
- `pyyaml>=6.0.0` - YAML parsing
- `aurelian>=0.1.0` - Pubmed utilities for paper fetching

## Validation CLI

After creating annotations, always validate them using the CLI:

```bash
# Validate annotation file
uv run python src/annotation_validator/cli.py your_annotation_file.yaml

# Validate with lower threshold (more lenient)
uv run python src/annotation_validator/cli.py your_annotation_file.yaml --threshold 0.6

# Validate with verbose output
uv run python src/annotation_validator/cli.py your_annotation_file.yaml --verbose
```

The CLI will:
- ✅ Fetch papers using aurelian's utilities
- ✅ Validate all supporting text against source papers
- ✅ Show confidence scores (🟢 high, 🟡 medium, 🔴 low)
- ✅ Provide context where text was found
- ✅ Suggest alternatives for failed validations
- ✅ Exit with error code if validation fails

## Commands

```bash
# Validate annotations (always do this after creating/updating)
uv run python src/annotation_validator/cli.py annotation_file.yaml

# Run MCP server
uv run simple-aurelian-annotation-validator-mcp

# Install/update dependencies
uv sync

# Format code
uv run black src/
uv run ruff src/
```

## Curation Memories

- Always fetch papers before trying to create or update annotations