from distutils.command.install import install as _install
from distutils.core import setup
import gcinvoice


class install(_install):
    """Specialized Python installer.

    This installer does not run install_scripts.

    """
    sub_commands = [(x, y) for (x, y) in _install.sub_commands
                    if x != 'install_scripts']


setup(cmdclass={'install': install},
      name='gcinvoice',
      version=gcinvoice.__version__,
      author='Roman Bertle',
      author_email='bertle@smoerz.org',
      url='http://www.smoerz.org/gcinvoice',
      description='Parse Gnucash data and create invoices',
      long_description="""A module to parse Gnucash data and create invoices.

The module provides a class to parse Gnucash data files (only data relevant
for invoices is extracted), and to create invoices from templates. The module
can also be run as a script.
""",
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Environment :: Console',
          'Intended Audience :: End Users/Desktop',
          'Intended Audience :: Financial and Insurance Industry',
          'License :: OSI Approved :: Python Software Foundation License',
          'Programming Language :: Python',
          'Topic :: Office/Business :: Financial :: Accounting',
          ],
      py_modules=['gcinvoice', 'yaptu'],
      scripts=['gcinvoice.py'],
      )
