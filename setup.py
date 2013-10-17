from setuptools import setup, find_packages


setup(
    name="django-vidscraper",
    version='dev',
    maintainer='Participatory Culture Foundation',
    maintainer_email='support@pculture.org',
    url='https://github.com/pculture/django-vidscraper',
    license='BSD',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'vidscraper>1.0.0',
    ],
    classifiers=(
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Multimedia :: Sound/Audio',
        'Topic :: Multimedia :: Video',
    ),
)
