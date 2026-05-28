from setuptools import setup
import os
from glob import glob

package_name = 'yolo_web'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # 런치 파일을 설치 폴더로 복사하기 위한 설정
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='rokey',
    maintainer_email='rokey@todo.todo',
    description='YOLO Web Detection Package',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # '실행파일명 = 패키지명.파일명:메인함수'
            'fork_detect_a = yolo_web.fork_turck_detecting_multi_noresize_a:main',
            'fork_detect_b = yolo_web.fork_turck_detecting_multi_noresize_b:main',
            'truck_fork_classifer = yolo_web.truck_fork_classifer:main',
        ],
    },
)