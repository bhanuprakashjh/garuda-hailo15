add_executable(test_scaffold test_scaffold.cpp)
target_link_libraries(test_scaffold PRIVATE garuda_perception_core)
add_test(NAME scaffold COMMAND test_scaffold)

add_executable(test_snapshot test_snapshot.cpp)
target_link_libraries(test_snapshot PRIVATE garuda_perception_core)
add_test(NAME snapshot COMMAND test_snapshot ${CMAKE_CURRENT_SOURCE_DIR}/golden/snapshot_v2.json)

add_executable(test_feed_server test_feed_server.cpp)
target_link_libraries(test_feed_server PRIVATE garuda_perception_core pthread)
add_test(NAME feed_server COMMAND test_feed_server)

add_executable(test_jpeg_encoder test_jpeg_encoder.cpp)
target_link_libraries(test_jpeg_encoder PRIVATE garuda_perception_core)
add_test(NAME jpeg_encoder COMMAND test_jpeg_encoder)

add_executable(test_bytetrack test_bytetrack.cpp)
target_link_libraries(test_bytetrack PRIVATE garuda_perception_core)
add_test(NAME bytetrack COMMAND test_bytetrack ${CMAKE_CURRENT_SOURCE_DIR}/golden/track_scenario.json ${CMAKE_CURRENT_SOURCE_DIR}/golden/track_golden.json)

add_executable(test_lock test_lock.cpp)
target_link_libraries(test_lock PRIVATE garuda_perception_core)
add_test(NAME lock COMMAND test_lock ${CMAKE_CURRENT_SOURCE_DIR}/golden/track_scenario.json ${CMAKE_CURRENT_SOURCE_DIR}/golden/track_golden.json)

add_executable(test_lock_core test_lock_core.cpp)
target_link_libraries(test_lock_core PRIVATE garuda_perception_core)
add_test(NAME lock_core COMMAND test_lock_core)

# Replay of the real run-5 (routine 1) capture through LockCore — on-board fix round 3, Ruling 19.5.
add_executable(test_lock_replay test_lock_replay.cpp)
target_link_libraries(test_lock_replay PRIVATE garuda_perception_core)
add_test(NAME lock_replay COMMAND test_lock_replay ${CMAKE_CURRENT_SOURCE_DIR}/fixtures/lock_replay_routine1.json)

# Replay of the real run-7 (routine 2, occlusion behind a chair) capture — on-board fix round 4,
# Ruling 20d.
add_executable(test_lock_replay2 test_lock_replay2.cpp)
target_link_libraries(test_lock_replay2 PRIVATE garuda_perception_core)
add_test(NAME lock_replay2 COMMAND test_lock_replay2 ${CMAKE_CURRENT_SOURCE_DIR}/fixtures/lock_replay_routine2.json)

# Replay of the real run-10e (routine 5, the phone routine) capture — on-board fix round 5,
# Ruling 22.5.
add_executable(test_lock_replay_phone test_lock_replay_phone.cpp)
target_link_libraries(test_lock_replay_phone PRIVATE garuda_perception_core)
add_test(NAME lock_replay_phone COMMAND test_lock_replay_phone ${CMAKE_CURRENT_SOURCE_DIR}/fixtures/lock_replay_phone.json)

add_executable(test_hailo_track_adapter test_hailo_track_adapter.cpp)
target_link_libraries(test_hailo_track_adapter PRIVATE garuda_perception_core)
add_test(NAME hailo_track_adapter COMMAND test_hailo_track_adapter)

add_executable(test_yolo26_decode test_yolo26_decode.cpp)
target_link_libraries(test_yolo26_decode PRIVATE garuda_perception_core)
add_test(NAME yolo26_decode COMMAND test_yolo26_decode ${CMAKE_CURRENT_SOURCE_DIR}/golden/yolo26_golden.json)

add_executable(test_yolo26_real test_yolo26_real.cpp)
target_link_libraries(test_yolo26_real PRIVATE garuda_perception_core)
add_test(NAME yolo26_real COMMAND test_yolo26_real ${CMAKE_CURRENT_SOURCE_DIR}/golden/yolo26_real_frame.json ${CMAKE_CURRENT_SOURCE_DIR}/golden/yolo26_real_frame.bin)

# Config-contract test: the two committed configs (config/yolo26_post.json, config/perception.json)
# and the M2 media-library profile agree with each other and with the compiled-in COCO table.
add_executable(test_yolo26_config test_yolo26_config.cpp)
target_link_libraries(test_yolo26_config PRIVATE garuda_perception_core)
add_test(NAME yolo26_config COMMAND test_yolo26_config
         ${CMAKE_CURRENT_SOURCE_DIR}/../config/yolo26_post.json
         ${CMAKE_CURRENT_SOURCE_DIR}/../config/perception.json
         ${CMAKE_CURRENT_SOURCE_DIR}/../../../hosts/hailo15l/medialib/profile/application_settings.json)
