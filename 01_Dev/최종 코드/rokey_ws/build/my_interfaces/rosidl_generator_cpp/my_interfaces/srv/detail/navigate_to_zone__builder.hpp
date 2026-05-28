// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from my_interfaces:srv/NavigateToZone.idl
// generated code does not contain a copyright notice

#ifndef MY_INTERFACES__SRV__DETAIL__NAVIGATE_TO_ZONE__BUILDER_HPP_
#define MY_INTERFACES__SRV__DETAIL__NAVIGATE_TO_ZONE__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "my_interfaces/srv/detail/navigate_to_zone__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace my_interfaces
{

namespace srv
{

namespace builder
{

class Init_NavigateToZone_Request_zone
{
public:
  Init_NavigateToZone_Request_zone()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  ::my_interfaces::srv::NavigateToZone_Request zone(::my_interfaces::srv::NavigateToZone_Request::_zone_type arg)
  {
    msg_.zone = std::move(arg);
    return std::move(msg_);
  }

private:
  ::my_interfaces::srv::NavigateToZone_Request msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::my_interfaces::srv::NavigateToZone_Request>()
{
  return my_interfaces::srv::builder::Init_NavigateToZone_Request_zone();
}

}  // namespace my_interfaces


namespace my_interfaces
{

namespace srv
{

namespace builder
{

class Init_NavigateToZone_Response_message
{
public:
  explicit Init_NavigateToZone_Response_message(::my_interfaces::srv::NavigateToZone_Response & msg)
  : msg_(msg)
  {}
  ::my_interfaces::srv::NavigateToZone_Response message(::my_interfaces::srv::NavigateToZone_Response::_message_type arg)
  {
    msg_.message = std::move(arg);
    return std::move(msg_);
  }

private:
  ::my_interfaces::srv::NavigateToZone_Response msg_;
};

class Init_NavigateToZone_Response_success
{
public:
  Init_NavigateToZone_Response_success()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_NavigateToZone_Response_message success(::my_interfaces::srv::NavigateToZone_Response::_success_type arg)
  {
    msg_.success = std::move(arg);
    return Init_NavigateToZone_Response_message(msg_);
  }

private:
  ::my_interfaces::srv::NavigateToZone_Response msg_;
};

}  // namespace builder

}  // namespace srv

template<typename MessageType>
auto build();

template<>
inline
auto build<::my_interfaces::srv::NavigateToZone_Response>()
{
  return my_interfaces::srv::builder::Init_NavigateToZone_Response_success();
}

}  // namespace my_interfaces

#endif  // MY_INTERFACES__SRV__DETAIL__NAVIGATE_TO_ZONE__BUILDER_HPP_
