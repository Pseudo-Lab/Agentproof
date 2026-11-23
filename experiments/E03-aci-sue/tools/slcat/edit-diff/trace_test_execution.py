"""Python 3.6-compatible profiling adapter around the repository's native runner.

The argv after the configuration is the unmodified script invocation. Per-test
execution includes setUp/tearDown; collection and class/module setup stay separate.
No test discovery, assertions or test selection are changed by this adapter.
"""
import json
import dis
import hashlib
import inspect
import os
import runpy
import sys
import types
import unittest
import time
import subprocess
import threading
from multiprocessing.process import BaseProcess
import coverage


class AfterImport:
    """Observe the first matching native module after its initialization.

    In particular, the runner must set its environment before importing its
    package. Installing a reporter must not import that package ahead of it.
    Once found, release the observer so later imports retain their native stack.
    """
    def __init__(self, names, callback):
        self.names=set(names)
        self.callback=callback

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self.names:return None
        for finder in list(sys.meta_path):
            if finder is self:continue
            spec=finder.find_spec(fullname,path,target)
            if spec is None:continue
            loader=spec.loader;callback=self.callback;observer=self
            class Loader:
                def create_module(self, spec):
                    return loader.create_module(spec) if hasattr(loader,'create_module') else None
                def exec_module(self, module):
                    loader.exec_module(module)
                    callback(module)
                    if observer in sys.meta_path:
                        sys.meta_path.remove(observer)
                def __getattr__(self, name):return getattr(loader,name)
            spec.loader=Loader()
            return spec
        return None


def main():
    # multiprocessing spawn imports this file as __mp_main__ with the native
    # repository sys.path. Observation helpers belong only to the parent run.
    from aci_test_units import PytestUnits, unittest_unit_for
    config_path,output_path,script=sys.argv[1:4]
    config=json.load(open(config_path))
    targets={}
    for path in config['files']:
        filename=os.path.realpath(os.path.join(config.get('root','/testbed'),path))
        targets.setdefault(filename,[]).append(path)
    hits={};active=[None];original=unittest.TestCase.run;context_files={}
    indexing=config.get('index', False)
    collected={};completed=[];durations={};started={};opaque=set();restore=[];fixture_scopes={};collection_paths=[]
    root=os.path.realpath(config.get('root','/testbed'))
    units=None;import_observer=None;unittest_units={}
    # Python trace callbacks synchronize frame locals on every line. This changes
    # programs retaining locals() (e.g. xarray argument forwarding and Django
    # lazy proxies). Coverage's C tracer records lines without that side effect.
    cov=coverage.Coverage(config_file=False,data_file=None,source=[root],timid=False)
    cov.start()
    trace=sys.gettrace()
    if type(trace).__module__!='coverage':
        cov.stop()
        raise RuntimeError('coverage C tracer is required; Python tracing is not transparent')
    def activate(context):
        active[0]=context
        cov.switch_context(context or '__shared_setup__')
    activate(None)
    def opaque_wrapper(owner,name):
        method=getattr(owner,name);restore.append((owner,name,method))
        def wrapped(self,*args,**kwargs):
            argv=args[0] if args else kwargs.get('args')
            version_probe=(owner is subprocess.Popen and isinstance(argv,(list,tuple)) and
                           list(argv)==[sys.executable,'-RV'])
            if not version_probe:opaque.add(active[0] or '__shared_setup__')
            return method(self,*args,**kwargs)
        setattr(owner,name,wrapped)
    if indexing:
        opaque_wrapper(subprocess.Popen,'__init__')
        opaque_wrapper(threading.Thread,'start')
        opaque_wrapper(BaseProcess,'start')
    wanted=config.get('lines')
    def source_hashes():
        result={}
        for path in config['files']:
            try:
                with open(os.path.join(root,path),'rb') as source:result[path]=hashlib.sha256(source.read()).hexdigest()
            except OSError:result[path]=None
        return result
    before=source_hashes() if 'source_hashes' in config else None
    executable={}
    if wanted is not None:
        def code_lines(code):
            found={n for _,n in dis.findlinestarts(code) if n>0}
            for value in code.co_consts:
                if isinstance(value,types.CodeType):found.update(code_lines(value))
            return found
        for path in config['files']:
            filename=os.path.join(root,path)
            try:
                with open(filename,'rb') as source:code=compile(source.read(),filename,'exec',dont_inherit=True)
                executable[path]=sorted(code_lines(code)&set(wanted.get(path,[])))
            except (OSError,SyntaxError,ValueError):executable[path]=None
        wanted={p:set(ns) for p,ns in wanted.items()}
    def remember(test,filename):
        if filename:
            path=os.path.relpath(os.path.realpath(filename),root)
            if path!='..' and not path.startswith('../'):
                context_files[test]=path
                if indexing:collected[test]=path
    def begin(test,filename):
        if sys.gettrace() is not trace:
            opaque.add('__shared_setup__')
        remember(test,filename)
        started[test]=time.monotonic()
    def finish(test):
        if sys.gettrace() is not trace:
            opaque.add(test)
        completed.append(test)
        durations[test]=durations.get(test,0)+time.monotonic()-started.pop(test,time.monotonic())
    def fixture_context(prefix,separator):
        context='__fixture__:'+separator+prefix
        fixture_scopes[context]=(prefix,separator)
        return context
    def test_run(self,*args,**kwargs):
        previous=active[0];activate(previous or self.id())
        if indexing and previous is None and config.get('runner')=='django':
            unittest_units[active[0]]=unittest_unit_for(self)
        try:
            if previous is None:
                if indexing:begin(active[0],inspect.getsourcefile(type(self)))
                else:remember(active[0],inspect.getsourcefile(type(self)))
        except (TypeError,OSError):pass
        try:return original(self,*args,**kwargs)
        finally:
            if indexing and previous is None:finish(active[0])
            activate(previous)
    unittest.TestCase.run=test_run
    if indexing and config.get('runner')=='django':
        def fixture_wrapper(name,previous_class=False,module=False):
            method=getattr(unittest.TestSuite,name);restore.append((unittest.TestSuite,name,method))
            def wrapped(suite,*args):
                cls=getattr(args[-1],'_previousTestClass',None) if previous_class else type(args[0])
                if cls is None:return method(suite,*args)
                prefix=cls.__module__ if module else cls.__module__+'.'+cls.__qualname__
                previous=active[0];activate(fixture_context(prefix,'.'))
                try:return method(suite,*args)
                finally:activate(previous)
            setattr(unittest.TestSuite,name,wrapped)
        fixture_wrapper('_handleClassSetUp')
        fixture_wrapper('_tearDownPreviousClass',previous_class=True)
        fixture_wrapper('_handleModuleFixture',module=True)
        fixture_wrapper('_handleModuleTearDown',previous_class=True,module=True)
    args=sys.argv[4:]
    sys.argv=[script]+args
    sys.path[0]=os.getcwd() if script=='-m' else os.path.dirname(os.path.abspath(script))
    try:
        if indexing and config.get('runner')=='sympy':
            reporters=set()
            def sympy_begin(self,f):
                activate(self._active_file+'::'+f.__name__)
                begin(active[0],os.path.join(root,self._active_file))
            def sympy_end(self,*a,**kw):
                if active[0] is not None:finish(active[0])
                activate(None)
            def attach_reporter(module):
                reporter=module.PyTestReporter
                if reporter in reporters:return
                reporters.add(reporter)
                def wrap(name, before=None, after=None):
                    method=getattr(reporter,name);restore.append((reporter,name,method))
                    def wrapped(self,*a,**kw):
                        if before:before(self,*a,**kw)
                        try:return method(self,*a,**kw)
                        finally:
                            if after:after(self,*a,**kw)
                    setattr(reporter,name,wrapped)
                wrap('entering_test',before=sympy_begin)
                for name in ('test_pass','test_fail','test_exception','test_skip','test_xfail','test_xpass'):
                    wrap(name,after=sympy_end)
                wrap('leaving_filename',after=sympy_end)
            import_observer=AfterImport(('sympy.testing.runtests','sympy.utilities.runtests'),attach_reporter)
            sys.meta_path.insert(0,import_observer)
        if script=='-m' and args and args[0]=='pytest':
            import pytest
            units=PytestUnits(root) if indexing or config.get('unit_report') else None
            class ContextPlugin:
                def pytest_collection_finish(self,session):
                    if indexing:
                        collection_paths[:]=session.config.args
                        for item in session.items:collected[item.nodeid]=os.path.relpath(str(item.fspath),root)
                @pytest.hookimpl(hookwrapper=True)
                def pytest_fixture_setup(self,fixturedef,request):
                    previous=active[0]
                    if indexing and request.scope!='function':
                        activate(fixture_context(request.node.nodeid,'/' if request.scope=='package' else '::'))
                    try:yield
                    finally:activate(previous)
                @pytest.hookimpl(hookwrapper=True)
                def pytest_runtest_protocol(self,item,nextitem):
                    previous=active[0];activate(item.nodeid)
                    if indexing:begin(item.nodeid,str(item.fspath))
                    else:remember(item.nodeid,str(item.fspath))
                    try:yield
                    finally:
                        if indexing:finish(item.nodeid)
                        activate(previous)
            plugins=[ContextPlugin()]+([units] if units is not None else [])
            raise SystemExit(pytest.main(args[1:],plugins=plugins))
        elif script=='-m':
            sys.argv=args
            runpy.run_module(args[0],run_name='__main__',alter_sys=True)
        else:runpy.run_path(script,run_name='__main__')
    finally:
        if import_observer in sys.meta_path:sys.meta_path.remove(import_observer)
        cov.stop();unittest.TestCase.run=original
        for owner,name,method in reversed(restore):setattr(owner,name,method)
        data=cov.get_data()
        for filename in data.measured_files():
            paths=targets.get(os.path.realpath(filename),[])
            for path in paths:
                for line,contexts in data.contexts_by_lineno(filename).items():
                    if wanted is not None and line not in wanted.get(path,()):continue
                    for context in contexts:
                        hits.setdefault(context or '__shared_setup__',{}).setdefault(path,set()).add(line)
        # Preserve direct observations separately from conservative fixture
        # ownership. A scope member did not necessarily execute fixture lines.
        raw_contexts={t:{p:sorted(ns) for p,ns in files.items()} for t,files in hits.items()}
        fixture_owners={}
        # A shared fixture belongs to its declared scope, not only the first
        # test that happened to initialize it. Keep all assertions in that scope.
        for context,(prefix,separator) in fixture_scopes.items():
            owners=[t for t in collected if not prefix or t==prefix or t.startswith(prefix+separator)] or ['__shared_setup__']
            fixture_owners[context]=dict(prefix=prefix,separator=separator,tests=owners)
            measured=hits.pop(context,{})
            for test in owners:
                for path,lines in measured.items():
                    hits.setdefault(test,{}).setdefault(path,set()).update(lines)
            if context in opaque:
                opaque.remove(context);opaque.update(owners or ['__shared_setup__'])
        with open(output_path,'w') as f:
            result={'contexts':{t:{p:sorted(ns) for p,ns in files.items()} for t,files in hits.items()},
                       'context_files':context_files,'files':config['files'],
                       'adapter':'coverage C tracer; unittest.TestCase.run / pytest protocol; native test arguments unchanged',
                       'coverage_version':coverage.__version__}
            if wanted is not None:
                result['executable_lines']=executable
                result['requested_lines']={p:sorted(ns) for p,ns in wanted.items()}
            if before is not None:
                result.update(source_hashes_before=before,source_hashes_after=source_hashes())
            if indexing:
                result.update(collected=collected,completed=completed,durations=durations,
                              raw_contexts=raw_contexts,fixture_owners=fixture_owners,
                              file_aliases=[paths for paths in targets.values() if len(paths)>1],
                              collection_paths=collection_paths,
                              opaque_contexts=sorted(opaque),
                              trace_scope='current process; subprocess.Popen, threading.Thread and multiprocessing.Process starts are opaque')
                if units is not None:result['test_units']=units.result()
                elif config.get('runner')=='django':
                    result['test_units']={'case_units':unittest_units}
            json.dump(result,f)
        if units is not None and config.get('unit_report'):
            units.write(config['unit_report'])


if __name__=='__main__':main()
