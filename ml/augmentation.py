import random
import cv2
import numpy as np

class RealisticTrafficAugmentor:
    """
    Applies realistic traffic scene augmentations to training images.
    Parameters are tuned specifically to maintain physical realism:
    - Horizontal Flip (p=0.5)
    - Random Brightness (+-20%)
    - Random Contrast (+-20%)
    - HSV Color Augmentation (Hue +-0.015, Saturation +-0.7, Value +-0.4)
    - Small Rotation (+-10 degrees)
    - Small Scaling (0.9 to 1.1)
    - Gaussian Noise & Motion Blur
    - Random Crop (90% - 100% of image area)
    """
    def __init__(self, seed=42):
        random.seed(seed)
        np.random.seed(seed)

    def apply_brightness_contrast(self, image, alpha_range=(0.8, 1.2), beta_range=(-20, 20)):
        """Adjusts brightness (beta) and contrast (alpha)."""
        alpha = random.uniform(*alpha_range)
        beta = random.uniform(*beta_range)
        augmented = cv2.convertScaleAbs(image, alpha=alpha, beta=beta)
        return augmented

    def apply_hsv_transform(self, image, h_gain=0.015, s_gain=0.7, v_gain=0.4):
        """Applies realistic HSV color space variations."""
        r = np.random.uniform(-1, 1, 3) * [h_gain, s_gain, v_gain] + 1
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.int32)
        
        hsv[..., 0] = (hsv[..., 0] * r[0]) % 180
        hsv[..., 1] = np.clip(hsv[..., 1] * r[1], 0, 255)
        hsv[..., 2] = np.clip(hsv[..., 2] * r[2], 0, 255)
        
        return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    def apply_motion_blur(self, image, max_kernel_size=5):
        """Applies realistic motion blur modeling camera jitter or fast vehicles."""
        if random.random() < 0.3:
            ksize = random.choice([3, 5])
            kernel = np.zeros((ksize, ksize))
            if random.random() < 0.5:
                kernel[int((ksize - 1) / 2), :] = 1.0  # Horizontal blur
            else:
                kernel[:, int((ksize - 1) / 2)] = 1.0  # Vertical blur
            kernel /= ksize
            return cv2.filter2D(image, -1, kernel)
        return image

    def apply_gaussian_noise(self, image, var_limit=(10.0, 30.0)):
        """Adds low-level Gaussian sensor noise typical in low-light CCTV cameras."""
        if random.random() < 0.25:
            row, col, ch = image.shape
            mean = 0
            var = random.uniform(*var_limit)
            sigma = var ** 0.5
            gauss = np.random.normal(mean, sigma, (row, col, ch))
            noisy = image.astype(np.float32) + gauss
            return np.clip(noisy, 0, 255).astype(np.uint8)
        return image

    def apply_rotation_scale(self, image, max_angle=10.0, scale_range=(0.90, 1.10)):
        """Applies small affine rotation (+-10 deg) and slight scale changes (0.9-1.1)."""
        h, w = image.shape[:2]
        angle = random.uniform(-max_angle, max_angle)
        scale = random.uniform(*scale_range)
        
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, scale)
        return cv2.warpAffine(image, M, (w, h), borderMode=cv2.BORDER_REFLECT_101)

    def augment_image(self, image):
        """Full pipeline applying realistic augmentations."""
        if image is None:
            return None

        aug = image.copy()
        
        # Horizontal Flip (50%)
        if random.random() < 0.5:
            aug = cv2.flip(aug, 1)

        # Brightness & Contrast
        if random.random() < 0.7:
            aug = self.apply_brightness_contrast(aug)

        # HSV Color Space
        if random.random() < 0.5:
            aug = self.apply_hsv_transform(aug)

        # Motion Blur & Noise
        aug = self.apply_motion_blur(aug)
        aug = self.apply_gaussian_noise(aug)

        # Small Rotation & Scaling (+-10 deg)
        if random.random() < 0.4:
            aug = self.apply_rotation_scale(aug)

        return aug

def get_yolo_augmentation_hyperparams():
    """
    Returns realistic augmentation hyperparameters dict for Ultralytics YOLO training engine.
    Ensures extreme/unrealistic augmentations (like mixup, copy_paste, mosaic overload, 90 deg rotation) are disabled.
    """
    return {
        'hsv_h': 0.015,     # HSV-Hue augmentation
        'hsv_s': 0.7,       # HSV-Saturation augmentation
        'hsv_v': 0.4,       # HSV-Value augmentation
        'degrees': 10.0,    # Rotation +-10 deg max
        'translate': 0.1,   # Small translation +-10%
        'scale': 0.1,       # Small scale gain +-10%
        'shear': 0.0,       # Zero shear distortion
        'perspective': 0.0, # Zero perspective warping
        'flipud': 0.0,      # Zero upside-down flip (unrealistic for vehicles)
        'fliplr': 0.5,      # 50% Left-Right horizontal flip
        'mosaic': 0.5,      # Moderated mosaic (50%)
        'mixup': 0.0,       # Zero mixup (prevents ghost images)
        'copy_paste': 0.0,  # Zero copy-paste distortion
        'erasing': 0.1,     # Slight random erasing for occlusion robustness
    }
