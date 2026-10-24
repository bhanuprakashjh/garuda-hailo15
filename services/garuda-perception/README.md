# garuda-perception

Real-time perception node for the Garuda SDK, running on Hailo-15L (or simulated with x86 native tests). Integrates object detection, depth estimation, and multi-object tracking. See [the perception node spec](../../../docs/superpowers/specs/) for architecture and dataflow.

## Native Tests (x86)

Build and run unit tests:

```bash
cd services/garuda-perception
cmake -B build-x86 -G Ninja
cmake --build build-x86
ctest --test-dir build-x86 --output-on-failure
```

## Cross Build (Hailo-15L)

Build the on-board pipeline (requires Hailo-15L SDK environment):

```bash
source /media/bhanu1234/Development/hailo15/sdk/environment-setup-armv8a-poky-linux
cd services/garuda-perception && cmake -B build-h15l -G Ninja -DGARUDA_BUILD_NODE=ON -DGARUDA_BUILD_TESTS=OFF -DCMAKE_TOOLCHAIN_FILE=$OECORE_NATIVE_SYSROOT/usr/share/cmake/OEToolchainConfig.cmake && cmake --build build-h15l
```

## Deployment

Deploy to the Hailo-15L device via:

```bash
./hosts/hailo15l/deploy.sh
```
