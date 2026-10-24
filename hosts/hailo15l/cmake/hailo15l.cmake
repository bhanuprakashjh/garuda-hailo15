# Include from a project CMakeLists.txt AFTER `source environment-setup-armv8a-poky-linux`.
# Fails fast if the SDK environment is not loaded, so a native build can never masquerade as a cross build.
if(NOT DEFINED ENV{OECORE_TARGET_SYSROOT})
  message(FATAL_ERROR "Hailo-15L SDK env not loaded: source <sdk>/environment-setup-armv8a-poky-linux first")
endif()
set(GARUDA_H15L_SYSROOT "$ENV{OECORE_TARGET_SYSROOT}")
list(APPEND CMAKE_PREFIX_PATH "${GARUDA_H15L_SYSROOT}/usr")
set(GARUDA_HAILO_INCLUDE "${GARUDA_H15L_SYSROOT}/usr/include/hailo")
