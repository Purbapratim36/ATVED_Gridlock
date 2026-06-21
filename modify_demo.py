import sys
import os
import cv2

# We will modify demo_live_end_to_end to only run 5 frames and print outputs
with open(r"C:\Users\mahan\OneDrive\Documents\Desktop\Projects\Gridlock_sunny\demo_live_end_to_end.py", "r") as f:
    code = f.read()

code = code.replace("while True:", "for _ in range(5):")
code = code.replace("cv2.imshow", "# cv2.imshow")
code = code.replace("cv2.waitKey(1)", "ord('x')")

with open(r"C:\Users\mahan\OneDrive\Documents\Desktop\Projects\Gridlock_sunny\demo_live_end_to_end_test.py", "w") as f:
    f.write(code)
