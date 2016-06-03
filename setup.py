import setuptools

setuptools.setup(
    name='cloudify-occi-plugin',
    version='1.0.0',
    author='Vlastimil Holer',
    author_email='holer@ics.muni.cz',
    packages=['cloudify_occi_plugin'],
    license='LICENSE',
    description='Cloudify OCCI plugin',
    install_requires=[
        'cloudify-plugins-common>=3.3.1',
    ],
)
