"""Run current and relocated-base entry points through the same native importers.

Python 3.5 compatible. Editable-install .pth files can create package placeholders
before the entry point runs; PYTHONPATH alone does not relocate those packages.
Executed project imports cannot safely be undone and are rejected. This protects
imports in this process, not arbitrary file access or descendant processes.
"""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import runpy
import sys


def relocate(source, base, current=False):
    source, base = Path(source).resolve(), Path(base).resolve()
    if current and source != base:
        raise ValueError('current entry point requires identical source and target roots')
    if not current and (source == base or source in base.parents or base in source.parents):
        raise ValueError('baseline and edited roots must be separate')

    def original(path):
        if not isinstance(path, str) or not path:
            return None
        try:
            return Path(path).resolve().relative_to(source)
        except (ValueError, OSError):
            return None

    def mapped(path):
        relative = original(path)
        return str(base / relative) if relative is not None else path

    sys.path[:] = [mapped(path) for path in sys.path]
    metadata = {'__name__', '__doc__', '__package__', '__loader__', '__spec__',
                '__path__', '__file__', '__cached__'}
    # Parents first, so native namespace specs can consult their relocated paths.
    for name, module in sorted(list(sys.modules.items()), key=lambda item: item[0].count('.')):
        paths = list(getattr(module, '__path__', ()))
        if original(getattr(module, '__file__', None)) is None and not any(original(p) is not None for p in paths):
            continue
        if not paths or set(vars(module)) - metadata:
            raise ImportError('baseline cannot relocate an already executed project module: ' + name)
        search = []
        for path in paths:
            parent = str(Path(mapped(path)).parent)
            if parent not in search:
                search.append(parent)
        spec = importlib.machinery.PathFinder.find_spec(name, search)
        if spec is None:
            raise ImportError('baseline package placeholder cannot be resolved: ' + name)
        replacement = importlib.util.module_from_spec(spec)
        sys.modules[name] = replacement
        parent, _, child = name.rpartition('.')
        if parent in sys.modules and getattr(sys.modules[parent], child, None) is module:
            setattr(sys.modules[parent], child, replacement)

    class BaseImports:
        def find_spec(self, fullname, path=None, target=None):
            for finder in list(sys.meta_path):
                if finder is self:
                    continue
                if hasattr(finder, 'find_spec'):
                    spec = finder.find_spec(fullname, path, target)
                else:
                    # Native PEP 302 compatibility, including older interpreters.
                    loader = finder.find_module(fullname, path)
                    spec = importlib.util.spec_from_loader(fullname, loader) if loader is not None else None
                if spec is None:
                    continue
                locations = [spec.origin] + list(spec.submodule_search_locations or ())
                if not current and any(original(location) is not None for location in locations):
                    raise ImportError('baseline import resolved to the edited project: ' + fullname)
                return spec
            return None

    sys.meta_path.insert(0, BaseImports())
    importlib.invalidate_caches()


def main():
    args = sys.argv[1:]
    current = args[:1] == ['--current']
    if current:
        args = args[1:]
    source, base, entry = args[:3]
    args = args[3:]
    if Path.cwd().resolve() != Path(base).resolve():
        raise ValueError('baseline entry point must run in the base workspace')
    relocate(source, base, current=current)
    if entry == '-m':
        sys.path[0] = os.getcwd()
        sys.argv = args
        runpy.run_module(args[0], run_name='__main__', alter_sys=True)
    elif entry.startswith('-'):
        raise ValueError('baseline requires a Python script or -m module')
    else:
        sys.path[0] = os.path.dirname(os.path.abspath(entry))
        sys.argv = [entry] + args
        runpy.run_path(entry, run_name='__main__')


if __name__ == '__main__':
    main()
