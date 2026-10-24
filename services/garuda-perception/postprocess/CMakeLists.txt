# The plugin needs the Hailo headers and libhailo_postprocess_tools from the board SDK: cross-build only.
add_library(yolo26_post SHARED yolo26_post.cpp)
target_compile_options(yolo26_post PRIVATE -Wall -Wextra -ffp-contract=off)
target_include_directories(yolo26_post PRIVATE ${GARUDA_HAILO_INCLUDE})
target_link_libraries(yolo26_post PRIVATE garuda_perception_core hailo_postprocess_tools)
set_target_properties(yolo26_post PROPERTIES OUTPUT_NAME yolo26_post)
install(TARGETS yolo26_post LIBRARY DESTINATION lib)
