#!/usr/bin/env python3
"""
Validate supporting text in annotation files against source publications.

This script takes an annotation YAML file and verifies that the supporting text
quotes actually appear in the referenced publications.
"""

import argparse
import yaml
import asyncio
import time
import requests
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import re
import sys
from aurelian.utils.pubmed_utils import get_pmid_text


@dataclass
class ValidationResult:
    """Result of validating a single supporting text entry."""
    hpo_id: str
    hpo_name: str
    text: str
    reference: str
    found: bool
    similarity_score: Optional[float] = None
    disease_relevant: Optional[bool] = None
    disease_relevance_score: Optional[float] = None
    error: Optional[str] = None
    context: Optional[str] = None
    suggestions: Optional[List[str]] = None


class PMIDFetcher:
    """Fetch publication content using aurelian's pubmed utilities."""
    
    def __init__(self):
        self.cache = {}
    
    async def fetch_content(self, pmid: str) -> Optional[str]:
        """Fetch paper content using aurelian's get_pmid_text."""
        if pmid in self.cache:
            return self.cache[pmid]
        
        try:
            # Use aurelian's get_pmid_text which handles full text + fallback to abstract
            content = await asyncio.to_thread(get_pmid_text, pmid)
            if content:
                self.cache[pmid] = content
                return content
            else:
                print(f"Warning: Could not fetch content for {pmid}")
                return None
                
        except Exception as e:
            print(f"Error fetching {pmid}: {e}")
            return None


class TextValidator:
    """Validate supporting text against publication content."""
    
    def __init__(self, fetcher: PMIDFetcher, disease_name: str = "", disease_id: str = ""):
        self.fetcher = fetcher
        self.disease_name = disease_name
        self.disease_id = disease_id
        self.disease_keywords = self._extract_disease_keywords(disease_name, disease_id)
    
    def _fetch_disease_synonyms(self, disease_id: str) -> List[str]:
        """Fetch disease synonyms from Monarch API."""
        if not disease_id:
            return []
        
        try:
            url = f"https://api.monarchinitiative.org/v3/api/entity/{disease_id}"
            response = requests.get(url)
            response.raise_for_status()
            
            data = response.json()
            synonyms = []
            
            # Extract synonyms from the response
            if 'synonyms' in data:
                synonyms.extend([syn.get('val', '') for syn in data['synonyms'] if syn.get('val')])
            
            # Also check for alternative names in other fields
            if 'name' in data:
                synonyms.append(data['name'])
            
            # Clean and normalize synonyms
            clean_synonyms = []
            for syn in synonyms:
                if syn and isinstance(syn, str):
                    clean_synonyms.append(syn.lower().strip())
            
            return list(set(clean_synonyms))  # Remove duplicates
            
        except Exception as e:
            print(f"Warning: Could not fetch synonyms for {disease_id}: {e}")
            return []
    
    def _extract_disease_keywords(self, disease_name: str, disease_id: str = "") -> List[str]:
        """Extract key terms from disease name and synonyms for relevance checking."""
        keywords = []
        
        # Start with disease name if provided
        if disease_name:
            # Split on common separators and normalize
            words = re.split(r'[,\s\-_]+', disease_name.lower())
            
            # Filter out common words
            stop_words = {'syndrome', 'disease', 'disorder', 'the', 'of', 'and', 'or', 'a', 'an'}
            keywords.extend([word for word in words if word and word not in stop_words and len(word) > 2])
            
            # Add the full disease name (normalized)
            keywords.append(disease_name.lower())
        
        # Fetch and add synonyms from Monarch API
        if disease_id:
            synonyms = self._fetch_disease_synonyms(disease_id)
            keywords.extend(synonyms)
            
            # Also extract words from synonyms
            for synonym in synonyms:
                words = re.split(r'[,\s\-_]+', synonym.lower())
                stop_words = {'syndrome', 'disease', 'disorder', 'the', 'of', 'and', 'or', 'a', 'an'}
                keywords.extend([word for word in words if word and word not in stop_words and len(word) > 2])
        
        return list(set(keywords))  # Remove duplicates
    
    def check_disease_relevance(self, content: str) -> tuple[bool, float]:
        """Check if publication content is relevant to the disease."""
        if not self.disease_keywords:
            return True, 1.0  # No keywords to check against
        
        normalized_content = self.normalize_text(content)
        
        # Count keyword matches
        matches = 0
        total_keywords = len(self.disease_keywords)
        
        for keyword in self.disease_keywords:
            if keyword in normalized_content:
                matches += 1
        
        relevance_score = matches / total_keywords if total_keywords > 0 else 0.0
        
        # Consider relevant if at least 20% of keywords match, or if key disease terms found
        is_relevant = relevance_score >= 0.2
        
        # Boost relevance for exact disease name matches
        if self.disease_name and self.disease_name.lower() in normalized_content:
            is_relevant = True
            relevance_score = max(relevance_score, 0.8)
        
        return is_relevant, relevance_score
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        # Remove extra whitespace, normalize quotes, etc.
        text = re.sub(r'\s+', ' ', text.strip())
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        return text.lower()
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple similarity score between two texts."""
        # Simple word-based similarity
        words1 = set(self.normalize_text(text1).split())
        words2 = set(self.normalize_text(text2).split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    def find_text_in_content(self, supporting_text: str, content: str, threshold: float = 0.8) -> tuple[bool, float, str, List[str]]:
        """Find supporting text in publication content and provide suggestions."""
        normalized_supporting = self.normalize_text(supporting_text)
        normalized_content = self.normalize_text(content)
        
        # Exact match
        if normalized_supporting in normalized_content:
            match_pos = normalized_content.find(normalized_supporting)
            start = max(0, match_pos - 100)
            end = min(len(content), match_pos + len(supporting_text) + 100)
            context = content[start:end].strip()
            return True, 1.0, context, []
        
        # Check for high similarity matches in sentences
        content_sentences = re.split(r'[.!?]+', content)
        best_similarity = 0.0
        best_sentence = ""
        suggestions = []
        
        for sentence in content_sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:  # Skip very short sentences
                continue
                
            similarity = self.calculate_similarity(normalized_supporting, sentence)
            if similarity > best_similarity:
                best_similarity = similarity
                best_sentence = sentence
            
            # Collect potential suggestions (sentences with decent similarity)
            if similarity >= 0.5:
                suggestions.append(f"Similarity {similarity:.2f}: {sentence[:100]}...")
            
            if similarity >= threshold:
                return True, similarity, sentence, suggestions
        
        # Limit suggestions to top 3
        suggestions = sorted(suggestions, key=lambda x: float(x.split()[1][:-1]), reverse=True)[:3]
        
        return False, best_similarity, best_sentence, suggestions
    
    async def validate_supporting_text(self, text: str, reference: str) -> ValidationResult:
        """Validate a single supporting text entry."""
        # For now, only handle PMID references
        if not reference.startswith("PMID:"):
            return ValidationResult(
                hpo_id="", hpo_name="", text=text, reference=reference,
                found=False, error="Only PMID references supported"
            )
        
        content = await self.fetcher.fetch_content(reference)
        if content is None:
            return ValidationResult(
                hpo_id="", hpo_name="", text=text, reference=reference,
                found=False, error="Could not fetch publication content"
            )
        
        # Check disease relevance first
        disease_relevant, disease_relevance_score = self.check_disease_relevance(content)
        
        # Check text match
        found, similarity, context, suggestions = self.find_text_in_content(text, content)
        
        return ValidationResult(
            hpo_id="", hpo_name="", text=text, reference=reference,
            found=found, similarity_score=similarity,
            disease_relevant=disease_relevant, disease_relevance_score=disease_relevance_score,
            context=context, suggestions=suggestions
        )


def load_annotation_file(filepath: str) -> Dict[str, Any]:
    """Load annotation YAML file."""
    with open(filepath, 'r') as f:
        return yaml.safe_load(f)


async def validate_annotation_file(filepath: str, similarity_threshold: float = 0.8) -> List[ValidationResult]:
    """Validate all supporting text in an annotation file."""
    print(f"Loading annotation file: {filepath}")
    data = load_annotation_file(filepath)
    
    disease_name = data.get('disease_name', '')
    disease_id = data.get('disease_id', '')
    print(f"Disease: {disease_name} ({disease_id})")
    
    fetcher = PMIDFetcher()
    validator = TextValidator(fetcher, disease_name, disease_id)
    results = []
    
    # Process all annotation sections
    sections = ['phenotypic_features', 'inheritance', 'clinical_course', 'diagnostic_methodology']
    
    for section_name in sections:
        if section_name not in data:
            continue
            
        print(f"\nValidating {section_name}...")
        section = data[section_name]
        
        for annotation in section:
            # Handle different annotation types
            if section_name == 'diagnostic_methodology':
                # Diagnostic methodology has different fields
                method_name = annotation.get('method_name', '')
                method_id = annotation.get('method_id', '')
                identifier = f"{method_name} ({method_id})" if method_id else method_name
                print(f"  Checking {identifier}")
            else:
                # Standard HPO-based annotations
                hpo_id = annotation.get('hpo_id', '')
                hpo_name = annotation.get('hpo_name', '')
                if hpo_id and hpo_name:
                    print(f"  Checking {hpo_id} ({hpo_name})")
                identifier = f"{hpo_id} ({hpo_name})" if hpo_id and hpo_name else "Unknown"
            
            # Validate main supporting text
            supporting_texts = annotation.get('supporting_text', [])
            for support_entry in supporting_texts:
                text = support_entry.get('text', '')
                reference = support_entry.get('reference', '')
                
                if text and reference:
                    result = await validator.validate_supporting_text(text, reference)
                    if section_name == 'diagnostic_methodology':
                        result.hpo_id = method_name
                        result.hpo_name = annotation.get('method_type', '')
                    else:
                        result.hpo_id = annotation.get('hpo_id', '')
                        result.hpo_name = annotation.get('hpo_name', '')
                    results.append(result)
            
            # Validate frequency supporting text (only for non-diagnostic methodology sections)
            if section_name != 'diagnostic_methodology':
                freq_texts = annotation.get('frequency_supporting_text', [])
                for support_entry in freq_texts:
                    text = support_entry.get('text', '')
                    reference = support_entry.get('reference', '')
                    
                    if text and reference:
                        result = await validator.validate_supporting_text(text, reference)
                        result.hpo_id = annotation.get('hpo_id', '')
                        result.hpo_name = annotation.get('hpo_name', '')
                        results.append(result)
    
    return results


def print_validation_report(results: List[ValidationResult]):
    """Print a validation report with actionable suggestions."""
    total = len(results)
    found = sum(1 for r in results if r.found)
    disease_relevant = sum(1 for r in results if r.disease_relevant)
    disease_irrelevant = sum(1 for r in results if r.disease_relevant is False)
    
    print(f"\n{'='*80}")
    print(f"ANNOTATION VALIDATION REPORT")
    print(f"{'='*80}")
    print(f"Total supporting text entries: {total}")
    print(f"✓ Found in publications: {found}")
    print(f"✗ Not found: {total - found}")
    print(f"🎯 Disease-relevant publications: {disease_relevant}")
    print(f"❌ Disease-irrelevant publications: {disease_irrelevant}")
    print(f"Success rate: {found/total*100:.1f}%" if total > 0 else "No entries to validate")
    print(f"Relevance rate: {disease_relevant/total*100:.1f}%" if total > 0 else "No entries to check")
    
    print(f"\n{'DETAILED RESULTS'}")
    print(f"{'-'*80}")
    
    for i, result in enumerate(results, 1):
        status = "✓ FOUND" if result.found else "✗ NOT FOUND"
        conf_icon = "🟢" if result.similarity_score and result.similarity_score > 0.8 else "🟡" if result.similarity_score and result.similarity_score > 0.5 else "🔴"
        similarity = f" (confidence: {result.similarity_score:.3f})" if result.similarity_score else ""
        
        # Disease relevance indicator
        if result.disease_relevant is not None:
            relevance_icon = "🎯" if result.disease_relevant else "❌"
            relevance_text = f" {relevance_icon}"
            if result.disease_relevance_score is not None:
                relevance_text += f" (relevance: {result.disease_relevance_score:.2f})"
        else:
            relevance_text = ""
        
        print(f"\n{i}. {status} {conf_icon}{similarity}{relevance_text}")
        
        if result.hpo_id:
            print(f"   HPO: {result.hpo_id} ({result.hpo_name})")
        print(f"   Reference: {result.reference}")
        print(f"   Text: {result.text}")
        
        if result.error:
            print(f"   ❌ Error: {result.error}")
        
        if result.context:
            print(f"   📍 Context: {result.context[:200]}{'...' if len(result.context) > 200 else ''}")
        
        if result.suggestions:
            print(f"   💡 Suggestions for improvement:")
            for suggestion in result.suggestions:
                print(f"      • {suggestion}")
    
    # Summary of failed validations
    failed_results = [r for r in results if not r.found]
    if failed_results:
        print(f"\n{'='*80}")
        print(f"FAILED VALIDATIONS SUMMARY")
        print(f"{'='*80}")
        print(f"The following {len(failed_results)} supporting text entries need attention:")
        
        for i, result in enumerate(failed_results, 1):
            print(f"\n{i}. {result.hpo_id} ({result.hpo_name})")
            print(f"   Reference: {result.reference}")
            print(f"   Text: {result.text[:80]}{'...' if len(result.text) > 80 else ''}")
            if result.error:
                print(f"   Issue: {result.error}")
            elif result.suggestions:
                print(f"   Best alternative: {result.suggestions[0] if result.suggestions else 'No suggestions'}")
            print(f"   Action needed: {'Check PMID validity' if result.error else 'Update supporting text or find better quote'}")
    
    print(f"\n{'='*80}")
    print(f"NEXT STEPS")
    print(f"{'='*80}")
    
    if failed_results:
        print("1. For failed validations:")
        print("   - Verify PMID references are correct")
        print("   - Update supporting text to match exact quotes from papers")
        print("   - Consider using suggested alternatives if available")
        print("   - Remove entries that cannot be validated")
        
    if disease_irrelevant > 0:
        print("2. For disease-irrelevant papers:")
        print("   - Check if PMIDs are correct for the disease being annotated")
        print("   - Consider finding more specific publications")
        
    if found == total:
        print("🎉 All supporting text entries validated successfully!")
        print("   - Consider adding more phenotypic features if needed")
        print("   - Review frequency data and inheritance patterns")
    
    print(f"\n{'='*80}")


async def main():
    parser = argparse.ArgumentParser(description="Validate supporting text in annotation files")
    parser.add_argument("annotation_file", help="Path to annotation YAML file")
    parser.add_argument("--threshold", type=float, default=0.8, 
                       help="Similarity threshold for text matching (default: 0.8)")
    parser.add_argument("--verbose", action="store_true", 
                       help="Print verbose output")
    
    args = parser.parse_args()
    
    try:
        results = await validate_annotation_file(args.annotation_file, args.threshold)
        print_validation_report(results)
        
        # Exit with error code if validation failed
        failed_count = sum(1 for r in results if not r.found)
        if failed_count > 0:
            print(f"\nValidation failed: {failed_count} supporting text entries could not be verified.")
            sys.exit(1)
        else:
            print("\nAll supporting text entries validated successfully!")
            sys.exit(0)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())