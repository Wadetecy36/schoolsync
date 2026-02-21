import numpy as np
import json
import base64
import os
from flask import current_app

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
            # Lowered score threshold from 0.4 to 0.3 for better detection in low light/small faces
            cls._detector = cv2.FaceDetectorYN.create(det_model_path, "", (320, 320), 0.3)
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
            if image_source is None:
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
                        current_app.logger.error(f"FaceHandler: Failed to decode base64 image: {e}")
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
            
            # Helper to check if faces were found safely for numpy arrays
            def has_faces(f):
                return f is not None and isinstance(f, np.ndarray) and f.size > 0

            if not has_faces(faces):
                # Try with a smaller input size if the image is large, sometimes helps YuNet
                if w > 640 or h > 640:
                    scale = 640.0 / max(w, h)
                    img_small = cv2.resize(img, (0,0), fx=scale, fy=scale)
                    detector.setInputSize((img_small.shape[1], img_small.shape[0]))
                    _, faces_small = detector.detect(img_small)
                    if has_faces(faces_small):
                        faces = faces_small
                        img = img_small

            # Grayscale fallback
            if not has_faces(faces):
                img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                img_gray = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
                _, faces_gray = detector.detect(img_gray)
                if has_faces(faces_gray):
                    faces = faces_gray
                    img = img_gray

            if has_faces(faces):
                # Use the first face found
                # Align and crop the face
                aligned_face = recognizer.alignCrop(img, faces[0])
                # Extract features
                feature = recognizer.feature(aligned_face)
                # Convert from [1, 128] numpy array to list
                return feature[0].tolist()

            return None
        except Exception as e:
            if current_app:
                current_app.logger.error(f"Error extracting face encoding: {e}")
            return None

    @staticmethod
    def find_match(known_encodings, target_encoding, threshold=None):
        """
        Find the best match for target_encoding among known_encodings.
        SFace usually works well with a cosine distance threshold around 0.36.
        """
        if not known_encodings or not target_encoding:
            return None

        # Threshold for SFace (Cosine Distance)
        # Recommended is 0.363, setting to 0.45 for more leniency/similarity detection
        if threshold is None:
            threshold = 0.45

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
