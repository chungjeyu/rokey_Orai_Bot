from setuptools import setup

package_name = 'miniproject'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='seonghojin',
    maintainer_email='todlfrl123@gmail.com',
    description='Navigation service server package',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'gui_nav_server = miniproject.gui_nav_server:main',
        ],
    },
)
