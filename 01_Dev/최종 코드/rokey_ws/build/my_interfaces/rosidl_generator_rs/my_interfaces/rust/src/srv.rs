#[cfg(feature = "serde")]
use serde::{Deserialize, Serialize};




// Corresponds to my_interfaces__srv__NavigateToZone_Request

// This struct is not documented.
#[allow(missing_docs)]

#[allow(non_camel_case_types)]
#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]
#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct NavigateToZone_Request {

    // This member is not documented.
    #[allow(missing_docs)]
    pub zone: std::string::String,

}



impl Default for NavigateToZone_Request {
  fn default() -> Self {
    <Self as rosidl_runtime_rs::Message>::from_rmw_message(super::srv::rmw::NavigateToZone_Request::default())
  }
}

impl rosidl_runtime_rs::Message for NavigateToZone_Request {
  type RmwMsg = super::srv::rmw::NavigateToZone_Request;

  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> {
    match msg_cow {
      std::borrow::Cow::Owned(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
        zone: msg.zone.as_str().into(),
      }),
      std::borrow::Cow::Borrowed(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
        zone: msg.zone.as_str().into(),
      })
    }
  }

  fn from_rmw_message(msg: Self::RmwMsg) -> Self {
    Self {
      zone: msg.zone.to_string(),
    }
  }
}


// Corresponds to my_interfaces__srv__NavigateToZone_Response

// This struct is not documented.
#[allow(missing_docs)]

#[allow(non_camel_case_types)]
#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]
#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct NavigateToZone_Response {

    // This member is not documented.
    #[allow(missing_docs)]
    pub success: bool,


    // This member is not documented.
    #[allow(missing_docs)]
    pub message: std::string::String,

}



impl Default for NavigateToZone_Response {
  fn default() -> Self {
    <Self as rosidl_runtime_rs::Message>::from_rmw_message(super::srv::rmw::NavigateToZone_Response::default())
  }
}

impl rosidl_runtime_rs::Message for NavigateToZone_Response {
  type RmwMsg = super::srv::rmw::NavigateToZone_Response;

  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> {
    match msg_cow {
      std::borrow::Cow::Owned(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
        success: msg.success,
        message: msg.message.as_str().into(),
      }),
      std::borrow::Cow::Borrowed(msg) => std::borrow::Cow::Owned(Self::RmwMsg {
      success: msg.success,
        message: msg.message.as_str().into(),
      })
    }
  }

  fn from_rmw_message(msg: Self::RmwMsg) -> Self {
    Self {
      success: msg.success,
      message: msg.message.to_string(),
    }
  }
}






#[link(name = "my_interfaces__rosidl_typesupport_c")]
extern "C" {
    fn rosidl_typesupport_c__get_service_type_support_handle__my_interfaces__srv__NavigateToZone() -> *const std::ffi::c_void;
}

// Corresponds to my_interfaces__srv__NavigateToZone
#[allow(missing_docs, non_camel_case_types)]
pub struct NavigateToZone;

impl rosidl_runtime_rs::Service for NavigateToZone {
    type Request = NavigateToZone_Request;
    type Response = NavigateToZone_Response;

    fn get_type_support() -> *const std::ffi::c_void {
        // SAFETY: No preconditions for this function.
        unsafe { rosidl_typesupport_c__get_service_type_support_handle__my_interfaces__srv__NavigateToZone() }
    }
}


