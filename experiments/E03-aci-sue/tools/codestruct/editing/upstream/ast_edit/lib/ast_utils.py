#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: CC-BY-NC-4.0

"""AST utilities for code analysis and manipulation

This module provides shared AST (Abstract Syntax Tree) utilities used by both
CodeRead and CodeWrite servers. It includes functions for node analysis,
selector parsing, and language-specific node type checking.
"""

from typing import Optional, Tuple, List, Dict
from tree_sitter import Node

try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False


def parse_scoped_selector(selector: str) -> Tuple[Optional[str], str]:
    """Parse scoped selector like 'Class.method' into (class_name, method_name)
    
    Args:
        selector: The selector string to parse
        
    Returns:
        Tuple of (class_name, method_name). class_name is None if not scoped.
        
    Examples:
        >>> parse_scoped_selector("Calculator.add")
        ("Calculator", "add")
        >>> parse_scoped_selector("add")
        (None, "add")
    """
    if '.' in selector:
        parts = selector.split('.', 1)
        return parts[0].strip(), parts[1].strip()
    return None, selector


def is_class_node(node: Node, language: str) -> bool:
    """Check if node is a class definition
    
    Args:
        node: The AST node to check
        language: The programming language
        
    Returns:
        True if the node represents a class definition
    """
    class_types = {
        'python': ['class_definition'],
        'javascript': ['class_declaration', 'class_expression'],
        'typescript': ['class_declaration', 'class_expression'],
        'java': ['class_declaration'],
        'c': ['struct_specifier'],
        'cpp': ['class_specifier', 'struct_specifier'],
        'c_sharp': ['class_declaration', 'struct_declaration', 'interface_declaration'],
        'go': ['type_declaration'],
        'rust': ['struct_item', 'impl_item', 'trait_item'],
        'ruby': ['class', 'module'],
        'php': ['class_declaration'],
        'swift': ['class_declaration'],
        'kotlin': ['class_declaration'],
        'scala': ['class_declaration', 'trait_declaration']
    }
    return node.type in class_types.get(language, ['class_definition'])


def is_function_node(node: Node, language: str) -> bool:
    """Check if node is a function definition
    
    Args:
        node: The AST node to check
        language: The programming language
        
    Returns:
        True if the node represents a function definition
    """
    function_types = {
        'python': ['function_definition'],
        'javascript': ['function_declaration', 'function_expression', 'method_definition'],
        'typescript': ['function_declaration', 'function_expression', 'method_definition'],
        'java': ['method_declaration', 'constructor_declaration'],
        'c': ['function_definition', 'function_declarator'],
        'cpp': ['function_definition', 'function_declarator'],
        'c_sharp': ['method_declaration', 'constructor_declaration'],
        'go': ['function_declaration', 'method_declaration'],
        'rust': ['function_item', 'impl_item'],
        'ruby': ['method', 'def'],
        'php': ['function_declaration', 'method_declaration'],
        'swift': ['function_declaration'],
        'kotlin': ['function_declaration'],
        'scala': ['function_declaration']
    }
    return node.type in function_types.get(language, ['function_definition'])


def get_node_name(node: Node, code: str) -> Optional[str]:
    """Extract name from AST node
    
    Args:
        node: The AST node to extract name from
        code: The source code string
        
    Returns:
        The name of the node, or None if not found
    """
    # For C/C++ function definitions, look for the function name in the function_declarator
    if node.type == 'function_definition':
        for child in node.children:
            if child.type == 'function_declarator':
                for grandchild in child.children:
                    if grandchild.type == 'identifier':
                        return grandchild.text.decode('utf8')
    
    # For Go type declarations, look for the type name in type_spec
    if node.type == 'type_declaration':
        for child in node.children:
            if child.type == 'type_spec':
                for grandchild in child.children:
                    if grandchild.type == 'type_identifier':
                        return grandchild.text.decode('utf8')
    
    # For Go method declarations, look for the method name
    if node.type == 'method_declaration':
        for child in node.children:
            if child.type == 'field_identifier':
                return child.text.decode('utf8')
    
    # For other nodes, use the standard approach
    name_node = node.child_by_field_name('name')
    if not name_node and node.children:
        for child in node.children:
            if child.type in ['identifier', 'type_identifier', 'field_identifier']:
                name_node = child
                break
    
    if name_node:
        return name_node.text.decode('utf8')
    return None


def get_node_signature(node: Node, code: str) -> str:
    """Get a signature representation of the node
    
    Args:
        node: The AST node to get signature for
        code: The source code string
        
    Returns:
        A string representation of the node signature
    """
    try:
        # For function/method definitions, try to extract parameters
        if node.type in ['function_definition', 'method_declaration', 'function_declaration']:
            # Get the function name
            name = get_node_name(node, code)
            if not name:
                return node.type
            
            # Try to find parameters
            params = []
            for child in node.children:
                if child.type in ['parameter_list', 'formal_parameters']:
                    for param in child.children:
                        if param.type in ['parameter', 'formal_parameter']:
                            param_name = get_node_name(param, code)
                            if param_name:
                                params.append(param_name)
                    break
            
            if params:
                return f"{name}({', '.join(params)})"
            else:
                return f"{name}()"
        
        # For other nodes, return the name or type
        name = get_node_name(node, code)
        return name if name else node.type
        
    except Exception:
        return node.type


def node_matches_selector(node: Node, selector: str, class_name: str, method_name: str, 
                         class_context: str, code: str) -> bool:
    """Check if node matches the selector
    
    Args:
        node: The AST node to check
        selector: The original selector string
        class_name: The parsed class name (None if not scoped)
        method_name: The parsed method name
        class_context: The current class context during traversal
        code: The source code string
        
    Returns:
        True if the node matches the selector
    """
    node_name = get_node_name(node, code)
    
    # Handle scoped selectors
    if class_name:
        if class_context == class_name and node_name:
            # Exact match first
            if node_name == method_name:
                return True
            # Enhanced fuzzy matching for method names
            if FUZZY_AVAILABLE:
                # Partial matching for short method names (≤6 chars)
                if len(method_name) <= 6 and method_name in node_name:
                    return True
                # Improved fuzzy matching with multiple scoring methods
                # Use WRatio for better matching of partial strings
                if fuzz.WRatio(method_name, node_name) >= 70:
                    return True
                # Use partial_ratio for cases where method_name is contained in node_name
                if fuzz.partial_ratio(method_name, node_name) >= 85:
                    return True
        return False
    
    # Handle non-scoped selectors
    if node_name:
        # Exact match first
        if node_name == selector:
            return True
        # Enhanced fuzzy matching
        if FUZZY_AVAILABLE:
            # Partial matching for short selectors (≤6 chars)
            if len(selector) <= 6 and selector in node_name:
                return True
            # Improved fuzzy matching with multiple scoring methods
            # Use WRatio for better matching of partial strings
            if fuzz.WRatio(selector, node_name) >= 70:
                return True
            # Use partial_ratio for cases where selector is contained in node_name
            if fuzz.partial_ratio(selector, node_name) >= 85:
                return True
    
    return False


def get_function_types(language: str) -> List[str]:
    """Get function/method node types for a language
    
    Args:
        language: The programming language
        
    Returns:
        List of node types that represent functions/methods
    """
    function_types = [
        'function_definition', 'method_definition', 'function_declaration',
        'function_item', 'method_declaration', 'constructor_declaration',
        'function', 'method', 'impl_item', 'function_declarator',
        'function_expression', 'def'
    ]
    
    # Language-specific additions
    if language == 'go':
        function_types.extend(['type_declaration'])
    elif language in ['c', 'cpp']:
        function_types.extend(['function_definition'])
    elif language == 'rust':
        function_types.extend(['function_item', 'impl_item'])
    elif language == 'ruby':
        function_types.extend(['method', 'def'])
    
    return function_types


def get_class_types(language: str) -> List[str]:
    """Get class/struct node types for a language
    
    Args:
        language: The programming language
        
    Returns:
        List of node types that represent classes/structs
    """
    class_types = [
        'class_definition', 'class_declaration', 'class_body',
        'struct_specifier', 'class_specifier', 'type_declaration',
        'struct_item', 'impl_item', 'trait_item', 'interface_declaration',
        'struct_declaration', 'class_expression', 'module',
        'class',  # Ruby classes
        'object_declaration',  # Kotlin objects
        'object_definition'  # Scala objects
    ]
    
    return class_types


def extract_available_selectors(tree: Node, code: str, language: str) -> Dict[str, List[Dict]]:
    """Extract all available selectors from an AST tree
    
    Args:
        tree: The AST tree root node
        code: The source code string
        language: The programming language
        
    Returns:
        Dictionary with 'classes', 'functions', 'methods' keys containing lists of available selectors
    """
    selectors = {
        'classes': [],
        'functions': [],
        'methods': []
    }
    
    class_types = get_class_types(language)
    function_types = get_function_types(language)
    
    def traverse(node: Node, class_context: str = None):
        # Check if this is a class
        if node.type in class_types:
            class_name = get_node_name(node, code)
            if class_name:
                selectors['classes'].append({
                    'name': class_name,
                    'line': get_line_number(code, node.start_byte),
                    'signature': get_node_signature(node, code)
                })
                class_context = class_name
        
        # Check if this is a function/method
        elif node.type in function_types:
            func_name = get_node_name(node, code)
            if func_name:
                func_info = {
                    'name': func_name,
                    'line': get_line_number(code, node.start_byte),
                    'signature': get_node_signature(node, code)
                }
                
                if class_context:
                    # This is a method
                    func_info['parent_class'] = class_context
                    func_info['scoped_name'] = f"{class_context}.{func_name}"
                    selectors['methods'].append(func_info)
                else:
                    # This is a standalone function
                    selectors['functions'].append(func_info)
        
        # Recursively traverse children
        for child in node.children:
            traverse(child, class_context)
    
    traverse(tree)
    return selectors


def get_line_number(code: str, byte_offset: int) -> int:
    """Get line number for a byte offset in code"""
    return code[:byte_offset].count('\n') + 1
