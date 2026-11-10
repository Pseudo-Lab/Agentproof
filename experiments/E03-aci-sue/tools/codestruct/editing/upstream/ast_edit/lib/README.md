# Code-readwrite-mcp Library

This directory contains the bundled Code-readwrite-mcp library files needed by the writeCode tool.

## Files

- `ast_utils.py` - AST parsing utilities including parse_scoped_selector
- `language_detection.py` - Language detection and parser management
- `fuzzy_search.py` - Fuzzy matching for code symbols
- `file_operations.py` - Safe file read/write operations
- `dynamic_languages.py` - Dynamic language loading
- `install_languages.py` - Language installation utilities

## Why Bundled?

These files are bundled directly with the tool to ensure:
1. No external dependencies on user-specific paths
2. Works in Docker containers without mounting
3. Portable across different environments
4. No need for git clone during runtime

## Source

Original source: Code-readwrite-mcp project
