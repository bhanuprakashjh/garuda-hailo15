import sys

import numpy as np

if len(sys.argv) != 2:
    sys.exit("usage: inspect_lbdump.py <path-to-lbdump.nv12>")
path = sys.argv[1]
W = H = 640
fsz = W * H * 3 // 2
data = np.fromfile(path, dtype=np.uint8)
n = len(data) // fsz
print("frames", n)
for i in (30, 120, 240):
    y = data[i * fsz:i * fsz + W * H].reshape(H, W)
    print(i, "Y mean content rows 140-499: %.1f, padding row0: %d, min/max content %d/%d" % (
        y[140:500].mean(), y[0].max(), y[140:500].min(), y[140:500].max()))
