#!/usr/bin/env python3
"""
MCP Server for validating disease annotations against source publications.

This MCP server provides tools for validating supporting text in disease annotations
against their referenced publications in real-time during curation.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
)

from .validator import AnnotationValidator

# Global validator instance
validator = AnnotationValidator()

# Create the MCP server
server = Server("annotation-validator")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available validation tools."""
    return [
        Tool(
            name="validate_supporting_text",
            description="Validate that supporting text appears in the referenced publication",
            inputSchema={
                "type": "object",
                "properties": {
                    "supporting_text": {
                        "type": "string",
                        "description": "The supporting text to validate"
                    },
                    "pmid": {
                        "type": "string", 
                        "description": "PMID reference (e.g., 'PMID:12345678')"
                    },
                    "disease_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keywords to check disease relevance (optional)",
                        "default": []
                    }
                },
                "required": ["supporting_text", "pmid"]
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
                                "reference": {"type": "string"},
                                "page_section": {"type": "string"}
                            },
                            "required": ["text", "reference"]
                        },
                        "description": "List of supporting text entries"
                    },
                    "disease_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keywords to check disease relevance",
                        "default": []
                    }
                },
                "required": ["hpo_id", "hpo_name", "supporting_texts"]
            }
        ),
        Tool(
            name="fetch_publication_info",
            description="Fetch title and abstract for a PMID",
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
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    
    if name == "validate_supporting_text":
        supporting_text = arguments["supporting_text"]
        pmid = arguments["pmid"]
        disease_keywords = arguments.get("disease_keywords", [])
        
        result = await validator.validate_annotation(supporting_text, pmid, disease_keywords)
        
        # Format result as readable text
        status = "✓ FOUND" if result.found else "✗ NOT FOUND"
        relevance = "🎯 RELEVANT" if result.disease_relevant else "❌ IRRELEVANT"
        
        response = f"""Validation Result: {status} | {relevance}

Supporting Text: {supporting_text[:100]}{'...' if len(supporting_text) > 100 else ''}
Reference: {pmid}
Similarity Score: {result.similarity_score:.2f}
Disease Relevance Score: {result.disease_relevance_score:.2f}

Publication Title: {result.publication_title or 'Not available'}

Publication Abstract: {result.publication_abstract[:300] if result.publication_abstract else 'Not available'}{'...' if result.publication_abstract and len(result.publication_abstract) > 300 else ''}

{f'Error: {result.error}' if result.error else ''}"""
        
        return [TextContent(type="text", text=response)]
    
    elif name == "validate_hpo_annotation":
        hpo_id = arguments["hpo_id"]
        hpo_name = arguments["hpo_name"]
        supporting_texts = arguments["supporting_texts"]
        disease_keywords = arguments.get("disease_keywords", [])
        
        results = []
        for entry in supporting_texts:
            result = await validator.validate_annotation(
                entry["text"], 
                entry["reference"], 
                disease_keywords
            )
            results.append({
                "text": entry["text"][:50] + "..." if len(entry["text"]) > 50 else entry["text"],
                "reference": entry["reference"],
                "found": result.found,
                "similarity": result.similarity_score,
                "disease_relevant": result.disease_relevant,
                "error": result.error
            })
        
        total = len(results)
        found = sum(1 for r in results if r["found"])
        relevant = sum(1 for r in results if r["disease_relevant"])
        
        response = f"""HPO Annotation Validation: {hpo_id} ({hpo_name})

Summary:
- Total supporting texts: {total}
- Found in publications: {found} ({found/total*100:.1f}%)
- Disease-relevant publications: {relevant} ({relevant/total*100:.1f}%)

Details:
"""
        
        for i, result in enumerate(results, 1):
            status = "✓" if result["found"] else "✗"
            relevance = "🎯" if result["disease_relevant"] else "❌"
            response += f"\n{i}. {status} {relevance} {result['reference']}"
            response += f"\n   Text: {result['text']}"
            response += f"\n   Similarity: {result['similarity']:.2f}"
            if result["error"]:
                response += f"\n   Error: {result['error']}"
            response += "\n"
        
        return [TextContent(type="text", text=response)]
    
    elif name == "fetch_publication_info":
        pmid = arguments["pmid"]
        
        pub_data = await validator.fetcher.fetch_abstract(pmid)
        if pub_data is None:
            return [TextContent(type="text", text=f"Could not fetch publication data for {pmid}")]
        
        response = f"""Publication Information: {pmid}

Title: {pub_data.get('title', 'Not available')}

Abstract: {pub_data.get('abstract', 'Not available')}"""
        
        return [TextContent(type="text", text=response)]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    # Run the server using stdin/stdout streams
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="annotation-validator",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())