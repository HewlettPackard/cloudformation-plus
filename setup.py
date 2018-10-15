#!/usr/bin/env python

'''
distutils/setuptools install script.
'''

from setuptools import setup, find_packages

setup(
    name='cloudformation-plus',
    version='1.0-pr1',
    description='A library that reduces the amount of code you must write in order to deploy non-trivial applications to AWS CloudFormation',
    long_description=open('README.md').read(),
    url='https://github.com/HewlettPackard/cloudformation-plus',
    author='Hewlett Packard Enterprise',
    author_email='charles.shearer@hpe.com',
    license='Apache License 2.0',
    packages=['cfnplus'],
    install_requires=[
        'boto3>=1.9,<2',
        'pyyaml',
    ],
    tests_require=[
        'pytest',
    ],
    classifiers=[
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Natural Language :: English',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
    ],
)
