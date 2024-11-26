#!/usr/bin/env python
from distutils.core import setup
from os.path import join, dirname, abspath

CURDIR = dirname(abspath(__file__))
filename=join(CURDIR, 'src', 'Rammbock', 'version.py')
exec(compile(open(filename, "rb").read(), filename, 'exec'))

setup(name         = 'robotframework-rammbock',
      version      = VERSION,
      description  = 'Protocol testing library for Robot Framework',
      author       = 'Robot Framework Developers',
      author_email = 'robotframework-users@googlegroups.com',
      url          = 'http://github.com/robotframework/Rammbock/',
      package_dir  = {'' : 'src'},
      packages     = ['Rammbock', 'Rammbock.templates'],
      long_description = open(join(CURDIR, 'README.rst')).read()
      )
