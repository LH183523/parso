import time
import os
import sys
import hashlib
import gc
import shutil
import pickle
import platform
import errno
import logging

from parso._compatibility import FileNotFoundError


_PICKLE_VERSION = 30
"""
Version number (integer) for file system cache.

Increment this number when there are any incompatible changes in
the parser tree classes.  For example, the following changes
are regarded as incompatible.

- A class name is changed.
- A class is moved to another module.
- A __slot__ of a class is changed.
"""

_VERSION_TAG = '%s-%s%s-%s' % (
    platform.python_implementation(),
    sys.version_info[0],
    sys.version_info[1],
    _PICKLE_VERSION
)
"""
Short name for distinguish Python implementations and versions.

It's like `sys.implementation.cache_tag` but for Python < 3.3
we generate something similar.  See:
http://docs.python.org/3/library/sys.html#sys.implementation
"""

def _get_default_cache_path():
    if platform.system().lower() == 'windows':
        dir_ = os.path.join(os.getenv('APPDATA') or '~', 'Parso', 'Parso')
    elif platform.system().lower() == 'darwin':
        dir_ = os.path.join('~', 'Library', 'Caches', 'Parso')
    else:
        dir_ = os.path.join(os.getenv('XDG_CACHE_HOME') or '~/.cache', 'parso')
    return os.path.expanduser(dir_)

_default_cache_path = _get_default_cache_path()
"""
The path where the cache is stored.

On Linux, this defaults to ``~/.cache/parso/``, on OS X to
``~/Library/Caches/Parso/`` and on Windows to ``%APPDATA%\\Parso\\Parso\\``.
On Linux, if environment variable ``$XDG_CACHE_HOME`` is set,
``$XDG_CACHE_HOME/parso`` is used instead of the default one.
"""

# for fast_parser, should not be deleted
parser_cache = {}



class _NodeCacheItem(object):
    def __init__(self, node, lines, change_time=None):
        self.node = node
        self.lines = lines
        if change_time is None:
            change_time = time.time()
        self.change_time = change_time


def load_module(grammar_hash, path, cache_path=None):
    """
    Returns a module or None, if it fails.
    """
    try:
        p_time = os.path.getmtime(path)
    except FileNotFoundError:
        return None

    try:
        # TODO Add grammar sha256
        module_cache_item = parser_cache[path]
        if p_time <= module_cache_item.change_time:
            return module_cache_item.node
    except KeyError:
        return _load_from_file_system(grammar_hash, path, p_time, cache_path=cache_path)


def _load_from_file_system(grammar_hash, path, p_time, cache_path=None):
    cache_path = _get_hashed_path(grammar_hash, path, cache_path=cache_path)
    try:
        try:
            if p_time > os.path.getmtime(cache_path):
                # Cache is outdated
                return None
        except OSError as e:
            if e.errno == errno.ENOENT:
                # In Python 2 instead of an IOError here we get an OSError.
                raise FileNotFoundError
            else:
                raise

        with open(cache_path, 'rb') as f:
            gc.disable()
            try:
                module_cache_item = pickle.load(f)
            finally:
                gc.enable()
    except FileNotFoundError:
        return None
    else:
        parser_cache[path] = module_cache_item
        logging.debug('pickle loaded: %s', path)
        return module_cache_item.node


def save_module(grammar_hash, path, module, lines, pickling=True, cache_path=None):
    try:
        p_time = None if path is None else os.path.getmtime(path)
    except OSError:
        p_time = None
        pickling = False

    item = _NodeCacheItem(module, lines, p_time)
    parser_cache[path] = item
    if pickling and path is not None:
        _save_to_file_system(grammar_hash, path, item)


def _save_to_file_system(grammar_hash, path, item, cache_path=None):
    with open(_get_hashed_path(grammar_hash, path, cache_path=cache_path), 'wb') as f:
        pickle.dump(item, f, pickle.HIGHEST_PROTOCOL)


def clear_cache(cache_path=None):
    if cache_path is None:
        cache_path = _default_cache_path
    shutil.rmtree(cache_path)
    parser_cache.clear()


def _get_hashed_path(grammar_hash, path, cache_path=None):
    directory = _get_cache_directory_path(cache_path=cache_path)

    file_hash = hashlib.sha256(path.encode("utf-8")).hexdigest()
    return os.path.join(directory, '%s-%s.pkl' % (grammar_hash, file_hash))


def _get_cache_directory_path(cache_path=None):
    if cache_path is None:
        cache_path = _default_cache_path
    directory = os.path.join(cache_path, _VERSION_TAG)
    if not os.path.exists(directory):
        os.makedirs(directory)
    return directory
