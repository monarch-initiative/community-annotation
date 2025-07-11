# Disease Annotation Format Specification

## Overview

This document describes the YAML-based annotation format for capturing disease-phenotype associations with rich supporting evidence. This format replaces traditional HPOA files with a more flexible, transparent, and collaborative structure.

## File Structure

Each disease gets a single `.annotations.yaml` file containing all phenotypic features, inheritance patterns, and clinical course information.

## Top-Level Fields

```yaml
disease_id: "MONDO:XXXXXXX"     # Required: MONDO identifier
disease_name: "Disease Name"     # Required: Human-readable disease name
last_updated: "YYYY-MM-DD"      # Required: ISO date format
```

## Annotation Sections

Annotations are organized by aspect type into separate sections:

### phenotypic_features
Clinical manifestations, symptoms, and observable traits

### inheritance
Inheritance patterns and genetic transmission modes

### clinical_course
Onset timing, progression, severity, and disease course information

## Annotation Object Structure

Each annotation within a section contains:

### Required Fields

- **hpo_id**: HPO term identifier (e.g., "HP:0002321")
- **hpo_name**: Human-readable HPO term name
- **evidence_code**: Evidence type (typically "PCS" for Published Clinical Study)
- **references**: List of supporting PMIDs
- **supporting_text**: List of evidence objects (see below)
- **curator**: ORCID identifier of the curator
- **curation_date**: Date of annotation in ISO format (YYYY-MM-DD)

### Optional Fields

- **frequency**: Prevalence data (preferred order: fractions > percentages > HPO frequency codes)
- **frequency_supporting_text**: List of evidence objects supporting frequency claims
- **curator_notes**: Additional context, caveats, or clarifications

## Supporting Text Object Structure

Each supporting text entry contains:

```yaml
- text: "Direct quote or paraphrased evidence"
  reference: "PMID:XXXXXXX"
  page_section: "Location in paper (e.g., Table 1, Results, Abstract)"
```

## Frequency Guidelines

1. **Fractions**: Use when specific numbers are reported (e.g., "60/65")
2. **Percentages**: Use when percentages are explicitly stated (e.g., "92%")
3. **HPO frequency qualifiers**: Use only when precise data unavailable (HP:0040281, HP:0040282, etc.)
4. **Leave null**: When only broad symptom categories are available without phenotype-specific breakdown

## Complete Example

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
        reference: "PMID:9525507"
        page_section: "Results"
    supporting_text:
      - text: "sound- and/or pressure-induced vertigo"
        reference: "PMID:9525507"
        page_section: "Abstract"
      - text: "Symptoms and vestibular nystagmus triggered by noise or pressure change"
        reference: "PMID:33522990"
        page_section: "Table 1"
    curator_notes: "Part of vestibular manifestations in Minor's original cohort"
    curator: "0000-0000-0000-0000"
    curation_date: "2025-01-10"
    
  - hpo_id: "HP:0008629"
    hpo_name: "Pulsatile tinnitus"
    evidence_code: "PCS"
    references: ["PMID:33522990"]
    frequency: null
    frequency_supporting_text: []
    supporting_text:
      - text: "pulsatile tinnitus"
        reference: "PMID:33522990"
        page_section: "Diagnostic criteria - Category 1"
    curator_notes: "One of four key symptoms in Bárány Society consensus criteria"
    curator: "0000-0000-0000-0000"
    curation_date: "2025-01-10"

inheritance:
  - hpo_id: "HP:0000006"
    hpo_name: "Autosomal dominant inheritance"
    evidence_code: "PCS"
    references: ["PMID:12345678"]
    supporting_text:
      - text: "autosomal dominant pattern of inheritance"
        reference: "PMID:12345678"
        page_section: "Genetics section"
    curator_notes: "Based on family studies"
    curator: "0000-0001-2345-6789"
    curation_date: "2025-01-15"

clinical_course:
  - hpo_id: "HP:0003581"
    hpo_name: "Adult onset"
    evidence_code: "PCS"
    references: ["PMID:9525507"]
    supporting_text:
      - text: "Patients tend to present with symptoms during the fifth and sixth decades of life"
        reference: "PMID:9525507"
        page_section: "Demographics"
    curator_notes: "Typical age of symptom onset"
    curator: "0000-0000-0000-0000"
    curation_date: "2025-01-10"
```

## Benefits

- **Transparency**: Full supporting evidence with precise attribution
- **Flexibility**: Easy to add new fields and annotation types
- **Collaboration**: Individual curator tracking at annotation level
- **Validation**: Granular evidence linking for verification
- **Rich metadata**: Page sections, curator notes, and confidence tracking
- **Backwards compatibility**: Can generate HPOA files when needed

## Validation

All annotations should be validated for:
- HPO term existence and accuracy
- PMID validity and accessibility
- Supporting text accuracy against source material
- Proper ORCID formatting for curators
- ISO date formatting for all date fields