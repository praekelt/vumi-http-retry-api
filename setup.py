from setuptools import setup, find_packages

setup(
    name="vumi-http-retry-api",
    version="0.1.4",
    url='http://github.com/praekelt/vumi-http-retry-api',
    license='BSD',
    description="API for retrying HTTP requests",
    long_description=open('README.rst', 'r').read(),
    author='Praekelt Foundation',
    author_email='dev@praekeltfoundation.org',
    packages=find_packages() + ['twisted.plugins'],
    include_package_data=True,
    install_requires=[
        'klein',
        'treq',
        'confmodel',
        'PyYAML',
        'txredis',
        'jsonschema',
   ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Internet :: WWW/HTTP',
    ],
)
