# pip install setuptools wheel
# python setup.py bdist_wheel


from setuptools import setup, find_packages

setup(
    name='AACE_DataLake_Common', #needs to build fabric
    version='0.0.6',
    url='https://www.itsalljustdata.com',
    author='Jonathan Mills',  
    author_email='jon@itsalljustdata.com',
    description='Utilities for AACE Data Lake',
    # packages=find_packages(),  
    # install_requires=[],
)