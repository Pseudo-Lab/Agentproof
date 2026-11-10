#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: CC-BY-NC-4.0

"""File operations and caching utilities

This module provides shared file I/O and caching utilities used by both
CodeRead and CodeWrite servers. It includes functions for file reading/writing,
caching, and file management operations.
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Union


class CodeCache:
    """Simple file-based cache for parsed signatures and other data"""
    
    def __init__(self, cache_dir: str = ".coderead_cache"):
        """Initialize cache with specified directory
        
        Args:
            cache_dir: Directory to store cache files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def _get_cache_key(self, file_path: str, mtime: float) -> str:
        """Generate cache key based on file path and modification time
        
        Args:
            file_path: Path to the file
            mtime: File modification time
            
        Returns:
            MD5 hash of the cache key
        """
        return hashlib.md5(f"{file_path}:{mtime}".encode()).hexdigest()
    
    def get(self, file_path: str) -> Optional[List[Dict]]:
        """Get cached data for a file
        
        Args:
            file_path: Path to the file
            
        Returns:
            Cached data or None if not found/expired
        """
        try:
            mtime = os.path.getmtime(file_path)
            cache_key = self._get_cache_key(file_path, mtime)
            cache_file = self.cache_dir / f"{cache_key}.json"
            
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return None
    
    def set(self, file_path: str, data: List[Dict]):
        """Cache data for a file
        
        Args:
            file_path: Path to the file
            data: Data to cache
        """
        try:
            mtime = os.path.getmtime(file_path)
            cache_key = self._get_cache_key(file_path, mtime)
            cache_file = self.cache_dir / f"{cache_key}.json"
            
            with open(cache_file, 'w') as f:
                json.dump(data, f)
        except:
            pass
    
    def clear(self, file_path: str = None):
        """Clear cache for a specific file or all files
        
        Args:
            file_path: Path to specific file, or None to clear all
        """
        try:
            if file_path:
                # Clear cache for specific file
                mtime = os.path.getmtime(file_path)
                cache_key = self._get_cache_key(file_path, mtime)
                cache_file = self.cache_dir / f"{cache_key}.json"
                if cache_file.exists():
                    cache_file.unlink()
            else:
                # Clear all cache files
                for cache_file in self.cache_dir.glob("*.json"):
                    cache_file.unlink()
        except:
            pass
    
    def get_cache_size(self) -> int:
        """Get the number of cached files
        
        Returns:
            Number of cache files
        """
        try:
            return len(list(self.cache_dir.glob("*.json")))
        except:
            return 0


def read_file_safe(file_path: str, encoding: str = 'utf-8') -> Optional[str]:
    """Safely read a file with error handling
    
    Args:
        file_path: Path to the file to read
        encoding: File encoding (default: utf-8)
        
    Returns:
        File content as string, or None if error
        
    Examples:
        >>> content = read_file_safe("main.py")
        >>> if content:
        ...     print("File read successfully")
    """
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            return f.read()
    except Exception:
        return None


def write_file_safe(file_path: str, content: str, encoding: str = 'utf-8') -> bool:
    """Safely write content to a file with error handling
    
    Args:
        file_path: Path to the file to write
        content: Content to write
        encoding: File encoding (default: utf-8)
        
    Returns:
        True if successful, False otherwise
        
    Examples:
        >>> success = write_file_safe("output.py", "print('hello')")
        >>> if success:
        ...     print("File written successfully")
    """
    try:
        with open(file_path, 'w', encoding=encoding) as f:
            f.write(content)
        return True
    except Exception:
        return False


def read_file_with_fallback(file_path: str, fallback_encodings: List[str] = None) -> Optional[str]:
    """Read file with multiple encoding fallbacks
    
    Args:
        file_path: Path to the file to read
        fallback_encodings: List of encodings to try (default: ['utf-8', 'latin-1', 'cp1252'])
        
    Returns:
        File content as string, or None if all encodings fail
    """
    if fallback_encodings is None:
        fallback_encodings = ['utf-8', 'latin-1', 'cp1252']
    
    for encoding in fallback_encodings:
        content = read_file_safe(file_path, encoding)
        if content is not None:
            return content
    
    return None


def get_file_info(file_path: str) -> Dict[str, Union[str, int, float, bool]]:
    """Get comprehensive file information
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary with file information
    """
    try:
        path_obj = Path(file_path)
        stat = path_obj.stat()
        
        return {
            'path': str(path_obj.absolute()),
            'name': path_obj.name,
            'stem': path_obj.stem,
            'suffix': path_obj.suffix,
            'size': stat.st_size,
            'mtime': stat.st_mtime,
            'exists': path_obj.exists(),
            'is_file': path_obj.is_file(),
            'is_dir': path_obj.is_dir(),
            'parent': str(path_obj.parent)
        }
    except Exception:
        return {
            'path': file_path,
            'name': '',
            'stem': '',
            'suffix': '',
            'size': 0,
            'mtime': 0,
            'exists': False,
            'is_file': False,
            'is_dir': False,
            'parent': ''
        }


def backup_file(file_path: str, backup_suffix: str = '.backup') -> Optional[str]:
    """Create a backup of a file
    
    Args:
        file_path: Path to the file to backup
        backup_suffix: Suffix for backup file
        
    Returns:
        Path to backup file, or None if failed
    """
    try:
        path_obj = Path(file_path)
        if not path_obj.exists():
            return None
        
        backup_path = path_obj.with_suffix(path_obj.suffix + backup_suffix)
        content = read_file_safe(file_path)
        if content is None:
            return None
        
        if write_file_safe(str(backup_path), content):
            return str(backup_path)
        return None
    except Exception:
        return None


def restore_file(backup_path: str, original_path: str) -> bool:
    """Restore a file from backup
    
    Args:
        backup_path: Path to the backup file
        original_path: Path to restore to
        
    Returns:
        True if successful, False otherwise
    """
    try:
        content = read_file_safe(backup_path)
        if content is None:
            return False
        
        return write_file_safe(original_path, content)
    except Exception:
        return False


def count_occurrences_in_file(file_path: str, search_string: str) -> int:
    """Count occurrences of a string in a file
    
    Args:
        file_path: Path to the file
        search_string: String to search for
        
    Returns:
        Number of occurrences
    """
    content = read_file_safe(file_path)
    if content is None:
        return 0
    
    return content.count(search_string)


def replace_in_file(file_path: str, old_string: str, new_string: str, 
                   count: int = -1, create_backup: bool = True) -> Dict[str, Union[str, int, bool]]:
    """Replace string in file with safety checks
    
    Args:
        file_path: Path to the file
        old_string: String to replace
        new_string: Replacement string
        count: Maximum number of replacements (-1 for all)
        create_backup: Whether to create backup before replacement
        
    Returns:
        Dictionary with operation result
    """
    result = {
        'success': False,
        'message': '',
        'replacements': 0,
        'backup_path': None
    }
    
    try:
        # Read file content
        content = read_file_safe(file_path)
        if content is None:
            result['message'] = f"Could not read file: {file_path}"
            return result
        
        # Count occurrences
        occurrences = content.count(old_string)
        if occurrences == 0:
            result['message'] = f"String '{old_string}' not found in file"
            return result
        
        if count == -1:
            count = occurrences
        
        # Create backup if requested
        if create_backup:
            backup_path = backup_file(file_path)
            if backup_path:
                result['backup_path'] = backup_path
        
        # Perform replacement
        new_content = content.replace(old_string, new_string, count)
        
        # Write back to file
        if write_file_safe(file_path, new_content):
            result['success'] = True
            result['replacements'] = min(count, occurrences)
            result['message'] = f"Successfully replaced {result['replacements']} occurrence(s)"
        else:
            result['message'] = f"Could not write to file: {file_path}"
            
    except Exception as e:
        result['message'] = f"Replacement failed: {str(e)}"
    
    return result


def validate_file_operation(file_path: str, operation: str) -> Dict[str, Union[str, bool]]:
    """Validate file operation parameters
    
    Args:
        file_path: Path to the file
        operation: Operation type ('read', 'write', 'modify')
        
    Returns:
        Dictionary with validation result
    """
    result = {
        'valid': False,
        'message': '',
        'file_info': None
    }
    
    try:
        path_obj = Path(file_path)
        
        if operation == 'read':
            if not path_obj.exists():
                result['message'] = f"File does not exist: {file_path}"
                return result
            if not path_obj.is_file():
                result['message'] = f"Path is not a file: {file_path}"
                return result
                
        elif operation in ['write', 'modify']:
            # For write/modify, parent directory must exist
            if not path_obj.parent.exists():
                result['message'] = f"Parent directory does not exist: {path_obj.parent}"
                return result
                
        result['valid'] = True
        result['file_info'] = get_file_info(file_path)
        result['message'] = f"File operation '{operation}' is valid"
        
    except Exception as e:
        result['message'] = f"Validation failed: {str(e)}"
    
    return result


def create_file(file_path: str, content: str, encoding: str = 'utf-8') -> Dict[str, Union[str, bool]]:
    """Create a new file with content
    
    Args:
        file_path: Path where file should be created
        content: Content to write
        encoding: File encoding (default: utf-8)
        
    Returns:
        Dictionary with operation result
    """
    result = {'success': False, 'message': ''}
    
    try:
        path_obj = Path(file_path)
        if path_obj.exists():
            result['message'] = f"File already exists: {file_path}"
            return result
        
        if write_file_safe(file_path, content, encoding):
            result['success'] = True
            result['message'] = f"File created: {file_path}"
        else:
            result['message'] = f"Failed to create file: {file_path}"
    except Exception as e:
        result['message'] = f"Error: {str(e)}"
    
    return result


# Global cache instance for backward compatibility
cache = CodeCache()
