"""
Annotation Validator - Tools for validating disease annotations against source publications.
"""

__version__ = "0.1.0"

from .validator import AnnotationValidator, ValidationResult
from .fetcher import PMIDFetcher

__all__ = ["AnnotationValidator", "ValidationResult", "PMIDFetcher"]