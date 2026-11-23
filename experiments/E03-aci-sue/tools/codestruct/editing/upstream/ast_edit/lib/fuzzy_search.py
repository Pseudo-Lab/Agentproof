#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: CC-BY-NC-4.0

"""Fuzzy search utilities for code analysis and manipulation

This module provides shared fuzzy search utilities used by both CodeRead and
CodeWrite servers. It includes functions for fuzzy matching, scoped search,
and fallback mechanisms when rapidfuzz is not available.
"""

from typing import List, Dict, Optional, Tuple, Set
from ast_utils import parse_scoped_selector

try:
    from rapidfuzz import fuzz, process
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False


def match_abbreviation(abbr: str, target: str) -> float:
    """
    Check if abbr is an abbreviation of target
    
    Args:
        abbr: The abbreviation to match
        target: The target string to match against
        
    Returns:
        Match score (0-100), higher is better
        
    Examples:
        >>> match_abbreviation("calc", "Calculator")
        95.0  # Prefix match
        >>> match_abbreviation("UM", "UserManager")
        90.0  # Capital letters match
        >>> match_abbreviation("usrmgr", "UserManager")
        85.0  # Subsequence match
    """
    abbr = abbr.lower()
    target_lower = target.lower()
    
    # 1. Prefix matching (high confidence)
    if target_lower.startswith(abbr):
        return 95.0
    
    # 2. Capital letters matching (for CamelCase)
    capitals = ''.join(c for c in target if c.isupper()).lower()
    if capitals and abbr in capitals:
        return 90.0
    
    # 3. Subsequence matching (abbr chars appear in order in target)
    # This handles cases like "usermgr" matching "UserManager"
    abbr_idx = 0
    for char in target_lower:
        if abbr_idx < len(abbr) and char == abbr[abbr_idx]:
            abbr_idx += 1
    if abbr_idx == len(abbr):  # All chars matched
        # Score based on how much of target was used
        ratio = len(abbr) / len(target_lower)
        if ratio > 0.5:  # More than half the characters
            return 88.0
        else:
            return 85.0
    
    # 4. Consonant skeleton matching (remove vowels)
    consonants_target = ''.join(c for c in target_lower if c not in 'aeiou')
    consonants_abbr = ''.join(c for c in abbr if c not in 'aeiou')
    if consonants_target and consonants_abbr in consonants_target:
        return 82.0
    
    # 5. Token matching (for snake_case/kebab-case)
    tokens = target_lower.replace('_', '').replace('-', '')
    if abbr in tokens:
        return 80.0
    
    return 0.0


def fuzzy_search_signatures(signatures: List[Dict], selector: str, threshold: float = 70.0) -> List[Dict]:
    """Perform fuzzy search on signatures with scoped search support
    
    Args:
        signatures: List of signature dictionaries to search
        selector: The selector string to search for (supports "Class.method" syntax)
        threshold: Minimum fuzzy match score (0-100)
        
    Returns:
        List of matching signature dictionaries
        
    Examples:
        >>> signatures = [{"name": "add", "parentClass": "Calculator"}, ...]
        >>> fuzzy_search_signatures(signatures, "Calculator.add")
        [{"name": "add", "parentClass": "Calculator", ...}]
        >>> fuzzy_search_signatures(signatures, "calcuator")  # Typo tolerance
        [{"name": "add", "parentClass": "Calculator", ...}]
    """
    # Parse scoped selector
    class_name, method_name = parse_scoped_selector(selector)
    
    # If scoped search, filter by class first
    if class_name:
        # Find signatures that belong to the specified class
        class_signatures = [s for s in signatures if s.get('parentClass') == class_name]
        if not class_signatures:
            # Try fuzzy matching on class names too
            if FUZZY_AVAILABLE:
                class_names = list(set(s.get('parentClass') for s in signatures if s.get('parentClass')))
                class_matches = process.extract(class_name, class_names, scorer=fuzz.WRatio, limit=3)
                for match_class, score, _ in class_matches:
                    if score >= threshold:
                        class_signatures.extend([s for s in signatures if s.get('parentClass') == match_class])
        
        # Now search for method within the class
        if class_signatures:
            return fuzzy_search_signatures_basic(class_signatures, method_name, threshold)
        else:
            return []  # No matching class found
    else:
        # Regular search without scoping
        return fuzzy_search_signatures_basic(signatures, selector, threshold)


def fuzzy_search_signatures_basic(signatures: List[Dict], selector: str, threshold: float = 70.0) -> List[Dict]:
    """Basic fuzzy search on signatures without scoping
    
    Args:
        signatures: List of signature dictionaries to search
        selector: The selector string to search for
        threshold: Minimum fuzzy match score (0-100)
        
    Returns:
        List of matching signature dictionaries
    """
    if not FUZZY_AVAILABLE:
        # Fallback to substring search
        return [s for s in signatures if selector.lower() in s['name'].lower()]
    
    # Step 1: Try abbreviation matching first (fast and accurate)
    abbr_matches = []
    for sig in signatures:
        abbr_score = match_abbreviation(selector, sig['name'])
        if abbr_score >= 80.0:  # High confidence abbreviation match
            abbr_matches.append((sig, abbr_score))
    
    if abbr_matches:
        # Sort by score and return
        abbr_matches.sort(key=lambda x: x[1], reverse=True)
        return [sig for sig, _ in abbr_matches]
    
    # Step 2: Fall back to fuzzy matching
    # Extract names for fuzzy matching
    names = [s['name'] for s in signatures]
    
    # Use primary scorer with higher threshold for better precision
    fuzzy_matches = process.extract(selector, names, scorer=fuzz.WRatio, limit=10)
    
    # For very short selectors, also try partial matching with higher threshold
    all_matches = set()
    for match_name, score, _ in fuzzy_matches:
        if score >= threshold:
            all_matches.add(match_name)
    
    # If no matches and selector is short, try partial matching with stricter threshold
    if not all_matches and len(selector) <= 6:
        partial_matches = process.extract(selector, names, scorer=fuzz.partial_ratio, limit=5)
        for match_name, score, _ in partial_matches:
            if score >= 85.0:  # Much higher threshold for partial matching
                all_matches.add(match_name)
    
    # Convert back to signatures
    matches = []
    for match_name in all_matches:
        matching_sigs = [s for s in signatures if s['name'] == match_name]
        matches.extend(matching_sigs)
    
    return matches


def fuzzy_search_nodes(nodes: List, selector: str, get_name_func, threshold: float = 70.0) -> List:
    """Perform fuzzy search on AST nodes
    
    Args:
        nodes: List of AST nodes to search
        selector: The selector string to search for
        get_name_func: Function to extract name from node
        threshold: Minimum fuzzy match score (0-100)
        
    Returns:
        List of matching nodes
    """
    if not FUZZY_AVAILABLE:
        # Fallback to substring search
        return [node for node in nodes if selector.lower() in get_name_func(node).lower()]
    
    # Extract names for fuzzy matching
    match_names = [get_name_func(node) for node in nodes]
    
    # Try primary fuzzy matching with WRatio
    fuzzy_matches = process.extract(selector, match_names, scorer=fuzz.WRatio, limit=10)
    best_matches = []
    
    for match_name, score, _ in fuzzy_matches:
        if score >= threshold:  # Standard threshold
            best_matches.append((match_name, score))
    
    # If no matches and selector is short, try partial matching with higher threshold
    if not best_matches and len(selector) <= 6:
        partial_matches = process.extract(selector, match_names, scorer=fuzz.partial_ratio, limit=5)
        for match_name, score, _ in partial_matches:
            if score >= 85:  # Higher threshold for partial matching
                best_matches.append((match_name, score))
    
    # Convert back to nodes
    matches = []
    for match_name, _ in best_matches:
        for node in nodes:
            if get_name_func(node) == match_name:
                matches.append(node)
                break
    
    return matches


def fuzzy_search_class_names(signatures: List[Dict], class_name: str, threshold: float = 70.0) -> List[str]:
    """Find class names using fuzzy search
    
    Args:
        signatures: List of signature dictionaries
        class_name: The class name to search for
        threshold: Minimum fuzzy match score (0-100)
        
    Returns:
        List of matching class names
    """
    if not FUZZY_AVAILABLE:
        # Fallback to substring search
        class_names = list(set(s.get('parentClass') for s in signatures if s.get('parentClass')))
        return [name for name in class_names if class_name.lower() in name.lower()]
    
    class_names = list(set(s.get('parentClass') for s in signatures if s.get('parentClass')))
    class_matches = process.extract(class_name, class_names, scorer=fuzz.WRatio, limit=3)
    
    matches = []
    for match_class, score, _ in class_matches:
        if score >= threshold:
            matches.append(match_class)
    
    return matches


def get_search_type_description(has_scoped: bool = False) -> str:
    """Get description of search type based on availability and scoping
    
    Args:
        has_scoped: Whether scoped search is being used
        
    Returns:
        Description string for the search type
    """
    if not FUZZY_AVAILABLE:
        return "scoped substring" if has_scoped else "substring"
    else:
        return "scoped fuzzy" if has_scoped else "fuzzy"


def is_fuzzy_available() -> bool:
    """Check if fuzzy search is available
    
    Returns:
        True if rapidfuzz is available, False otherwise
    """
    return FUZZY_AVAILABLE


def get_fallback_search_results(signatures: List[Dict], selector: str) -> List[Dict]:
    """Get fallback search results when fuzzy search fails
    
    Args:
        signatures: List of signature dictionaries
        selector: The selector string to search for
        
    Returns:
        List of signature dictionaries that contain the selector as substring
    """
    return [s for s in signatures if selector.lower() in s['name'].lower()]


def get_enhanced_fuzzy_matches(selector: str, candidates: List[str], threshold: float = 70.0) -> List[Tuple[str, float]]:
    """Get enhanced fuzzy matches with multiple scoring methods
    
    Args:
        selector: The string to search for
        candidates: List of candidate strings to match against
        threshold: Minimum match score (0-100)
        
    Returns:
        List of tuples (match_string, score) sorted by score
    """
    if not FUZZY_AVAILABLE:
        # Fallback to substring search
        matches = []
        for candidate in candidates:
            if selector.lower() in candidate.lower():
                # Calculate simple score based on length ratio
                score = (len(selector) / len(candidate)) * 100
                matches.append((candidate, score))
        return sorted(matches, key=lambda x: x[1], reverse=True)
    
    all_matches = set()
    
    # Primary fuzzy matching with WRatio
    fuzzy_matches = process.extract(selector, candidates, scorer=fuzz.WRatio, limit=10)
    for match_name, score, _ in fuzzy_matches:
        if score >= threshold:
            all_matches.add((match_name, score))
    
    # For short selectors, also try partial matching
    if len(selector) <= 6:
        partial_matches = process.extract(selector, candidates, scorer=fuzz.partial_ratio, limit=5)
        for match_name, score, _ in partial_matches:
            if score >= 85.0:  # Higher threshold for partial matching
                all_matches.add((match_name, score))
    
    # Sort by score (highest first)
    return sorted(list(all_matches), key=lambda x: x[1], reverse=True)


def validate_fuzzy_threshold(threshold: float) -> float:
    """Validate and normalize fuzzy search threshold
    
    Args:
        threshold: The threshold value to validate
        
    Returns:
        Normalized threshold value (0-100)
    """
    if threshold < 0:
        return 0.0
    elif threshold > 100:
        return 100.0
    else:
        return float(threshold)
