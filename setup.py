import codecs
from setuptools import setup, find_packages

VERSION = '0.0.0'

entry_points = {
    "z3c.autoinclude.plugin": [
		'target = nti.app',
	],
}

setup(
	name='nti.app.analytics_registration',
	version=VERSION,
	author='Josh Zuech',
	author_email='josh.zuech@nextthought.com',
	description="NTI App Analytics Registration",
	long_description=codecs.open('README.rst', encoding='utf-8').read(),
	license='Proprietary',
	keywords='pyramid preference',
	classifiers=[
		'Intended Audience :: Developers',
		'Natural Language :: English',
		'Programming Language :: Python :: 2.7',
		'Programming Language :: Python :: 3',
		'Programming Language :: Python :: 3.3',
	],
	packages=find_packages('src'),
	package_dir={'': 'src'},
	namespace_packages=['nti', 'nti.app'],
	install_requires=[
		'setuptools',
		'nti.analytics_registration',
		'nti.app.analytics'
	],
	entry_points=entry_points
)
