#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: CC-BY-NC-4.0

"""Language detection and parser utilities

This module provides shared language detection and parser creation utilities
used by both CodeRead and CodeWrite servers. It includes functions for
detecting programming languages from file extensions and creating appropriate
tree-sitter parsers.
"""

import os
from pathlib import Path
from typing import Optional, Tuple, List
from tree_sitter import Parser
from dynamic_languages import load_all_languages, EXTENSION_MAP, get_all_extensions

# Load all available languages dynamically
LANGUAGES = load_all_languages()


def detect_language_from_path(file_path: str) -> str:
    """Auto-detect language from file extension
    
    Args:
        file_path: Path to the file to detect language for
        
    Returns:
        The detected language name, or 'unknown' if not supported
        
    Examples:
        >>> detect_language_from_path("main.py")
        "python"
        >>> detect_language_from_path("app.js")
        "javascript"
        >>> detect_language_from_path("unknown.xyz")
        "unknown"
    """
    ext = Path(file_path).suffix.lower()
    return EXTENSION_MAP.get(ext, 'unknown')


def get_language_parser(file_path: str) -> Tuple[Optional[Parser], Optional[str]]:
    """Get appropriate parser based on file extension
    
    Args:
        file_path: Path to the file to get parser for
        
    Returns:
        Tuple of (parser, language_name). Both are None if language not supported.
        
    Examples:
        >>> parser, lang = get_language_parser("main.py")
        >>> print(lang)
        "python"
        >>> print(type(parser))
        <class 'tree_sitter.Parser'>
    """
    # Try tree-sitter-languages first (same as readCode)
    try:
        from tree_sitter_languages import get_parser as ts_get_parser
        lang = detect_language_from_path(file_path)
        if lang != 'unknown':
            try:
                parser = ts_get_parser(lang)
                return parser, lang
            except Exception:
                pass
    except ImportError:
        pass
    
    # Fallback to dynamic_languages
    ext = Path(file_path).suffix.lower()
    lang = EXTENSION_MAP.get(ext)
    if lang and lang in LANGUAGES:
        try:
            parser = Parser(LANGUAGES[lang])
            return parser, lang
        except Exception:
            pass
    
    return None, None


def get_language_parser_by_name(language: str) -> Tuple[Optional[Parser], Optional[str]]:
    """Get parser by language name
    
    Args:
        language: The language name (e.g., 'python', 'javascript')
        
    Returns:
        Tuple of (parser, language_name). Both are None if language not supported.
        
    Examples:
        >>> parser, lang = get_language_parser_by_name("python")
        >>> print(lang)
        "python"
    """
    if language in LANGUAGES:
        parser = Parser(LANGUAGES[language])
        return parser, language
    
    return None, None


def is_supported_language(language: str) -> bool:
    """Check if a language is supported
    
    Args:
        language: The language name to check
        
    Returns:
        True if the language is supported, False otherwise
        
    Examples:
        >>> is_supported_language("python")
        True
        >>> is_supported_language("unknown")
        False
    """
    return language in LANGUAGES


def is_supported_extension(extension: str) -> bool:
    """Check if a file extension is supported
    
    Args:
        extension: The file extension (with or without dot)
        
    Returns:
        True if the extension is supported, False otherwise
        
    Examples:
        >>> is_supported_extension(".py")
        True
        >>> is_supported_extension("py")
        True
        >>> is_supported_extension(".xyz")
        False
    """
    # Normalize extension to include dot
    if not extension.startswith('.'):
        extension = '.' + extension
    
    return extension.lower() in EXTENSION_MAP


def get_code_files(dir_path: str) -> List[str]:
    """Get all code files in directory, filtering out hidden dirs and node_modules
    
    Args:
        dir_path: Directory path to search for code files
        
    Returns:
        List of file paths for supported code files
        
    Examples:
        >>> files = get_code_files("./src")
        >>> print(len(files))
        15
    """
    code_extensions = get_all_extensions()
    files = []
    
    for root, dirs, filenames in os.walk(dir_path):
        # Filter out hidden directories and node_modules
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']
        
        for filename in filenames:
            if Path(filename).suffix.lower() in code_extensions:
                files.append(os.path.join(root, filename))
    
    return sorted(files)


def get_supported_extensions() -> List[str]:
    """Get list of all supported file extensions
    
    Returns:
        List of supported file extensions (with dots)
        
    Examples:
        >>> extensions = get_supported_extensions()
        >>> print(".py" in extensions)
        True
    """
    return list(EXTENSION_MAP.keys())


def get_supported_languages() -> List[str]:
    """Get list of all supported languages
    
    Returns:
        List of supported language names
        
    Examples:
        >>> languages = get_supported_languages()
        >>> print("python" in languages)
        True
    """
    return list(LANGUAGES.keys())


def get_language_for_extension(extension: str) -> Optional[str]:
    """Get language name for a file extension
    
    Args:
        extension: The file extension (with or without dot)
        
    Returns:
        The language name, or None if not supported
        
    Examples:
        >>> get_language_for_extension(".py")
        "python"
        >>> get_language_for_extension("js")
        "javascript"
    """
    # Normalize extension to include dot
    if not extension.startswith('.'):
        extension = '.' + extension
    
    return EXTENSION_MAP.get(extension.lower())


def get_extensions_for_language(language: str) -> List[str]:
    """Get all file extensions for a language
    
    Args:
        language: The language name
        
    Returns:
        List of file extensions (with dots) for the language
        
    Examples:
        >>> get_extensions_for_language("python")
        [".py", ".pyi"]
    """
    extensions = []
    for ext, lang in EXTENSION_MAP.items():
        if lang == language:
            extensions.append(ext)
    return extensions


def validate_language_request(requested_language: str, file_path: str) -> Tuple[str, str]:
    """Validate and determine the language to use for a request
    
    Args:
        requested_language: The language requested by user ("auto" or specific language)
        file_path: Path to the file being processed
        
    Returns:
        Tuple of (detected_language, detection_method)
        
    Examples:
        >>> validate_language_request("auto", "main.py")
        ("python", "auto_detected")
        >>> validate_language_request("javascript", "main.py")
        ("javascript", "user_specified")
    """
    if requested_language == "auto":
        detected = detect_language_from_path(file_path)
        if detected == "unknown":
            # Fallback to python for unknown extensions
            return "python", "auto_detected_fallback"
        return detected, "auto_detected"
    else:
        if is_supported_language(requested_language):
            return requested_language, "user_specified"
        else:
            # Fallback to auto-detection if user specified unsupported language
            detected = detect_language_from_path(file_path)
            if detected == "unknown":
                return "python", "user_unsupported_fallback"
            return detected, "user_unsupported_fallback"
