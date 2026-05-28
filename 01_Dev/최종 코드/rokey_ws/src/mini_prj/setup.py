from setuptools import find_packages, setup

package_name = 'mini_prj'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/start_nodes.launch.py']),
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
            'follow_waypoints = mini_prj.3_1_c_follow_waypoints:main',
            'node_a = mini_prj.node_a_nav:main',
            'node_a_nav_1 = mini_prj.node_a_nav_1:main',
            'node_a_nav_1_1 = mini_prj.node_a_nav_1_1:main',
            'node_a_nav_1_2 = mini_prj.node_a_nav_1_2:main',
            'node_a_nav_2_1 = mini_prj.node_a_nav_2_1:main',
            'node_a_nav_2_2 = mini_prj.node_a_nav_2_2:main',
            'node_a_nav_2_3 = mini_prj.node_a_nav_2_3:main',
            'node_a_nav_2_4 = mini_prj.node_a_nav_2_4:main',
            'node_b = mini_prj.node_b_3:main',
            'node_b_6 = mini_prj.node_b_6:main',
            'fake_c = mini_prj.fake_node_c:main',
            'node_c = mini_prj.node_c:main',
            'node_c_test = mini_prj.node_c_test:main',
            'node_c_test2 = mini_prj.node_c_test2:main',
            'node_c_8 = mini_prj.node_c_8:main',
            'depth_to_3d = mini_prj.depth_to_3d_ts:main',
        ],
    },
)
