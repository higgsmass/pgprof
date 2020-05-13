import os
import glob
from setuptools import setup, find_packages

def read(descfile):
    return open( os.path.join ( os.path.dirname(__file__), descfile)).read()

def datafiles(source_files):
    return glob.glob( os.path.join ( os.path.dirname(__file__), source_files))

setup(
    name='pgprof',

    version='1.0',

    author='Venkat Kaushik',

    author_email='higgsmass@github.com',

    maintainer='Venkat Kaushik',

    maintainer_email='higgsmass@github.com',

    url='https://github.com/higgsmass/pgprof.git',

    description= ('multi-threaded, connection pooled CRUD-ops benchmarking app for postgres cluster') ,

    long_description = read('README.md'),

    platforms="platform-independent",

    license='MIT',

    packages=find_packages('.'),

    package_dir={ '':'.' },

    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7',
        'Topic :: Text Processing :: Linguistic',
    ],

    install_requires = [
        'psycopg2 >= 2.8.5',
        'python-lorem >= 1.1.2',
    ],

    setup_requires = [
        'psycopg2 >= 2.8.5',
        'python-lorem >= 1.1.2',
    ],

    #test_suite='nose.collector',
    #tests_require=['nose'],

    entry_points = {
        'console_scripts': ['pgprof-start=pgprof.command_line:main'],
    },

    scripts=[
        'pgprof/benchpg',
    ],

    data_files= [ ('pgprof', datafiles('pgprof/*.sql'))],

    zip_safe=False,
    include_package_data=True,

)
