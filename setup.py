from setuptools import setup, find_packages
from os import path
import codecs
import re


def read(*parts):
	here = path.abspath(path.dirname(__file__))
	with codecs.open(path.join(here, *parts), 'r') as fp:
		return fp.read()


def find_version():
	version_file = read("masabot", "version.py")
	version_match = re.search(r"^\s*__version__\s*=\s*['\"]([^'\"]*)['\"]\s*$", version_file, re.MULTILINE)

	if version_match:
		return version_match.group(1)
	else:
		raise RuntimeError("Unable to find version string")


setup(
	name='masabot',
	version=find_version(),
	description='Performs various secretarial tasks on Discord.',
	long_description=read('README.rst'),
	url='https://github.com/moe-serifu-circle/masabot',
	author='Rebecca Nelson',
	author_email='president@moeserifu.moe',
	classifiers=[
		'Programming Language :: Python :: 3'
	],
	keywords='discord',
	packages=find_packages(),
	install_requires=['discord.py'],
	tests_require=[],
	python_requires='>=3.5.*',
	entry_points={
		'console_scripts': [
			'masabot=masabot:run'
		]
	},
	package_data={
		'': ['readme.rst']
	},
	include_package_data=True
)