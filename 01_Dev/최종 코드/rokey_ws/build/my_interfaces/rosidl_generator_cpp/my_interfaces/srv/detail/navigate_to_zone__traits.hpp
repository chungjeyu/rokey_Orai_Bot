// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from my_interfaces:srv/NavigateToZone.idl
// generated code does not contain a copyright notice

#ifndef MY_INTERFACES__SRV__DETAIL__NAVIGATE_TO_ZONE__TRAITS_HPP_
#define MY_INTERFACES__SRV__DETAIL__NAVIGATE_TO_ZONE__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "my_interfaces/srv/detail/navigate_to_zone__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

namespace my_interfaces
{

namespace srv
{

inline void to_flow_style_yaml(
  const NavigateToZone_Request & msg,
  std::ostream & out)
{
  out << "{";
  // member: zone
  {
    out << "zone: ";
    rosidl_generator_traits::value_to_yaml(msg.zone, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const NavigateToZone_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: zone
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "zone: ";
    rosidl_generator_traits::value_to_yaml(msg.zone, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const NavigateToZone_Request & msg, bool use_flow_style = false)
{
  std::ostringstream out;
  if (use_flow_style) {
    to_flow_style_yaml(msg, out);
  } else {
    to_block_style_yaml(msg, out);
  }
  return out.str();
}

}  // namespace srv

}  // namespace my_interfaces

namespace rosidl_generator_traits
{

[[deprecated("use my_interfaces::srv::to_block_style_yaml() instead")]]
inline void to_yaml(
  const my_interfaces::srv::NavigateToZone_Request & msg,
  std::ostream & out, size_t indentation = 0)
{
  my_interfaces::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use my_interfaces::srv::to_yaml() instead")]]
inline std::string to_yaml(const my_interfaces::srv::NavigateToZone_Request & msg)
{
  return my_interfaces::srv::to_yaml(msg);
}

template<>
inline const char * data_type<my_interfaces::srv::NavigateToZone_Request>()
{
  return "my_interfaces::srv::NavigateToZone_Request";
}

template<>
inline const char * name<my_interfaces::srv::NavigateToZone_Request>()
{
  return "my_interfaces/srv/NavigateToZone_Request";
}

template<>
struct has_fixed_size<my_interfaces::srv::NavigateToZone_Request>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<my_interfaces::srv::NavigateToZone_Request>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<my_interfaces::srv::NavigateToZone_Request>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace my_interfaces
{

namespace srv
{

inline void to_flow_style_yaml(
  const NavigateToZone_Response & msg,
  std::ostream & out)
{
  out << "{";
  // member: success
  {
    out << "success: ";
    rosidl_generator_traits::value_to_yaml(msg.success, out);
    out << ", ";
  }

  // member: message
  {
    out << "message: ";
    rosidl_generator_traits::value_to_yaml(msg.message, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const NavigateToZone_Response & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: success
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "success: ";
    rosidl_generator_traits::value_to_yaml(msg.success, out);
    out << "\n";
  }

  // member: message
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "message: ";
    rosidl_generator_traits::value_to_yaml(msg.message, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const NavigateToZone_Response & msg, bool use_flow_style = false)
{
  std::ostringstream out;
  if (use_flow_style) {
    to_flow_style_yaml(msg, out);
  } else {
    to_block_style_yaml(msg, out);
  }
  return out.str();
}

}  // namespace srv

}  // namespace my_interfaces

namespace rosidl_generator_traits
{

[[deprecated("use my_interfaces::srv::to_block_style_yaml() instead")]]
inline void to_yaml(
  const my_interfaces::srv::NavigateToZone_Response & msg,
  std::ostream & out, size_t indentation = 0)
{
  my_interfaces::srv::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use my_interfaces::srv::to_yaml() instead")]]
inline std::string to_yaml(const my_interfaces::srv::NavigateToZone_Response & msg)
{
  return my_interfaces::srv::to_yaml(msg);
}

template<>
inline const char * data_type<my_interfaces::srv::NavigateToZone_Response>()
{
  return "my_interfaces::srv::NavigateToZone_Response";
}

template<>
inline const char * name<my_interfaces::srv::NavigateToZone_Response>()
{
  return "my_interfaces/srv/NavigateToZone_Response";
}

template<>
struct has_fixed_size<my_interfaces::srv::NavigateToZone_Response>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<my_interfaces::srv::NavigateToZone_Response>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<my_interfaces::srv::NavigateToZone_Response>
  : std::true_type {};

}  // namespace rosidl_generator_traits

namespace rosidl_generator_traits
{

template<>
inline const char * data_type<my_interfaces::srv::NavigateToZone>()
{
  return "my_interfaces::srv::NavigateToZone";
}

template<>
inline const char * name<my_interfaces::srv::NavigateToZone>()
{
  return "my_interfaces/srv/NavigateToZone";
}

template<>
struct has_fixed_size<my_interfaces::srv::NavigateToZone>
  : std::integral_constant<
    bool,
    has_fixed_size<my_interfaces::srv::NavigateToZone_Request>::value &&
    has_fixed_size<my_interfaces::srv::NavigateToZone_Response>::value
  >
{
};

template<>
struct has_bounded_size<my_interfaces::srv::NavigateToZone>
  : std::integral_constant<
    bool,
    has_bounded_size<my_interfaces::srv::NavigateToZone_Request>::value &&
    has_bounded_size<my_interfaces::srv::NavigateToZone_Response>::value
  >
{
};

template<>
struct is_service<my_interfaces::srv::NavigateToZone>
  : std::true_type
{
};

template<>
struct is_service_request<my_interfaces::srv::NavigateToZone_Request>
  : std::true_type
{
};

template<>
struct is_service_response<my_interfaces::srv::NavigateToZone_Response>
  : std::true_type
{
};

}  // namespace rosidl_generator_traits

#endif  // MY_INTERFACES__SRV__DETAIL__NAVIGATE_TO_ZONE__TRAITS_HPP_
