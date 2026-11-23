"""Freezing must never replace the source archive when validation fails."""
import hashlib
import tempfile
import unittest
from pathlib import Path
import finalize_v5 as F


class FreezeTests(unittest.TestCase):
    def test_validation_failure_leaves_existing_archive_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir()
            archive=Path(tmp)/'archive';archive.mkdir()
            (root/'a.py').write_text('new a')
            (root/'b.py').write_text('unexpected b')
            (archive/'a.py').write_text('original a')
            with self.assertRaises(ValueError):
                F.freeze_sources(root,archive,['a.py','b.py'],{'b.py':hashlib.sha256(b'expected b').hexdigest()})
            self.assertEqual((archive/'a.py').read_text(),'original a')
            self.assertFalse((archive/'b.py').exists())

    def test_existing_snapshot_is_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir()
            archive=Path(tmp)/'archive';archive.mkdir()
            (root/'a.py').write_text('new a');(archive/'a.py').write_text('original a')
            with self.assertRaises(ValueError):F.freeze_sources(root,archive,['a.py'],{})
            self.assertEqual((archive/'a.py').read_text(),'original a')

if __name__=='__main__':unittest.main()
