from setuptools import find_packages, setup

package_name = 'day3'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='rokey',
    maintainer_email='eycho96@gmail.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'nav_to_poses = day3.3_1_a_nav_to_pose:main',
            'nav_through_poses = day3.3_1_b_nav_through_poses:main',
            'follow_waypoints = day3.3_1_c_follow_waypoints:main',
        ],
    },
)
