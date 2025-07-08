# HPO Annotation Format Specification

This document describes the Human Phenotype Ontology (HPO) annotation format, specifically the `phenotype.hpoa` file format used for annotating diseases with phenotypic features.

## File Format Overview

The HPO annotation format is a tab-separated value (TSV) file containing 13 columns. Each row represents a single annotation linking a disease to a phenotypic feature from the HPO ontology.

## File Structure

- **File extension**: `.hpoa.tsv`
- **Format**: Tab-separated values (TSV)
- **Metadata**: Lines beginning with `#` contain metadata and comments
- **Header**: Column names are specified in a header line
- **Data**: Each subsequent line represents one annotation

## Column Specifications

### 1. DatabaseID (Required)
- **Type**: CURIE identifier
- **Description**: Unique identifier for the disease from a recognized database
- **Format**: `Database:Identifier`
- **Example**: `MIM:154700`

### 2. DiseaseName (Required)
- **Type**: Text string
- **Description**: The accepted name of the disease
- **Note**: Must use the official disease name, not synonyms

### 3. Qualifier (Optional)
- **Type**: Text string
- **Description**: Indicates negation of the phenotypic feature
- **Allowed values**: `NOT` or empty
- **Usage**: Use `NOT` to indicate the absence of a phenotypic feature

### 4. HPO_ID (Required)
- **Type**: HPO term identifier
- **Description**: The HPO identifier for the phenotypic feature
- **Format**: `HP:XXXXXXX`
- **Example**: `HP:0002487`

### 5. HPO_Name (Required)
- **Type**: Text string
- **Description**: The human-readable name of the HPO phenotypic feature
- **Note**: Should correspond to the official HPO term name for the HPO_ID
- **Example**: `Scoliosis`

### 6. DB_Reference (Required)
- **Type**: Database reference
- **Description**: Source of the annotation information
- **Allowed formats**:
  - `OMIM:XXXXXX` - Online Mendelian Inheritance in Man
  - `PMID:XXXXXXX` - PubMed identifier
  - `HPO:Ref` - HPO internal reference
- **Example**: `OMIM:154700`, `PMID:15517394`

### 7. Evidence (Required)
- **Type**: Evidence code
- **Description**: Level of evidence supporting the annotation
- **Allowed values**:
  - `IEA` - Inferred from Electronic Annotation
  - `PCS` - Published Clinical Study
  - `TAS` - Traceable Author Statement

### 8. Onset (Optional)
- **Type**: HPO term identifier
- **Description**: Age of onset for the phenotypic feature
- **Format**: HPO term from the "Age of onset" subontology (HP:0003674)
- **Example**: `HP:0003577` (Congenital onset)

### 9. Frequency (Optional)
- **Type**: Frequency specification
- **Description**: How frequently the phenotypic feature occurs
- **Allowed formats**:
  - HPO frequency term (e.g., `HP:0040280` - Obligate)
  - Patient count (e.g., `7/13`)
  - Percentage (e.g., `17%`)

### 10. Sex (Optional)
- **Type**: Text string
- **Description**: Sex limitation of the phenotypic feature
- **Allowed values**: `MALE` or `FEMALE`
- **Note**: Refers to phenotypic sex, not chromosomal sex

### 11. Modifier (Optional)
- **Type**: HPO term identifier
- **Description**: Clinical modifier for the phenotypic feature
- **Format**: HPO term from the "Clinical modifier" subontology

### 12. Aspect (Required)
- **Type**: Single character code
- **Description**: Aspect of the annotation
- **Allowed values**:
  - `P` - Phenotypic abnormality
  - `I` - Inheritance pattern
  - `C` - Clinical course
  - `M` - Clinical modifier

### 13. BiocurationBy (Required)
- **Type**: Curator information
- **Description**: Information about who created the annotation and when
- **Format**: `HPO:curator_name[YYYY-MM-DD]`
- **Multiple curators**: Separated by semicolon
- **Example**: `HPO:probinson[2012-04-24]`

## Example Annotation

```
MIM:154700	Marfan syndrome	NOT	HP:0002487	Scoliosis	OMIM:154700	IEA	HP:0003577	HP:0040280	MALE	HP:0031797	P	HPO:probinson[2012-04-24]
```

## Validation Rules

1. **Required fields**: DatabaseID, DiseaseName, HPO_ID, HPO_Name, DB_Reference, Evidence, Aspect, and BiocurationBy must be present
2. **HPO term validation**: HPO_ID, Onset, Frequency (if HPO term), and Modifier must be valid HPO identifiers
3. **HPO name consistency**: HPO_Name must correspond to the official term name for the given HPO_ID
4. **Evidence codes**: Must be one of the allowed evidence codes (IEA, PCS, TAS)
5. **Aspect codes**: Must be one of the allowed aspect codes (P, I, C, M)
6. **Sex values**: If specified, must be exactly "MALE" or "FEMALE"
7. **Date format**: Dates in BiocurationBy must follow YYYY-MM-DD format
8. **Qualifier**: If specified, must be "NOT"

## Common Use Cases

- **Disease-phenotype associations**: Link diseases to their characteristic phenotypic features
- **Negative annotations**: Use "NOT" qualifier to indicate absence of typically associated features
- **Clinical data integration**: Incorporate literature-based and clinical study evidence
- **Computational analysis**: Enable phenotype-based disease classification and analysis

## File Processing Notes

- Empty fields should be represented as empty strings between tabs
- Lines beginning with `#` are metadata and should be preserved
- The file should be UTF-8 encoded
- Tab characters (`\t`) are used as field separators
- Each annotation should be on a separate line
