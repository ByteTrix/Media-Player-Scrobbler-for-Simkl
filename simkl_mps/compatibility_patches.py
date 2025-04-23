"""
Compatibility patches for libraries that haven't been updated for Python 3.10+
"""
import collections
import collections.abc


for abc_class in ['MutableMapping', 'Mapping', 'Sequence', 'MutableSequence', 'Set', 'MutableSet']:
    if not hasattr(collections, abc_class):
        setattr(collections, abc_class, getattr(collections.abc, abc_class))

def apply_patches():
    """Apply all compatibility patches"""
    # Currently all patches are applied at import time, but more complex
    # patching logic can be added here if needed later
    pass