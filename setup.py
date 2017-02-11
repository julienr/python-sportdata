from setuptools import setup, find_packages

__version__ = '0.1.0'

setup(
    name='python-sportdata',
    version=__version__,
    author='Julien Rebetez',
    author_email='julien@fhtagn.net',
    packages=find_packages(),
    install_requires=[
        'lxml',
        'dateutils',
        'numpy',
    ]
)
