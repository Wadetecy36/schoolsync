import numpy as np
import json
import base64
import os

class FaceHandler:
    _detector = None
    _recognizer = None
    
    @classmethod
    def _get_models(cls):
        """Initialize the OpenCV models if not already loaded"""
        import cv2
        if cls._detector is None or cls._recognizer is None:
            # Paths to models
            base_path = os.path.dirname(os.path.abspath(__file__))
            det_model_path = os.path.join(base_path, 'static', 'models', 'face_detection_yunet_2023mar.onnx')
            rec_model_path = os.path.join(base_path, 'static', 'models', 'face_recognition_sface_2021dec.onnx')
            
            if not os.path.exists(det_model_path) or not os.path.exists(rec_model_path):
                print(f"Face models not found at {det_model_path} or {rec_model_path}")
                return None, None

            # Initialize detector with a dummy input size, will be updated per image
            # Lowered score threshold to 0.4 for better detection in various lighting/quality
            cls._detector = cv2.FaceDetectorYN.create(det_model_path, "", (320, 320), 0.4)
            cls._recognizer = cv2.FaceRecognizerSF.create(rec_model_path, "")
            
        return cls._detector, cls._recognizer

    @staticmethod
    def get_encoding(image_source):
        """
        Get face encoding using OpenCV SFace.
        Returns a list of 128 floats or None if no face is found.
        """
        try:
            import cv2
            img = None
            if not image_source:
                print("FaceHandler: Empty image source")
                return None

            if isinstance(image_source, str):
                if image_source.startswith("data:"):
                    # Handle base64 data URI
                    try:
                        header, encoded = image_source.split(",", 1)
                        image_data = base64.b64decode(encoded)
                        nparr = np.frombuffer(image_data, np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    except Exception as e:
                        print(f"FaceHandler: Failed to decode base64 image: {e}")
                        return None
                elif os.path.exists(image_source):
                    # Handle file path
                    img = cv2.imread(image_source)
                else:
                    # Try as a relative path from static/uploads if it's just a filename
                    base_path = os.path.dirname(os.path.abspath(__file__))
                    upload_path = os.path.join(base_path, 'static', 'uploads', image_source)
                    if os.path.exists(upload_path):
                        img = cv2.imread(upload_path)
                    else:
                        print(f"FaceHandler: File not found: {image_source}")
            elif isinstance(image_source, np.ndarray):
                img = image_source
            
            if img is None:
                return None

            detector, recognizer = FaceHandler._get_models()
            if detector is None:
                return None

            # Update detector input size
            h, w, _ = img.shape
            detector.setInputSize((w, h))
            
            # Detect faces
            _, faces = detector.detect(img)
            
            if faces is None or len(faces) == 0:
                # Try with a smaller input size if the image is large, sometimes helps YuNet
                if w > 640 or h > 640:
                    scale = 640.0 / max(w, h)
                    img_small = cv2.resize(img, (0,0), fx=scale, fy=scale)
                    detector.setInputSize((img_small.shape[1], img_small.shape[0]))
                    _, faces = detector.detect(img_small)
                    if faces is not None and len(faces) > 0:
                        # If found on small image, we need to use the small image for alignment
                        img = img_small

            if faces is not None and len(faces) > 0:
                # Use the first face found
                # Align and crop the face
                aligned_face = recognizer.alignCrop(img, faces[0])
                # Extract features
                feature = recognizer.feature(aligned_face)
                # Convert from [1, 128] numpy array to list
                return feature[0].tolist()

            print("FaceHandler: No faces detected in image")
            return None
        except Exception as e:
            print(f"Error extracting face encoding: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def find_match(known_encodings, target_encoding, threshold=None):
        """
        Find the best match for target_encoding among known_encodings.
        SFace usually works well with a cosine distance threshold around 0.36,
        but in practice this can be tuned based on how strict/lenient matching
        should be for your dataset and lighting conditions.
        """
        if not known_encodings or not target_encoding:
            return None

        # Threshold for SFace (Cosine Distance).
        # Higher values are more lenient (accept more matches).
        # Default is slightly relaxed from the paper value to better handle
        # real-world school photos and camera differences.
        if threshold is None:
            threshold = 0.55

        best_match = None
        min_dist = float('inf')

        target_vec = np.array(target_encoding)

        for item in known_encodings:
            known_vec = np.array(item['encoding'])
            
            # Calculate cosine distance
            try:
                # Norm of vectors
                norm_a = np.linalg.norm(target_vec)
                norm_b = np.linalg.norm(known_vec)
                if norm_a == 0 or norm_b == 0:
                    continue
                    
                cos_sim = np.dot(target_vec, known_vec) / (norm_a * norm_b)
                dist = 1 - cos_sim
                
                if dist < threshold and dist < min_dist:
                    min_dist = dist
                    best_match = {
                        'id': item['id'],
                        'distance': float(dist)
                    }
            except Exception as e:
                print(f"Comparison error: {e}")
                continue

        return best_match
