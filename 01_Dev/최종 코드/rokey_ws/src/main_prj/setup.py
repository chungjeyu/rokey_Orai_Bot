from setuptools import find_packages, setup

package_name = 'main_prj'

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
        'abgui_goal_pose2_service = main_prj.abgui_goal_pose2_service:main',
        'abgui_goal_pose1 = main_prj.abgui_goal_pose1:main',
        ],
    },
)
