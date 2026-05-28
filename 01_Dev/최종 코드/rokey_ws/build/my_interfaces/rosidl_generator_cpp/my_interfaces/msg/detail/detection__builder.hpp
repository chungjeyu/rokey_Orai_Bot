// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from my_interfaces:msg/Detection.idl
// generated code does not contain a copyright notice

#ifndef MY_INTERFACES__MSG__DETAIL__DETECTION__BUILDER_HPP_
#define MY_INTERFACES__MSG__DETAIL__DETECTION__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "my_interfaces/msg/detail/detection__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace my_interfaces
{

namespace msg
{

namespace builder
{

class Init_Detection_label
{
public:
  explicit Init_Detection_label(::my_interfaces::msg::Detection & msg)
  : msg_(msg)
  {}
  ::my_interfaces::msg::Detection label(::my_interfaces::msg::Detection::_label_type arg)
  {
    msg_.label = std::move(arg);
    return std::move(msg_);
  }

private:
  ::my_interfaces::msg::Detection msg_;
};

class Init_Detection_confidence
{
public:
  Init_Detection_confidence()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_Detection_label confidence(::my_interfaces::msg::Detection::_confidence_type arg)
  {
    msg_.confidence = std::move(arg);
    return Init_Detection_label(msg_);
  }

private:
  ::my_interfaces::msg::Detection msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::my_interfaces::msg::Detection>()
{
  return my_interfaces::msg::builder::Init_Detection_confidence();
}

}  // namespace my_interfaces

#endif  // MY_INTERFACES__MSG__DETAIL__DETECTION__BUILDER_HPP_
