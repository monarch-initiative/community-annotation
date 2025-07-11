"""
Publication fetching utilities.
"""

import asyncio
import json
import logging
import os
import requests
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PMIDFetcher:
    """Fetch publication content from PubMed."""
    
    def __init__(self, delay: float = 0.5, cache_dir: str = "publication-cache"):
        self.delay = delay
        self.cache = {}
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def _get_cache_file(self, pmid: str) -> Path:
        """Get cache file path for a PMID."""
        clean_pmid = pmid.replace("PMID:", "")
        return self.cache_dir / f"PMID_{clean_pmid}_abstract.json"
    
    def _load_from_cache(self, pmid: str) -> Optional[Dict[str, str]]:
        """Load publication data from cache file."""
        cache_file = self._get_cache_file(pmid)
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load cache for {pmid}: {e}")
        return None
    
    def _save_to_cache(self, pmid: str, data: Dict[str, str]) -> None:
        """Save publication data to cache file."""
        cache_file = self._get_cache_file(pmid)
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save cache for {pmid}: {e}")

    async def fetch_abstract(self, pmid: str) -> Optional[Dict[str, str]]:
        """Fetch abstract and title for a PMID."""
        # Check memory cache first
        if pmid in self.cache:
            return self.cache[pmid]
        
        # Check file cache
        cached_data = self._load_from_cache(pmid)
        if cached_data:
            self.cache[pmid] = cached_data
            return cached_data
        
        # Remove PMID: prefix if present
        clean_pmid = pmid.replace("PMID:", "")
        
        try:
            # Use E-utilities to fetch abstract
            base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            params = {
                "db": "pubmed",
                "id": clean_pmid,
                "retmode": "text",
                "rettype": "abstract"
            }
            
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            
            content = response.text.strip()
            if content and not content.startswith("ERROR"):
                # Parse title and abstract from the response
                lines = content.split('\n')
                title = ""
                abstract = ""
                
                for i, line in enumerate(lines):
                    if line.strip() and not line.startswith("1.") and not line.startswith("PMID:"):
                        if not title and "." in line and len(line) > 20:
                            title = line.strip()
                        elif line.strip() and len(line) > 30:
                            abstract += line.strip() + " "
                
                result = {
                    "title": title.strip(),
                    "abstract": abstract.strip(),
                    "full_text": content,
                    "pmid": pmid,
                    "fetched_at": str(asyncio.get_event_loop().time())
                }
                
                # Cache both in memory and file
                self.cache[pmid] = result
                self._save_to_cache(pmid, result)
                
                await asyncio.sleep(self.delay)  # Be nice to NCBI
                return result
            else:
                logger.warning(f"Could not fetch abstract for {pmid}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching {pmid}: {e}")
            return None