"""
Core validation logic for annotations.
"""

import re
from typing import List, Tuple, Optional
from dataclasses import dataclass

from .fetcher import PMIDFetcher


@dataclass
class ValidationResult:
    """Result of validating a supporting text entry."""
    found: bool
    similarity_score: float = 0.0
    disease_relevant: bool = False
    disease_relevance_score: float = 0.0
    error: Optional[str] = None
    publication_title: Optional[str] = None
    publication_abstract: Optional[str] = None


class AnnotationValidator:
    """Validate annotations against publications."""
    
    def __init__(self, fetcher: Optional[PMIDFetcher] = None):
        self.fetcher = fetcher or PMIDFetcher()
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        text = re.sub(r'\s+', ' ', text.strip())
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        return text.lower()
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple similarity score between two texts."""
        words1 = set(self.normalize_text(text1).split())
        words2 = set(self.normalize_text(text2).split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    def check_disease_relevance(self, content: str, disease_keywords: List[str]) -> Tuple[bool, float]:
        """Check if publication content is relevant to the disease."""
        if not disease_keywords:
            return True, 1.0
        
        normalized_content = self.normalize_text(content)
        
        matches = 0
        for keyword in disease_keywords:
            if self.normalize_text(keyword) in normalized_content:
                matches += 1
        
        relevance_score = matches / len(disease_keywords) if disease_keywords else 0.0
        is_relevant = relevance_score >= 0.2
        
        return is_relevant, relevance_score
    
    def find_text_in_content(self, supporting_text: str, content: str, threshold: float = 0.7) -> Tuple[bool, float]:
        """Find supporting text in publication content."""
        normalized_supporting = self.normalize_text(supporting_text)
        normalized_content = self.normalize_text(content)
        
        # Exact match
        if normalized_supporting in normalized_content:
            return True, 1.0
        
        # Check for high similarity matches in sentences
        content_sentences = re.split(r'[.!?]+', normalized_content)
        best_similarity = 0.0
        
        for sentence in content_sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue
                
            similarity = self.calculate_similarity(normalized_supporting, sentence)
            best_similarity = max(best_similarity, similarity)
            
            if similarity >= threshold:
                return True, similarity
        
        return False, best_similarity
    
    async def validate_annotation(
        self, 
        supporting_text: str, 
        pmid: str, 
        disease_keywords: List[str] = None
    ) -> ValidationResult:
        """Validate a single annotation."""
        if not pmid.startswith("PMID:"):
            return ValidationResult(
                found=False, 
                error="Only PMID references supported"
            )
        
        pub_data = await self.fetcher.fetch_abstract(pmid)
        if pub_data is None:
            return ValidationResult(
                found=False, 
                error="Could not fetch publication content"
            )
        
        # Check disease relevance
        disease_relevant = True
        disease_relevance_score = 1.0
        if disease_keywords:
            disease_relevant, disease_relevance_score = self.check_disease_relevance(
                pub_data["full_text"], disease_keywords
            )
        
        # Check text match
        found, similarity = self.find_text_in_content(supporting_text, pub_data["full_text"])
        
        return ValidationResult(
            found=found,
            similarity_score=similarity,
            disease_relevant=disease_relevant,
            disease_relevance_score=disease_relevance_score,
            publication_title=pub_data.get("title"),
            publication_abstract=pub_data.get("abstract")
        )