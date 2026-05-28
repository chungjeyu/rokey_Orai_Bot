// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from my_interfaces:msg/Detection.idl
// generated code does not contain a copyright notice

#ifndef MY_INTERFACES__MSG__DETAIL__DETECTION__STRUCT_H_
#define MY_INTERFACES__MSG__DETAIL__DETECTION__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

// Include directives for member types
// Member 'label'
#include "rosidl_runtime_c/string.h"

/// Struct defined in msg/Detection in the package my_interfaces.
typedef struct my_interfaces__msg__Detection
{
  float confidence;
  rosidl_runtime_c__String label;
} my_interfaces__msg__Detection;

// Struct for a sequence of my_interfaces__msg__Detection.
typedef struct my_interfaces__msg__Detection__Sequence
{
  my_interfaces__msg__Detection * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} my_interfaces__msg__Detection__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // MY_INTERFACES__MSG__DETAIL__DETECTION__STRUCT_H_
