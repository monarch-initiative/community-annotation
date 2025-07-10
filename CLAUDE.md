# Disease Curation Process for HPO Annotation Files

**Objective**: Create a standardized .hpoa.tsv file for a disease by extracting phenotypic features from primary literature and mapping them to Human Phenotype Ontology (HPO) terms.

## Step-by-Step Process

### 1. Literature Search & Retrieval
- Search PubMed for key publications related to the disease
- Identify foundational papers, case reports, and clinical studies
- Fetch and read full abstracts/papers to extract clinical features

### 2. Phenotype Extraction
- Extract all clinical manifestations, symptoms, and characteristics described in the literature
- Note inheritance patterns, prevalence data, and onset information
- Document the specific PMIDs supporting each phenotype

### 3. HPO Term Mapping
- Use the Monarch Initiative API (https://api.monarchinitiative.org/v3/api/search) to search for appropriate HPO terms
- Verify HPO term definitions using the entity endpoint (https://api.monarchinitiative.org/v3/api/entity/HP:XXXXXX)
- Map clinical features to the most specific HPO terms available
- Use broader terms if specific ones don't exist

### 4. Annotation File Creation
- Format: DatabaseId, DB_Name, Qualifier, HPO_ID, HPO_Name, DB_Reference, Evidence, Onset, Frequency, Sex, Modifier, Aspect, BiocurationBy
- Use MONDO ID for disease identifier
- Include multiple PMIDs separated by semicolons for well-supported phenotypes
- Use "PCS" (Published Clinical Study) as evidence code
- Set Aspect to "P" (Phenotype) for clinical features, "I" (Inheritance) for inheritance patterns

#### Frequency Column Guidelines (in order of preference)
1. **Fractions**: Use when specific numbers are reported (e.g., "60/65" for 60 out of 65 patients)
2. **Percentages**: Use when percentages are explicitly stated (e.g., "92%")
3. **HPO frequency qualifiers**: Use only when precise data unavailable (HP:0040281, HP:0040282, etc.)
4. **Leave empty**: When only broad symptom category frequencies are available without phenotype-specific breakdown
- Be conservative: only include frequencies that are explicitly stated for the specific HPO term being annotated

### 5. Quality Control
- Verify HPO term accuracy against official definitions
- Ensure all phenotypes are supported by cited literature
- Check file format consistency with existing annotation files

## Key Tools
- PubMed literature search
- Monarch Initiative API
- HPO browser
- Primary literature review