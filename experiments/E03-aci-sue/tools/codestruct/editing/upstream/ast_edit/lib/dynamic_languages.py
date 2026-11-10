#!/usr/bin/env python3
"""Dynamic tree-sitter language loader"""

import importlib
import pkgutil
import warnings
from tree_sitter import Language

# Common tree-sitter language packages and their function names
LANGUAGE_PACKAGES = {
    'tree_sitter_python': 'language',
    'tree_sitter_javascript': 'language', 
    'tree_sitter_typescript': 'language_typescript',
    'tree_sitter_java': 'language',
    'tree_sitter_c': 'language',
    'tree_sitter_cpp': 'language',
    'tree_sitter_c_sharp': 'language',
    'tree_sitter_go': 'language',
    'tree_sitter_rust': 'language',
    'tree_sitter_ruby': 'language',
    'tree_sitter_php': 'language_php',
    'tree_sitter_swift': 'language',
    'tree_sitter_kotlin': 'language',
    'tree_sitter_scala': 'language',
    'tree_sitter_lua': 'language',
    'tree_sitter_r': 'language',
    'tree_sitter_julia': 'language',
    'tree_sitter_dart': 'language',
    'tree_sitter_elixir': 'language',
    'tree_sitter_elm': 'language',
    'tree_sitter_clojure': 'language',
    'tree_sitter_hcl': 'language',
    'tree_sitter_matlab': 'language',
    'tree_sitter_ocaml': 'language_ocaml',
    'tree_sitter_bash': 'language',
    'tree_sitter_css': 'language',
    'tree_sitter_html': 'language',
    'tree_sitter_json': 'language',
    'tree_sitter_yaml': 'language',
    'tree_sitter_toml': 'language',
    'tree_sitter_xml': 'language',
    'tree_sitter_sql': 'language',
    'tree_sitter_dockerfile': 'language',
    'tree_sitter_markdown': 'language',
    'tree_sitter_latex': 'language',
    'tree_sitter_vim': 'language',
    'tree_sitter_perl': 'language',
    'tree_sitter_haskell': 'language',
    'tree_sitter_erlang': 'language',
    'tree_sitter_zig': 'language',
    'tree_sitter_nix': 'language',
    'tree_sitter_solidity': 'language',
    'tree_sitter_verilog': 'language',
    'tree_sitter_vhdl': 'language',
    'tree_sitter_fortran': 'language',
    'tree_sitter_cobol': 'language',
    'tree_sitter_ada': 'language',
    'tree_sitter_pascal': 'language',
    'tree_sitter_scheme': 'language',
    'tree_sitter_racket': 'language',
    'tree_sitter_prolog': 'language',
    'tree_sitter_smalltalk': 'language',
    'tree_sitter_tcl': 'language',
    'tree_sitter_crystal': 'language',
    'tree_sitter_d': 'language',
    'tree_sitter_nim': 'language',
    'tree_sitter_odin': 'language',
    'tree_sitter_v': 'language',
    'tree_sitter_gleam': 'language',
    'tree_sitter_pony': 'language',
    'tree_sitter_roc': 'language',
}

# File extension mappings
EXTENSION_MAP = {
    '.py': 'python', '.pyw': 'python',
    '.js': 'javascript', '.jsx': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
    '.ts': 'typescript', '.tsx': 'typescript',
    '.java': 'java',
    '.c': 'c', '.h': 'c',
    '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp', '.hpp': 'cpp', '.hxx': 'cpp',
    '.cs': 'c_sharp',
    '.go': 'go',
    '.rs': 'rust',
    '.rb': 'ruby',
    '.php': 'php', '.phtml': 'php',
    '.swift': 'swift',
    '.kt': 'kotlin', '.kts': 'kotlin',
    '.scala': 'scala', '.sc': 'scala',
    '.lua': 'lua',
    '.r': 'r', '.R': 'r',
    '.jl': 'julia',
    '.dart': 'dart',
    '.ex': 'elixir', '.exs': 'elixir',
    '.elm': 'elm',
    '.clj': 'clojure', '.cljs': 'clojure', '.cljc': 'clojure',
    '.tf': 'hcl', '.hcl': 'hcl',
    '.m': 'matlab',
    '.ml': 'ocaml', '.mli': 'ocaml',
    '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash',
    '.css': 'css', '.scss': 'css', '.sass': 'css',
    '.html': 'html', '.htm': 'html',
    '.json': 'json',
    '.yaml': 'yaml', '.yml': 'yaml',
    '.toml': 'toml',
    '.xml': 'xml',
    '.sql': 'sql',
    '.dockerfile': 'dockerfile', '.Dockerfile': 'dockerfile',
    '.md': 'markdown', '.markdown': 'markdown',
    '.tex': 'latex', '.latex': 'latex',
    '.vim': 'vim', '.vimrc': 'vim',
    '.pl': 'perl', '.pm': 'perl',
    '.hs': 'haskell', '.lhs': 'haskell',
    '.erl': 'erlang', '.hrl': 'erlang',
    '.zig': 'zig',
    '.nix': 'nix',
    '.sol': 'solidity',
    '.v': 'verilog', '.sv': 'verilog',
    '.vhd': 'vhdl', '.vhdl': 'vhdl',
    '.f': 'fortran', '.f90': 'fortran', '.f95': 'fortran',
    '.cob': 'cobol', '.cbl': 'cobol',
    '.ada': 'ada', '.adb': 'ada', '.ads': 'ada',
    '.pas': 'pascal',
    '.scm': 'scheme', '.ss': 'scheme',
    '.rkt': 'racket',
    '.pl': 'prolog',
    '.st': 'smalltalk',
    '.tcl': 'tcl',
    '.cr': 'crystal',
    '.d': 'd',
    '.nim': 'nim',
    '.odin': 'odin',
    '.gleam': 'gleam',
    '.pony': 'pony',
    '.roc': 'roc',
}

def load_all_languages():
    """Dynamically load all available tree-sitter languages"""
    languages = {}
    
    for package_name, func_name in LANGUAGE_PACKAGES.items():
        try:
            module = importlib.import_module(package_name)
            lang_func = getattr(module, func_name)
            lang_name = package_name.replace('tree_sitter_', '')
            lang_ptr = lang_func()
            # Suppress FutureWarning from tree-sitter about Language() constructor
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')
                languages[lang_name] = Language(lang_ptr)
        except (ImportError, AttributeError, TypeError) as e:
            pass  # Silently skip unavailable languages
    
    return languages

def get_all_extensions():
    """Get all supported file extensions"""
    return set(EXTENSION_MAP.keys())

if __name__ == "__main__":
    print("Loading all available tree-sitter languages...")
    langs = load_all_languages()
    print(f"\n🎉 Successfully loaded {len(langs)} languages:")
    for lang in sorted(langs.keys()):
        print(f"  - {lang}")