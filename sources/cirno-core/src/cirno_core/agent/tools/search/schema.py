"""Function-call contracts for the file search capabilities."""

from typing import Any


def find_parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Search root (default '.'); set path explicitly to search skipped worktrees, builds or tool artifacts",
            },
            "query": {
                "type": "string",
                "description": "Case-insensitive path terms; all must match",
            },
            "glob": {
                "type": "string",
                "description": "Root-relative path glob, e.g. 'src/**/*.{ts,tsx}'; bare '*.py' matches any depth",
            },
            "type": {
                "type": "string",
                "description": "File type, e.g. 'py', 'ts', 'md', or 'json'",
            },
            "include_dirs": {
                "type": "boolean",
                "description": "Include directories (default false)",
            },
            "sort": {
                "type": "string",
                "enum": ["path", "modified"],
                "description": "Sort order (default path)",
            },
            "head_limit": {
                "type": "integer",
                "description": "Maximum paths (default 200; 0 for all)",
                "minimum": 0,
                "maximum": 1000,
            },
            "offset": {
                "type": "integer",
                "description": "Paths to skip before head_limit",
                "minimum": 0,
                "maximum": 100000,
            },
        },
    }


def grep_parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex, or literal text when fixed_strings=true",
                "minLength": 1,
            },
            "path": {
                "type": "string",
                "description": "Search root (default '.'); set path explicitly to search skipped worktrees, builds or tool artifacts",
            },
            "glob": {
                "type": "string",
                "description": "Root-relative path glob, e.g. 'src/**/*.{ts,tsx}'; bare '*.py' matches any depth",
            },
            "type": {
                "type": "string",
                "description": "File type, e.g. 'py', 'ts', 'md', or 'json'",
            },
            "pages": {
                "type": "string",
                "description": "PDF page number or range, e.g. '7' or '101-200' (max 100 pages)",
            },
            "case_insensitive": {
                "type": "boolean",
                "description": "Ignore case (default false)",
            },
            "fixed_strings": {
                "type": "boolean",
                "description": "Treat pattern literally (default false)",
            },
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_with_matches", "count"],
                "description": (
                    "content: matches with context (default); "
                    "files_with_matches: paths; count: matches per file"
                ),
            },
            "context_before": {
                "type": "integer",
                "description": "Context lines before a match (default 5)",
                "minimum": 0,
                "maximum": 20,
            },
            "context_after": {
                "type": "integer",
                "description": "Context lines after a match (default 5)",
                "minimum": 0,
                "maximum": 20,
            },
            "head_limit": {
                "type": "integer",
                "description": "Maximum matches or file entries (default 250; 0 for all)",
                "minimum": 0,
                "maximum": 1000,
            },
            "offset": {
                "type": "integer",
                "description": "Matches or file entries to skip before head_limit",
                "minimum": 0,
                "maximum": 100000,
            },
        },
        "required": ["pattern"],
    }
