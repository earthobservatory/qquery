from setuptools import setup, find_packages
import qquery

setup(
    name='qquery',
    version=qquery.__version__,
    long_description=qquery.__description__,
    url=qquery.__url__,
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'redis'
    ]
)
