from setuptools import find_packages, setup

package_name = 'main_2'

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
        # 'test_pub = main_2.test_pub:main',
        # 'test_sub = main_2.test_sub:main',
        'follower_node = main_2.02_follower:main',
        'follower_node3 = main_2.03_follower:main',
        'follower_node12 = main_2.12_follower:main',
        'leader_node = main_2.02_leader:main',
        'leader_node6 = main_2.06_leader:main',
        'leader_node5 = main_2.05_leader:main',
        'leader_node7 = main_2.07_leader:main',
        'leader_node8 = main_2.08_leader:main',
        'leader_node11 = main_2.11_leader:main',
        'leader_node13 = main_2.13_leader:main',
        'leader_node14 = main_2.14_leader:main',
        'leader_node16 = main_2.16_leader:main',
        'leader_node17 = main_2.17_leader:main',
        'leader_node25 = main_2.25_leader:main',
        'executor_node_17 = main_2.event_yolo_detect_17:main',
        ],
    },
)
