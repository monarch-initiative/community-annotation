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
import aiohttp
from typing import Dict, List, Any, Optional, Tuple
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


@dataclass 
class IdentifierValidationResult:
    """Result of validating a method identifier."""
    method_name: str
    method_id: str
    valid: bool
    title_match: Optional[bool] = None
    retrieved_title: Optional[str] = None
    error: Optional[str] = None


class IdentifierValidator:
    """Validate method identifiers like DOI, LOINC, CPT codes."""
    
    def __init__(self):
        self.cache = {}
    
    async def validate_doi(self, method_name: str, doi: str) -> IdentifierValidationResult:
        """Validate a DOI and check if title matches method name."""
        if doi in self.cache:
            cached = self.cache[doi]
            return IdentifierValidationResult(
                method_name=method_name,
                method_id=doi,
                valid=cached['valid'],
                title_match=self._check_title_match(method_name, cached.get('title')),
                retrieved_title=cached.get('title'),
                error=cached.get('error')
            )
        
        try:
            # Use CrossRef API to validate DOI
            url = f"https://api.crossref.org/works/{doi}"
            response = await asyncio.to_thread(requests.get, url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                title = data['message']['title'][0] if data['message'].get('title') else None
                
                self.cache[doi] = {'valid': True, 'title': title}
                
                title_match = self._check_title_match(method_name, title)
                
                return IdentifierValidationResult(
                    method_name=method_name,
                    method_id=doi,
                    valid=True,
                    title_match=title_match,
                    retrieved_title=title,
                    error=None
                )
            else:
                error_msg = f"DOI not found (HTTP {response.status_code})"
                self.cache[doi] = {'valid': False, 'error': error_msg}
                
                return IdentifierValidationResult(
                    method_name=method_name,
                    method_id=doi,
                    valid=False,
                    title_match=None,
                    retrieved_title=None,
                    error=error_msg
                )
                
        except Exception as e:
            error_msg = f"Error validating DOI: {str(e)}"
            self.cache[doi] = {'valid': False, 'error': error_msg}
            
            return IdentifierValidationResult(
                method_name=method_name,
                method_id=doi,
                valid=False,
                title_match=None,
                retrieved_title=None,
                error=error_msg
            )
    
    def _check_title_match(self, method_name: str, retrieved_title: str) -> bool:
        """Check if method name appears in or matches the retrieved title."""
        if not retrieved_title:
            return False
        
        # Normalize both strings for comparison
        method_normalized = method_name.lower().strip()
        title_normalized = retrieved_title.lower().strip()
        
        # Check for key terms from method name in title
        method_words = set(re.findall(r'\b\w+\b', method_normalized))
        title_words = set(re.findall(r'\b\w+\b', title_normalized))
        
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'framework', 'criteria'}
        method_words -= stop_words
        title_words -= stop_words
        
        # Check if significant overlap exists
        if len(method_words) == 0:
            return False
        
        overlap = method_words.intersection(title_words)
        overlap_ratio = len(overlap) / len(method_words)
        
        # Consider it a match if >50% of meaningful words overlap
        return overlap_ratio > 0.5
    
    async def validate_identifier(self, method_name: str, method_id: str) -> IdentifierValidationResult:
        """Validate any type of identifier based on its format."""
        if not method_id or method_id.lower() == 'null':
            return IdentifierValidationResult(
                method_name=method_name,
                method_id=method_id,
                valid=True,  # null is valid (no identifier)
                title_match=None,
                retrieved_title=None,
                error=None
            )
        
        # Check if it's a DOI
        if method_id.startswith('DOI:'):
            doi = method_id[4:]  # Remove 'DOI:' prefix
            return await self.validate_doi(method_name, doi)
        elif method_id.startswith('10.'):
            # Direct DOI without prefix
            return await self.validate_doi(method_name, method_id)
        else:
            # For other identifier types (CPT, LOINC, etc.), we can't validate without APIs
            return IdentifierValidationResult(
                method_name=method_name,
                method_id=method_id,
                valid=True,  # Assume valid for now
                title_match=None,
                retrieved_title=None,
                error="Identifier type not validated (no API available)"
            )


class ContentFetcher:
    """Fetch publication content using aurelian's pubmed utilities and web content."""
    
    def __init__(self):
        self.cache = {}
    
    async def fetch_pmid_content(self, pmid: str) -> Optional[str]:
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
    
    async def fetch_url_content(self, url: str) -> Optional[str]:
        """Fetch web page content from URL."""
        if url in self.cache:
            return self.cache[url]
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)  # Set a 10-second timeout
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.text()
                        self.cache[url] = content
                        return content
                    else:
                        print(f"Warning: HTTP {response.status} for {url}")
                        return None
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    async def fetch_content(self, reference: str) -> Optional[str]:
        """Fetch content based on reference type (PMID or URL)."""
        if reference.startswith("PMID:"):
            return await self.fetch_pmid_content(reference)
        elif reference.startswith("http"):
            return await self.fetch_url_content(reference)
        else:
            print(f"Warning: Unsupported reference type: {reference}")
            return None


class TextValidator:
    """Validate supporting text against publication content."""
    
    def __init__(self, fetcher: ContentFetcher, disease_name: str = "", disease_id: str = ""):
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
        # Handle both PMID and URL references
        if not (reference.startswith("PMID:") or reference.startswith("http")):
            return ValidationResult(
                hpo_id="", hpo_name="", text=text, reference=reference,
                found=False, error="Only PMID and URL references supported"
            )
        
        content = await self.fetcher.fetch_content(reference)
        if content is None:
            return ValidationResult(
                hpo_id="", hpo_name="", text=text, reference=reference,
                found=False, error="Could not fetch content"
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


async def validate_annotation_file(filepath: str, similarity_threshold: float = 0.8) -> Tuple[List[ValidationResult], List[IdentifierValidationResult]]:
    """Validate all supporting text in an annotation file."""
    print(f"Loading annotation file: {filepath}")
    data = load_annotation_file(filepath)
    
    disease_name = data.get('disease_name', '')
    disease_id = data.get('disease_id', '')
    print(f"Disease: {disease_name} ({disease_id})")
    
    fetcher = ContentFetcher()
    validator = TextValidator(fetcher, disease_name, disease_id)
    identifier_validator = IdentifierValidator()
    results = []
    identifier_results = []
    
    # Process all annotation sections
    sections = ['phenotypic_features', 'inheritance', 'clinical_course', 'diagnostic_methodology', 'relevant_publications']
    
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
                
                # Validate method identifier if present
                if method_id and method_id != 'null':
                    id_result = await identifier_validator.validate_identifier(method_name, method_id)
                    identifier_results.append(id_result)
            elif section_name == 'relevant_publications':
                # Relevant publications section
                reference = annotation.get('reference', '')
                title = annotation.get('title', '')
                identifier = f"{reference} ({title[:50]}...)" if title else reference
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
                    elif section_name == 'relevant_publications':
                        result.hpo_id = annotation.get('reference', '')
                        result.hpo_name = annotation.get('title', '')
                    else:
                        result.hpo_id = annotation.get('hpo_id', '')
                        result.hpo_name = annotation.get('hpo_name', '')
                    results.append(result)
            
            # Validate frequency supporting text (only for HPO annotation sections)
            if section_name not in ['diagnostic_methodology', 'relevant_publications']:
                freq_texts = annotation.get('frequency_supporting_text', [])
                for support_entry in freq_texts:
                    text = support_entry.get('text', '')
                    reference = support_entry.get('reference', '')
                    
                    if text and reference:
                        result = await validator.validate_supporting_text(text, reference)
                        result.hpo_id = annotation.get('hpo_id', '')
                        result.hpo_name = annotation.get('hpo_name', '')
                        results.append(result)
    
    return results, identifier_results


def print_validation_report(results: List[ValidationResult], identifier_results: List[IdentifierValidationResult] = None):
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
    
    # Print identifier validation results if present
    if identifier_results:
        print(f"\n{'='*80}")
        print(f"IDENTIFIER VALIDATION REPORT")
        print(f"{'='*80}")
        
        valid_ids = sum(1 for r in identifier_results if r.valid)
        title_matches = sum(1 for r in identifier_results if r.title_match)
        total_ids = len(identifier_results)
        
        print(f"Total identifiers checked: {total_ids}")
        print(f"✓ Valid identifiers: {valid_ids}")
        print(f"✗ Invalid identifiers: {total_ids - valid_ids}")
        if title_matches > 0:
            print(f"📋 Title matches: {title_matches}")
        
        for i, result in enumerate(identifier_results, 1):
            status = "✓ VALID" if result.valid else "✗ INVALID"
            match_status = ""
            if result.title_match is not None:
                match_status = " 📋 TITLE MATCH" if result.title_match else " ❌ TITLE MISMATCH"
            
            print(f"\n{i}. {status}{match_status}")
            print(f"   Method: {result.method_name}")
            print(f"   ID: {result.method_id}")
            
            if result.retrieved_title:
                print(f"   Retrieved Title: {result.retrieved_title[:100]}{'...' if len(result.retrieved_title) > 100 else ''}")
            
            if result.error:
                print(f"   ❌ Error: {result.error}")

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
        results, identifier_results = await validate_annotation_file(args.annotation_file, args.threshold)
        print_validation_report(results, identifier_results)
        
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