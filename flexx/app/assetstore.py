"""
Asset store.

The purpose of these classes is simple: they must provide the assets
(JavaScript files, CSS files, images, etc.) needed by the applications.

Assets are global, which makes certain things (e.g. exporting a bunch
of apps to the same directory) very simple.

Naturally, different sessions may need different assets with the same
name. Therefore the SessionAssets class provides a way to manage assets
with name mangling.
    
Groups of Model classes can be added as a CSS and JS asset using
``assets.create_module_assets()``, which will select all Model classes
present in the given Python module. Classes used by the session that
are not provided via such a module asset will be added to the index.
"""

import os
import sys
import json
import time
import random
import hashlib
import logging
from urllib.request import urlopen
from collections import OrderedDict

from .model import Model, get_model_classes

INDEX = """<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>Flexx UI</title>

ASSET-LINK-HOOK

</head>

<body id='body'>

ASSET-CONTENT-HOOK

</body>
</html>
"""

RESET = """
/*! normalize.css v3.0.3 | MIT License | github.com/necolas/normalize.css */
html
{font-family:sans-serif;-ms-text-size-adjust:100%;-webkit-text-size-adjust:100%}
body{margin:0}
article,aside,details,figcaption,figure,footer,header,hgroup,main,menu,nav,
section,summary{display:block}
audio,canvas,progress,video{display:inline-block;vertical-align:baseline}
audio:not([controls]){display:none;height:0}
[hidden],template{display:none}
a{background-color:transparent}
a:active,a:hover{outline:0}
abbr[title]{border-bottom:1px dotted}
b,strong{font-weight:bold}
dfn{font-style:italic}
h1{font-size:2em;margin:.67em 0}
mark{background:#ff0;color:#000}
small{font-size:80%}
sub,sup{font-size:75%;line-height:0;position:relative;vertical-align:baseline}
sup{top:-0.5em}
sub{bottom:-0.25em}
img{border:0}
svg:not(:root){overflow:hidden}
figure{margin:1em 40px}
hr{box-sizing:content-box;height:0}
pre{overflow:auto}
code,kbd,pre,samp{font-family:monospace,monospace;font-size:1em}
button,input,optgroup,select,textarea{color:inherit;font:inherit;margin:0}
button{overflow:visible}
button,select{text-transform:none}
button,html input[type="button"],input[type="reset"],input[type="submit"]
{-webkit-appearance:button;cursor:pointer}
button[disabled],html input[disabled]{cursor:default}
button::-moz-focus-inner,input::-moz-focus-inner{border:0;padding:0}
input{line-height:normal}
input[type="checkbox"],input[type="radio"]{box-sizing:border-box;padding:0}
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button{height:auto}
input[type="search"]{-webkit-appearance:textfield;box-sizing:content-box}
input[type="search"]::-webkit-search-cancel-button,
input[type="search"]::-webkit-search-decoration{-webkit-appearance:none}
fieldset{border:1px solid #c0c0c0;margin:0 2px;padding:.35em .625em .75em}
legend{border:0;padding:0}
textarea{overflow:auto}
optgroup{font-weight:bold}
table{border-collapse:collapse;border-spacing:0}
td,th{padding:0}
"""


reprs = json.dumps


def lookslikeafilename(s):
    # We need this to allow smart-asset setting on legacy Python
    if sys.version_info[0] == 2:
        fchars = '\n\r\x00\x0a'.encode('utf-8')
        if isinstance(s, unicode):  # noqa
            return True
        elif not isinstance(s, bytes):
            return False
        elif any([c in s for c in fchars]):
            return False
        elif len(s) > 500 and s.count('function(') > 5:
            return False  # Looks like a minified file. Bah, rather arbitrary
        else:
            return True
    return isinstance(s, str)


def modname_startswith(x, y):
    return (x + '.').startswith(y + '.')


def create_css_and_js_from_model_classes(classes, css='', js=''):
    # Collect CSS and JS, and filter out empty ones
    css, js = [css], ['"use strict";', js]
    for cls in classes:
        css.append(cls.CSS)  # the CSS is '' if not specified for that class
        js.append(cls.JS.CODE)
    css = [i for i in css if i.strip()]
    js = [i for i in js if i.strip()]
    return '\n\n'.join(css) or '\n', '\n\n'.join(js) or '\n'


class AssetStore:
    """ Global provider of client assets (CSS, JavaScript, images, etc.).
    
    Assets are global to the process via the AssetStore instance at
    ``flexx.app.assets``. Use the Session instance for unique (name
    mangled) assets.
    """
    
    def __init__(self):
        self._cache = {}
        self._assets = {}
        self._module_names = []
        self.add_asset('reset.css', RESET.encode())
    
    def _cache_get(self, key):
        """ Get content using caching.
        """
        if key not in self._cache:
            if key.startswith('http://') or key.startswith('https://'):
                self._cache[key] = urlopen(key, timeout=5.0).read()
            elif os.path.isfile(key):
                self._cache[key] = open(key, 'rb').read()
            else:  # this should never happen
                raise RuntimeError('Asset cache key is not a known module '
                                   'or filename: %r' % key)
        return self._cache[key]
    
    def get_asset_names(self):
        """ Get a list of all asset names (ordered alphabetically).
        """
        # Note: order matters not (it does for the session though)
        return list(sorted(self._assets.keys()))
    
    def add_asset(self, fname, content):
        """ Add an asset. Can be JavaScript, CSS, images, etc. 
        
        Parameters:
            fname (str): the (relative) filename for the asset.
            content (str, bytes): the content of the asset. If a str,
                it is interpreted as the filename or url to the asset
                (the contents will be cached). If bytes, it is
                interpreted as the raw asset content.
        """
        if fname in self._assets:
            if content == self._assets[fname]:
                return  # asset is the same (same filename or same bytes)
            else:
                raise ValueError('Asset %r is already set. Can only reuse if '
                                 'content is a filename and the same.' % fname)
        
        if lookslikeafilename(content):  # isinstance(content, str) on py3k
            if content.startswith('http://') or content.startswith('https://'):
                pass  # don't check now
            elif not os.path.isfile(content):
                content = content if (len(content) < 99) else content[:99] + '...'
                raise ValueError('Asset file does not exist: %r' % content)
            self._assets[fname] = content
        elif isinstance(content, bytes):
            self._assets[fname] = content
        else:
            raise ValueError('An asset must be str filename or bytes.')
    
    def load_asset(self, fname):
        """ Get the asset corresponding to the given name.
        
        Parameters:
            fname (str): the (relative) filename for the asset.
        Returns:
            asset (bytes): the asset content.
        """
        try:
            content = self._assets[fname]
        except KeyError:
            raise IndexError('Asset %r not known.' % fname)
        
        if lookslikeafilename(content):
            return self._cache_get(content)
        else:
            return content
    
    def get_module_name_for_model_class(self, cls):
        """ Given a Model class, get the module name for which we have
        a corresponding asset, or None if we don't.
        """
        modname = cls.__module__
        for name in self._module_names:
            if modname_startswith(modname, name):
                return name
    
    def create_module_assets(self, module_name, css='', js=''):
        """ Create an asset with Model classes from a Python module.
        
        Create a JS and CSS asset containing the definitions of all Model classes
        defined in the given module.
        
        Parameters:
            module_name (str): the Python module to create a module asset for.
            css (str, optional): additional CSS to prepend to the module.
            js (str, optional): additional JS to prepend to the module.
        """
        # Collect classes and remember which ones we have covered
        classes = list()
        for cls in get_model_classes():
            if modname_startswith(cls.__module__, module_name):
                # This cls is in our module, check if we dont already have it
                for name in self._module_names:
                    if modname_startswith(cls.__module__, name):
                        break
                else:
                    classes.append(cls)
        
        css_, js_ = create_css_and_js_from_model_classes(classes, css, js)
        
        # Store module name and sort
        self._module_names.append(module_name)
        self._module_names.sort(key=lambda x: -len(x))
        
        # Create cached assets
        fname = module_name.replace('.', '-')
        self._assets[fname + '.css'] = css_.encode()
        self._assets[fname + '.js'] = js_.encode()
    
    def export(self, dirname):
        """ Write all assets to the given directory.
        """
        # Normalize and check
        if dirname.startswith('~'):  # pragma: no cover
            dirname = os.path.expanduser(dirname)
        if not os.path.isdir(dirname):
            raise ValueError('dirname %r for export is not a directory.' % dirname)
        # Export all assets
        for fname in self.get_asset_names():
            if not fname.startswith('index-'):
                with open(os.path.join(dirname, fname), 'wb') as f:
                    f.write(self.load_asset(fname))

# Our singleton asset store
assets = AssetStore()


class SessionAssets:
    """ Provider for assets for a specific session. Inherited by Session.
    """
    
    def __init__(self, store=None):  # Allow custom store for testing
        self._store = store if (store is not None) else assets
        assert isinstance(self._store, AssetStore)
        self._asset_names = list()
        self._remote_asset_names = []  # e.g. JS and CSS to load from a CDN
        self._served = False
        self._known_classes = set()  # Cache what classes we know (for performance)
        self._extra_model_classes = []  # Model classes that are not in an asset/module
        self._id = get_random_string()
    
    @property
    def id(self):
        """ The unique identifier of this session.
        """
        return self._id
    
    def get_used_asset_names(self):
        """ Get a list of names of the assets used by this session, in
        the order that they were added.
        """
        return list(self._asset_names)  # Note: order matters
    
    def use_remote_asset(self, url):
        """ Make this session use a remote CSS/JS asset.
        
        Assets specified in this way will always be included as a link
        (even when exporting to a single-page app). These will typically
        be on-line resources (e.g. from a CDN), though can also be used
        for local files (as long as the app only runs locally).
        """
        if not isinstance(url, str):
            raise ValueError('Remote asset name must be a string.')
        if url not in self._remote_asset_names:
            self._remote_asset_names.append(url)
    
    def use_global_asset(self, fname, before=None):
        """ Make this session use a global asset.
        
        The given asset must be available in the global asset store
        (``app.assets``). JS and CSS assets are added/linked in the
        page index. It is ok to call this multiple times for the same
        asset.
        
        Parameters:
            fname (str): the (relative) filename for the asset.
            before (str, None): If given, places the new asset before the
                given asset.
        """
        if not isinstance(fname, str):
            raise ValueError('Asset name must be a string.')
        
        if fname in self._asset_names:
            return  # ok
        
        if fname not in self._store.get_asset_names():
            raise IndexError('Asset %r is not present in the store.' % fname)
        
        if self._served and (fname.endswith('.js') or fname.endswith('.css')):
            suffix = fname.split('.')[-1].upper()
            code = self._store.load_asset(fname).decode()
            self._send_command('DEFINE-%s %s' % (suffix, code))
            #logging.warn('Adding asset %r but the page was already "served".' % fname)
        
        if before:
            index = self._asset_names.index(before)
            self._asset_names.insert(index, fname)
        else:
            self._asset_names.append(fname)
    
    def add_asset(self, fname, content, before=None):
        """ Add an asset specific for this session.
        
        Assets are global to the process (stored in AssetStore
        ``app.assets``), which is why the ``fname`` is mangled with the
        session id.
        
        Parameters:
            fname (str): the (relative) filename for the asset.
            content (str, bytes): the content of the asset. If a str,
                it is interpreted as the filename or url to the asset.
                If bytes, it is interpreted as the raw asset content.
            before (str, None): If given, places the new asset before the
                given asset.
        Returns:
            fname (str): A mangled version of the given ``fname``.
        """
        if not isinstance(fname, str):
            raise ValueError('Asset name must be a string.')
        part1, dot, part2 = fname.rpartition('.')
        fname = '%s-%s%s%s' % (part1, self.id, dot, part2)
        self.add_global_asset(fname, content, before)
        return fname
    
    def add_global_asset(self, fname, content, before=None):
        """ Add an asset that is global to this process.
        
        Use this for JS and CSS, but probably not for images and content
        specific for a certain app. This is equivalent to
        ``app.assets.add_asset(fname, content)`` followed  by
        ``session.use_global_asset(fname)``. It's ok if the asset is already
        in the global assets, as long as it has the same content.
        """
        self._store.add_asset(fname, content)
        self.use_global_asset(fname, before)
    
    def register_model_class(self, cls):
        """ Ensure that the client knows the given class. A class can
        already be defined via a module asset, or we can add it to a
        pending list if the page has not been served yet. Otherwise it
        needs to be defined dynamically.
        """
        if not (isinstance(cls, type) and issubclass(cls, Model)):
            raise ValueError('Not a Model class')
        
        # Early exit if we know the class already
        if cls in self._known_classes:
            return
        
        # Make sure the base classes are registered first
        for cls2 in cls.mro()[1:]:
            if not issubclass(cls2, Model):  # True if cls2 is *the* Model class
                break
            if cls2 not in self._known_classes:
                self.register_model_class(cls2)
        
        # Make sure that no two models have the same name, or we get problems
        # that are difficult to debug.
        same_name = [c for c in self._known_classes if c.__name__ == cls.__name__]
        if same_name:
            same_name.append(cls)
            raise RuntimeError('Cannot have multiple Model classes with the '
                               'same name: %r' % same_name)
        
        logging.info('Registering Model class %r' % cls.__name__)
        self._known_classes.add(cls)
        
        # Check if cls is covered by our assets
        module_name = self._store.get_module_name_for_model_class(cls)
        if module_name:
            # cls is present in a module, add corresponding asset (overwrite ok)
            fname = module_name.replace('.', '-')
            if (fname + '.js') not in self._asset_names:
                self.use_global_asset(fname + '.css')
                self.use_global_asset(fname + '.js')
        elif not self._served:
            # Remember cls, will be served in the index
            self._extra_model_classes.append(cls)
        else:
            # Define class dynamically - assuming we're a session subclass ...
            logging.warn('Dynamically defining class %r' % cls)
            js, css = cls.JS.CODE, cls.CSS
            self._send_command('DEFINE-JS ' + js)
            if css.strip():
                self._send_command('DEFINE-CSS ' + css)
    
    def _get_js_and_css_assets(self, with_reset=False):
        """ Get an ordered dictionary with the JS and CSS assets.
        """
        # Create assets from our extra model classes
        if self._extra_model_classes:
            css, js = create_css_and_js_from_model_classes(self._extra_model_classes)
            self.add_asset('index-extra-model-classes.css', css.encode())
            self.add_asset('index-extra-model-classes.js', js.encode())
        self._extra_model_classes = None  # make sure we wont append to it anymore :)
        # Mark that any new assets dont make it into the currently served page
        self._served = True
        # Collect assets
        d = OrderedDict()
        if with_reset:
            fname = 'reset.css'
            d[fname] = self._store.load_asset(fname).decode()
        for fname in self.get_used_asset_names():
            if fname.endswith('.js') or fname.endswith('.css'):
                d[fname] = self._store.load_asset(fname).decode()
        return d
    
    def get_js_only(self):
        """ Get all JS assets as a single string. Intended for apps
        that make no use of CSS (like in Node).
        """
        js = []
        for fname, code in self._get_js_and_css_assets().items():
            if fname.endswith('.js'):
                js.append(code)
        return '\n\n'.join(js)
    
    def get_assets_as_html(self):
        """ Get a list of "<script>" and "<style>" html elements (as
        strings) representing the assets. No reset.css is included, nor
        any remote assets.
        """
        content_assets = []
        for fname, code in self._get_js_and_css_assets(False).items():
            if not code.strip():  # pragma: no cover
                continue
            elif fname.endswith('.css'):
                t = "<style>\n/* CSS for %s */\n%s\n</style>"
                content_assets.append(t % (fname, code))
            else:
                t = "<script>\n/* JS for %s */\n%s\n</script>"
                content_assets.append(t % (fname, code))
        return content_assets
    
    def get_page(self, single=False):
        """ Get the string for the HTML page to render this session's app.
        """
        return self._get_page(single)
    
    def get_page_for_export(self, commands, single=False):
        """ Get the string for an exported HTML page (to run without a server).
        """
        # Create lines to init app
        lines = []
        lines.append('flexx.is_exported = true;\n')
        lines.append('flexx.runExportedApp = function () {')
        lines.extend(['    flexx.command(%s);' % reprs(c) for c in commands])
        lines.append('};\n')
        
        # Create an extra asset for the export
        self.add_asset('index-export.js', '\n'.join(lines).encode())
        return self._get_page(single)
    
    def _get_page(self, single):
        """ This code takes the template, the collected JS and CSS, and
        composes an index page to serve/export.
        """
        # Init source code from template
        link_assets = []
        content_assets = []
        
        # Collect remote assets
        for url in self._remote_asset_names:
            if url.endswith('.css'):
                t = "    <link rel='stylesheet' type='text/css' href='%s' />"
                link_assets.append(t % url)
            else:
                t = "    <script src='%s'></script>"
                link_assets.append(t % url)
        
        # Collect JS and CSS
        for fname, code in self._get_js_and_css_assets(True).items():
            if not code.strip():  # pragma: no cover
                continue
            if single or fname.startswith('index-'):
                if fname.endswith('.css'):
                    t = "<style>\n/* CSS for %s */\n%s\n</style>"
                    content_assets.append(t % (fname, code))
                else:
                    t = "<script>\n/* JS for %s */\n%s\n</script>"
                    content_assets.append(t % (fname, code))
            else:
                if fname.endswith('.css'):
                    t = "    <link rel='stylesheet' type='text/css' href='%s' />"
                    link_assets.append(t % fname)
                else:
                    t = "    <script src='%s'></script>"
                    link_assets.append(t % fname)
        
        # Compose index page
        src = INDEX
        src = src.replace('ASSET-LINK-HOOK', '\n'.join(link_assets))
        src = src.replace('ASSET-CONTENT-HOOK', '\n'.join(content_assets))
        
        return src


# Use the system PRNG for session id generation (if possible)
# NOTE: secure random string generation implementation is adapted
#       from the Django project. 

def get_random_string(length=24, allowed_chars=None):
    """ Produce a securely generated random string.
    
    With a length of 12 with the a-z, A-Z, 0-9 character set returns
    a 71-bit value. log_2((26+26+10)^12) =~ 71 bits
    """
    allowed_chars = allowed_chars or ('abcdefghijklmnopqrstuvwxyz' +
                                      'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
    try:
        srandom = random.SystemRandom()
    except NotImplementedError:
        srandom = random
        logging.warn('Falling back to less secure Mersenne Twister random string.')
        bogus = "%s%s%s" % (random.getstate(), time.time(), 'sdkhfbsdkfbsdbhf')
        random.seed(hashlib.sha256(bogus.encode()).digest())

    return ''.join(srandom.choice(allowed_chars) for i in range(length))
