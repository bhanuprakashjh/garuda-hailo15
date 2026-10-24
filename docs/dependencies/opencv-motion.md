# OpenCV camera-motion dependency

The optional `GARUDA_TRACKING_OPENCV` plugin uses OpenCV core, imgproc, features2d and
calib3d for ORB descriptors, mutual ratio matching and RANSAC similarity estimation.
This is background-motion compensation, not a learned
object-identity tracker, depth source or VIO implementation.

Upstream OpenCV 4.5.5 source is Apache-2.0:
https://github.com/opencv/opencv/blob/4.5.5/LICENSE

Primary API references:

- https://docs.opencv.org/4.5.5/d1/d89/tutorial_py_orb.html
- https://docs.opencv.org/4.5.5/d9/d0c/group__calib3d.html

The Hailo SDK supplies 4.5.5 headers/libraries. The factory board already supplies
core/imgproc/calib3d/features2d/flann 4.5.5. These factory libraries are reused; no
system package, additional inference engine, shared library or boot setting is installed.
Native development tests use the installed OpenCV 4.6.0 and ARM tests use 4.5.5;
native results alone are not evidence of target behavior.

The disabled recipe skeleton records the dependency for the product port. It is
not a substitute for the existing vendor image's complete third-party notices/SBOM.
No pretrained weights are introduced by this plugin. The default tracking core and
translation backend build without OpenCV.
