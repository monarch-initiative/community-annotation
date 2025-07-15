#!/usr/bin/env python3
"""
Simple MCP Server for annotation validation using aurelian's pubmed utilities.

This server focuses on annotation validation while leveraging aurelian's
proven paper fetching capabilities.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
)

from aurelian.utils.pubmed_utils import get_pmid_text
import aiohttp

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the MCP server
server = Server("simple-aurelian-annotation-validator")

# Paper cache to avoid repeated fetches
paper_cache = {}

# URL cache for web resources
url_cache = {}

async def fetch_url_text(url: str) -> Optional[str]:
    """Fetch web page content from URL."""
    if url in url_cache:
        return url_cache[url]
    
    try:
        timeout = ClientTimeout(total=10)  # Set a 10-second timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    url_cache[url] = text
                    logger.info(f"Successfully fetched {url} ({len(text)} characters)")
                    return text
                else:
                    logger.warning(f"HTTP {response.status} for {url}")
                    return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

async def fetch_paper_text(pmid: str) -> Optional[str]:
    """Fetch paper text using aurelian's utilities."""
    if pmid in paper_cache:
        return paper_cache[pmid]
    
    try:
        # Use aurelian's get_pmid_text which handles full text + fallback
        text = await asyncio.to_thread(get_pmid_text, pmid)
        if text:
            paper_cache[pmid] = text
            logger.info(f"Successfully fetched {pmid} ({len(text)} characters)")
            return text
        else:
            logger.warning(f"No text found for {pmid}")
            return None
    except Exception as e:
        logger.error(f"Error fetching {pmid}: {e}")
        return None

def extract_title_from_text(text: str) -> str:
    """Extract title from paper text."""
    lines = text.split('\n')
    for line in lines[:10]:  # Check first 10 lines
        if line.strip() and len(line) > 20 and '.' in line:
            return line.strip()
    return "No title found"

def find_supporting_text_in_paper(supporting_text: str, paper_text: str) -> tuple[bool, float, str]:
    """Find supporting text in paper with context."""
    
    # Normalize text for comparison
    supporting_lower = supporting_text.lower()
    paper_lower = paper_text.lower()
    
    # Try exact match first
    if supporting_lower in paper_lower:
        # Find the context around the match
        match_pos = paper_lower.find(supporting_lower)
        start = max(0, match_pos - 100)
        end = min(len(paper_text), match_pos + len(supporting_text) + 100)
        context = paper_text[start:end].strip()
        return True, 1.0, context
    
    # Try partial word matching
    supporting_words = re.findall(r'\b\w+\b', supporting_lower)
    if len(supporting_words) < 2:
        return False, 0.0, ""
    
    # Count how many words match
    paper_words = set(re.findall(r'\b\w+\b', paper_lower))
    matched_words = [word for word in supporting_words if word in paper_words]
    
    if len(matched_words) == 0:
        return False, 0.0, ""
    
    confidence = len(matched_words) / len(supporting_words)
    
    # If confidence is high enough, find best matching sentence
    if confidence > 0.7:
        sentences = re.split(r'[.!?]+', paper_text)
        best_sentence = ""
        best_sentence_score = 0
        
        for sentence in sentences:
            sentence_lower = sentence.lower()
            sentence_words = set(re.findall(r'\b\w+\b', sentence_lower))
            sentence_matches = [word for word in supporting_words if word in sentence_words]
            sentence_score = len(sentence_matches) / len(supporting_words) if supporting_words else 0
            
            if sentence_score > best_sentence_score:
                best_sentence_score = sentence_score
                best_sentence = sentence.strip()
        
        return confidence > 0.8, confidence, best_sentence
    
    return False, confidence, ""

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available validation tools."""
    return [
        Tool(
            name="fetch_paper",
            description="Fetch paper content using aurelian's pubmed utilities",
            inputSchema={
                "type": "object",
                "properties": {
                    "pmid": {
                        "type": "string",
                        "description": "PMID reference (e.g., 'PMID:12345678')"
                    }
                },
                "required": ["pmid"]
            }
        ),
        Tool(
            name="validate_supporting_text",
            description="Validate supporting text against paper content",
            inputSchema={
                "type": "object",
                "properties": {
                    "supporting_text": {
                        "type": "string",
                        "description": "The supporting text to validate"
                    },
                    "reference": {
                        "type": "string", 
                        "description": "PMID reference (e.g., 'PMID:12345678') or URL"
                    }
                },
                "required": ["supporting_text", "reference"]
            }
        ),
        Tool(
            name="validate_hpo_annotation",
            description="Validate a complete HPO annotation with multiple supporting texts",
            inputSchema={
                "type": "object",
                "properties": {
                    "hpo_id": {
                        "type": "string",
                        "description": "HPO term ID (e.g., 'HP:0002321')"
                    },
                    "hpo_name": {
                        "type": "string",
                        "description": "HPO term name"
                    },
                    "supporting_texts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "reference": {"type": "string"}
                            },
                            "required": ["text", "reference"]
                        },
                        "description": "List of supporting text entries"
                    }
                },
                "required": ["hpo_id", "hpo_name", "supporting_texts"]
            }
        ),
        Tool(
            name="validate_annotation_file",
            description="Validate an entire annotation file",
            inputSchema={
                "type": "object",
                "properties": {
                    "annotation_data": {
                        "type": "object",
                        "description": "The annotation YAML data as a dictionary"
                    }
                },
                "required": ["annotation_data"]
            }
        ),
        Tool(
            name="cache_papers_from_annotation",
            description="Pre-fetch and cache all papers referenced in an annotation file",
            inputSchema={
                "type": "object",
                "properties": {
                    "annotation_data": {
                        "type": "object",
                        "description": "The annotation YAML data as a dictionary"
                    }
                },
                "required": ["annotation_data"]
            }
        ),
        Tool(
            name="validate_relevant_publications",
            description="Validate the relevant_publications section of an annotation file",
            inputSchema={
                "type": "object",
                "properties": {
                    "publications": {
                        "type": "array",
                        "description": "List of relevant publication entries",
                        "items": {
                            "type": "object",
                            "properties": {
                                "reference": {"type": "string"},
                                "title": {"type": "string"},
                                "supporting_text": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "text": {"type": "string"},
                                            "reference": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "required": ["publications"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    
    if name == "fetch_paper":
        pmid = arguments["pmid"]
        
        paper_text = await fetch_paper_text(pmid)
        
        if paper_text:
            title = extract_title_from_text(paper_text)
            response = f"""Paper Fetched: {pmid}

Title: {title}

Content Length: {len(paper_text)} characters
Has Full Text: {'Yes' if len(paper_text) > 5000 else 'Likely abstract only'}

Preview:
{paper_text[:800]}{'...' if len(paper_text) > 800 else ''}"""
        else:
            response = f"✗ Could not fetch paper: {pmid}"
        
        return [TextContent(type="text", text=response)]
    
    elif name == "validate_supporting_text":
        supporting_text = arguments["supporting_text"]
        reference = arguments["reference"]
        
        # Determine if this is a PMID or URL and fetch accordingly
        if reference.startswith("PMID:"):
            content = await fetch_paper_text(reference)
            content_type = "paper"
        elif reference.startswith("http"):
            content = await fetch_url_text(reference)
            content_type = "webpage"
        else:
            response = f"✗ Unsupported reference type: {reference}"
            return [TextContent(type="text", text=response)]
        
        if not content:
            response = f"✗ Could not fetch {content_type}: {reference}"
            return [TextContent(type="text", text=response)]
        
        # Find supporting text
        found, confidence, context = find_supporting_text_in_paper(supporting_text, content)
        
        # Format result
        status = "✓ FOUND" if found else "✗ NOT FOUND"
        confidence_icon = "🟢" if confidence > 0.8 else "🟡" if confidence > 0.5 else "🔴"
        
        if content_type == "paper":
            title = extract_title_from_text(content)
        else:
            # For URLs, extract title from HTML or use reference
            title = reference
        
        response = f"""Validation Result: {status} {confidence_icon}

Supporting Text: {supporting_text}
Reference: {reference}
{content_type.title()}: {title[:80]}{'...' if len(title) > 80 else ''}

Confidence Score: {confidence:.3f}"""
        
        if context:
            response += f"\n\nMatching Context:\n{context}"
        
        return [TextContent(type="text", text=response)]
    
    elif name == "validate_hpo_annotation":
        hpo_id = arguments["hpo_id"]
        hpo_name = arguments["hpo_name"]
        supporting_texts = arguments["supporting_texts"]
        
        results = []
        paper_ids = set()
        
        for support_entry in supporting_texts:
            text = support_entry.get("text", "")
            reference = support_entry.get("reference", "")
            
            if not text or not reference or not reference.startswith("PMID:"):
                continue
                
            paper_ids.add(reference)
            
            # Fetch paper
            paper_text = await fetch_paper_text(reference)
            if not paper_text:
                results.append({
                    "text": text[:50] + "...",
                    "reference": reference,
                    "found": False,
                    "confidence": 0.0,
                    "error": "Could not fetch paper"
                })
                continue
            
            # Validate
            found, confidence, context = find_supporting_text_in_paper(text, paper_text)
            results.append({
                "text": text[:50] + "..." if len(text) > 50 else text,
                "reference": reference,
                "found": found,
                "confidence": confidence,
                "context": context[:100] + "..." if len(context) > 100 else context
            })
        
        # Calculate summary
        total = len(results)
        found_count = sum(1 for r in results if r["found"])
        avg_confidence = sum(r["confidence"] for r in results) / total if total > 0 else 0
        
        response = f"""HPO Annotation Validation: {hpo_id} ({hpo_name})

📊 Summary:
- Total supporting texts: {total}
- Found in papers: {found_count}/{total} ({found_count/total*100:.1f}%)
- Average confidence: {avg_confidence:.3f}
- Papers used: {len(paper_ids)}

📋 Results:"""
        
        for i, result in enumerate(results, 1):
            status = "✓" if result["found"] else "✗"
            conf_icon = "🟢" if result["confidence"] > 0.8 else "🟡" if result["confidence"] > 0.5 else "🔴"
            response += f"\n{i}. {status} {conf_icon} {result['reference']}"
            response += f"\n   Text: {result['text']}"
            response += f"\n   Confidence: {result['confidence']:.3f}"
            if result.get("context"):
                response += f"\n   Context: {result['context']}"
            if result.get("error"):
                response += f"\n   Error: {result['error']}"
            response += "\n"
        
        return [TextContent(type="text", text=response)]
    
    elif name == "validate_annotation_file":
        annotation_data = arguments["annotation_data"]
        
        disease_name = annotation_data.get("disease_name", "")
        disease_id = annotation_data.get("disease_id", "")
        
        all_results = []
        section_summaries = {}
        
        # Process all sections
        sections = ['phenotypic_features', 'inheritance', 'clinical_course', 'relevant_publications']
        
        for section_name in sections:
            if section_name not in annotation_data:
                continue
            
            section = annotation_data[section_name]
            section_results = []
            
            if section_name == "relevant_publications":
                # Handle relevant_publications section differently
                for pub in section:
                    reference = pub.get("reference", "")
                    title = pub.get("title", "")
                    supporting_texts = pub.get("supporting_text", [])
                    
                    for support_entry in supporting_texts:
                        text = support_entry.get("text", "")
                        ref = support_entry.get("reference", "")
                        
                        if not text or not ref:
                            continue
                        
                        # Determine content type and fetch
                        if ref.startswith("PMID:"):
                            content = await fetch_paper_text(ref)
                        elif ref.startswith("http"):
                            content = await fetch_url_text(ref)
                        else:
                            continue
                        
                        if content:
                            found, confidence, context = find_supporting_text_in_paper(text, content)
                            result = {
                                "hpo_id": reference,  # Use main reference as ID
                                "hpo_name": title,    # Use publication title as name
                                "text": text,
                                "reference": ref,
                                "found": found,
                                "confidence": confidence,
                                "section": section_name
                            }
                            section_results.append(result)
                            all_results.append(result)
            else:
                # Handle HPO annotation sections
                for annotation in section:
                    hpo_id = annotation.get("hpo_id", "")
                    hpo_name = annotation.get("hpo_name", "")
                    supporting_texts = annotation.get("supporting_text", [])
                    
                    if not supporting_texts:
                        continue
                    
                    # Validate each supporting text
                    for support_entry in supporting_texts:
                        text = support_entry.get("text", "")
                        reference = support_entry.get("reference", "")
                        
                        if not text or not reference:
                                continue
                        
                    # Determine content type and fetch
                    if reference.startswith("PMID:"):
                        content = await fetch_paper_text(reference)
                    elif reference.startswith("http"):
                        content = await fetch_url_text(reference)
                    else:
                        continue
                        
                        if content:
                            found, confidence, context = find_supporting_text_in_paper(text, content)
                            result = {
                                "hpo_id": hpo_id,
                                "hpo_name": hpo_name,
                                "text": text,
                                "reference": reference,
                                "found": found,
                                "confidence": confidence,
                                "section": section_name
                            }
                            section_results.append(result)
                            all_results.append(result)
            
            # Section summary
            if section_results:
                section_found = sum(1 for r in section_results if r["found"])
                section_total = len(section_results)
                section_summaries[section_name] = {
                    "found": section_found,
                    "total": section_total,
                    "rate": section_found / section_total if section_total > 0 else 0
                }
        
        # Overall summary
        total_annotations = len(all_results)
        total_found = sum(1 for r in all_results if r["found"])
        overall_rate = total_found / total_annotations if total_annotations > 0 else 0
        avg_confidence = sum(r["confidence"] for r in all_results) / total_annotations if total_annotations > 0 else 0
        
        # Unique papers
        unique_papers = set(r["reference"] for r in all_results)
        
        response = f"""Annotation File Validation: {disease_name} ({disease_id})

📊 Overall Results:
- Total annotations: {total_annotations}
- Successfully validated: {total_found}/{total_annotations} ({overall_rate*100:.1f}%)
- Average confidence: {avg_confidence:.3f}
- Unique papers: {len(unique_papers)}

📋 Section Breakdown:"""
        
        for section_name, summary in section_summaries.items():
            response += f"\n- {section_name.replace('_', ' ').title()}: {summary['found']}/{summary['total']} ({summary['rate']*100:.1f}%)"
        
        # Show papers used
        response += f"\n\n📄 Papers Used:\n"
        for paper in sorted(unique_papers):
            response += f"- {paper}\n"
        
        return [TextContent(type="text", text=response)]
    
    elif name == "cache_papers_from_annotation":
        annotation_data = arguments["annotation_data"]
        
        # Extract all unique references (PMIDs and URLs)
        references = set()
        sections = ['phenotypic_features', 'inheritance', 'clinical_course', 'relevant_publications']
        
        for section_name in sections:
            if section_name not in annotation_data:
                continue
            section = annotation_data[section_name]
            
            if section_name == "relevant_publications":
                # Handle relevant_publications section
                for pub in section:
                    supporting_texts = pub.get("supporting_text", [])
                    for support_entry in supporting_texts:
                        ref = support_entry.get("reference", "")
                        if ref.startswith("PMID:") or ref.startswith("http"):
                            references.add(ref)
            else:
                # Handle HPO annotation sections
                for annotation in section:
                    supporting_texts = annotation.get("supporting_text", [])
                    for support_entry in supporting_texts:
                        ref = support_entry.get("reference", "")
                        if ref.startswith("PMID:") or ref.startswith("http"):
                            references.add(ref)
        
        # Cache all references
        success_count = 0
        results = []
        
        for ref in sorted(references):
            if ref.startswith("PMID:"):
                content = await fetch_paper_text(ref)
                if content:
                    success_count += 1
                    title = extract_title_from_text(content)[:60]
                    results.append(f"✓ {ref}: {title}...")
                else:
                    results.append(f"✗ {ref}: Failed to fetch")
            elif ref.startswith("http"):
                content = await fetch_url_text(ref)
                if content:
                    success_count += 1
                    results.append(f"✓ {ref}: URL cached ({len(content)} chars)")
                else:
                    results.append(f"✗ {ref}: Failed to fetch")
        
        response = f"""Caching References from Annotation

Found {len(references)} unique references
Successfully cached: {success_count}/{len(references)}

Results:
""" + "\n".join(results)
        
        return [TextContent(type="text", text=response)]
    
    elif name == "validate_relevant_publications":
        publications = arguments["publications"]
        
        results = []
        all_validation_results = []
        
        for pub in publications:
            reference = pub.get("reference", "")
            title = pub.get("title", "")
            supporting_texts = pub.get("supporting_text", [])
            
            pub_results = []
            
            for support_entry in supporting_texts:
                text = support_entry.get("text", "")
                ref = support_entry.get("reference", "")
                
                if not text or not ref:
                    continue
                
                # Determine content type and fetch
                if ref.startswith("PMID:"):
                    content = await fetch_paper_text(ref)
                    content_type = "paper"
                elif ref.startswith("http"):
                    content = await fetch_url_text(ref)
                    content_type = "webpage"
                else:
                    pub_results.append({
                        "text": text[:50] + "..." if len(text) > 50 else text,
                        "reference": ref,
                        "found": False,
                        "confidence": 0.0,
                        "error": f"Unsupported reference type: {ref}"
                    })
                    continue
                
                if not content:
                    pub_results.append({
                        "text": text[:50] + "..." if len(text) > 50 else text,
                        "reference": ref,
                        "found": False,
                        "confidence": 0.0,
                        "error": f"Could not fetch {content_type}"
                    })
                    continue
                
                # Validate
                found, confidence, context = find_supporting_text_in_paper(text, content)
                result = {
                    "text": text[:50] + "..." if len(text) > 50 else text,
                    "reference": ref,
                    "found": found,
                    "confidence": confidence,
                    "context": context[:100] + "..." if len(context) > 100 else context,
                    "content_type": content_type
                }
                pub_results.append(result)
                all_validation_results.append(result)
            
            # Publication summary
            pub_found = sum(1 for r in pub_results if r["found"])
            pub_total = len(pub_results)
            pub_avg_conf = sum(r["confidence"] for r in pub_results) / pub_total if pub_total > 0 else 0
            
            results.append({
                "reference": reference,
                "title": title[:60] + "..." if len(title) > 60 else title,
                "found": pub_found,
                "total": pub_total,
                "avg_confidence": pub_avg_conf,
                "details": pub_results
            })
        
        # Overall summary
        total_validations = len(all_validation_results)
        total_found = sum(1 for r in all_validation_results if r["found"])
        overall_avg_conf = sum(r["confidence"] for r in all_validation_results) / total_validations if total_validations > 0 else 0
        high_confidence = sum(1 for r in all_validation_results if r["confidence"] > 0.8)
        
        response = f"""Relevant Publications Validation

📊 Overall Summary:
- Total publications: {len(publications)}
- Total supporting texts: {total_validations}
- Successfully validated: {total_found}/{total_validations} ({total_found/total_validations*100:.1f}%)
- High confidence (>0.8): {high_confidence}/{total_validations} ({high_confidence/total_validations*100:.1f}%)
- Average confidence: {overall_avg_conf:.3f}

📋 Publication Details:"""
        
        for i, result in enumerate(results, 1):
            response += f"\n\n{i}. {result['reference']}"
            response += f"\n   Title: {result['title']}"
            response += f"\n   Supporting texts: {result['found']}/{result['total']} validated ({result['found']/result['total']*100:.1f}%)"
            response += f"\n   Average confidence: {result['avg_confidence']:.3f}"
            
            for j, detail in enumerate(result['details'], 1):
                status = "✓" if detail["found"] else "✗"
                conf_icon = "🟢" if detail["confidence"] > 0.8 else "🟡" if detail["confidence"] > 0.5 else "🔴"
                response += f"\n     {j}. {status} {conf_icon} {detail['reference']} ({detail['content_type']})"
                response += f"\n        Text: {detail['text']}"
                response += f"\n        Confidence: {detail['confidence']:.3f}"
                if detail.get("context"):
                    response += f"\n        Context: {detail['context']}"
                if detail.get("error"):
                    response += f"\n        Error: {detail['error']}"
        
        return [TextContent(type="text", text=response)]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    """Run the simple aurelian MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="simple-aurelian-annotation-validator",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())