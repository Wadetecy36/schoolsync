from face_handler import FaceHandler
import numpy as np
import cv2
import os

def test_face_handler():
    print("Testing FaceHandler...")
    
    # Check models
    detector, recognizer = FaceHandler._get_models()
    if detector is None:
        print("FAIL: Models could not be loaded!")
        return
    else:
        print("SUCCESS: Models loaded.")
    
    # Create a dummy image with a white circle (simplest shape)
    # This won't find a face but will test if the detector.detect call works
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.circle(img, (320, 240), 100, (255, 255, 255), -1)
    
    print("Testing detection call...")
    try:
        encoding = FaceHandler.get_encoding(img)
        print(f"Call finished. Encoding found: {encoding is not None}")
    except Exception as e:
        print(f"FAIL: Exception during get_encoding: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_face_handler()
