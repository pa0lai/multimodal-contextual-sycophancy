import base64
import io
import random
from PIL import Image, ImageEnhance, ImageFilter
from typing import Tuple, Optional
import numpy as np


class VisualAttacker:
    """
    Applies various visual attacks to images to test model robustness.
    """
    
    def load_image(self, image_path: str) -> Image.Image:
        """Load an image from path."""
        return Image.open(image_path).convert("RGB")

    def image_to_base64(self, img: Image.Image, format: str = "PNG", compress_for_api: bool = False) -> str:
        """
        Convert PIL Image to base64 string.
        
        Args:
            img: PIL Image object
            format: Output format (default PNG for consistency)
            compress_for_api: If True, resize large images and use JPEG to prevent API limits (for problematic cases)
        """
        buffer = io.BytesIO()
        
        if compress_for_api:
            # Resize if too large
            max_size = 1536
            w, h = img.size
            if max(w, h) > max_size:
                ratio = max_size / max(w, h)
                new_size = (int(w * ratio), int(h * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Ensure RGB mode for JPEG
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            img.save(buffer, format="JPEG", quality=85, optimize=True)
        else:
            img.save(buffer, format=format)
        
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    @staticmethod
    def base64_to_image(b64_string: str) -> Image.Image:
        """Convert base64 string to PIL Image."""
        img_data = base64.b64decode(b64_string)
        return Image.open(io.BytesIO(img_data)).convert("RGB")
    
    @staticmethod
    def apply_low_light(img: Image.Image, brightness_factor: float = 0.15) -> Image.Image:
        enhancer = ImageEnhance.Brightness(img)
        return enhancer.enhance(brightness_factor)
    
    @staticmethod
    def apply_overexposure(img: Image.Image, brightness_factor: float = 2.5) -> Image.Image:
        enhancer = ImageEnhance.Brightness(img)
        bright = enhancer.enhance(brightness_factor)
        contrast_enhancer = ImageEnhance.Contrast(bright)
        return contrast_enhancer.enhance(0.5)
    
    @staticmethod
    def apply_heavy_compression(img: Image.Image, quality: int = 5) -> Image.Image:
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality)
        buffer.seek(0)
        return Image.open(buffer).convert("RGB")
    
    @staticmethod
    def apply_pixelation(img: Image.Image, pixel_size: int = 16) -> Image.Image:
        original_size = img.size
        small_size = (max(1, original_size[0] // pixel_size), 
                      max(1, original_size[1] // pixel_size))
        small = img.resize(small_size, Image.Resampling.NEAREST)
        return small.resize(original_size, Image.Resampling.NEAREST)
    
    @staticmethod
    def apply_rain_effect(img: Image.Image, density: float = 0.02, drop_length: int = 20, drop_width: int = 2) -> Image.Image:
        img_array = np.array(img)
        h, w, _ = img_array.shape
        num_drops = int(h * w * density / (drop_length * drop_width))
        for _ in range(num_drops):
            x = random.randint(0, w - 1)
            y = random.randint(0, h - drop_length)
            for dy in range(drop_length):
                for dx in range(-drop_width // 2, drop_width // 2 + 1):
                    nx = min(max(x + dx, 0), w - 1)
                    ny = min(y + dy, h - 1)
                    alpha = 0.7
                    img_array[ny, nx] = (img_array[ny, nx] * (1 - alpha) + np.array([200, 200, 220]) * alpha).astype(np.uint8)
        return Image.fromarray(img_array)
    
    @staticmethod
    def apply_snow_effect(img: Image.Image, density: float = 0.05) -> Image.Image:
        img_array = np.array(img)
        h, w, _ = img_array.shape
        num_flakes = int(h * w * density)
        for _ in range(num_flakes):
            x = random.randint(0, w - 1)
            y = random.randint(0, h - 1)
            size = random.randint(2, 5)
            for dy in range(-size, size + 1):
                for dx in range(-size, size + 1):
                    if dx**2 + dy**2 <= size**2:
                        nx = min(max(x + dx, 0), w - 1)
                        ny = min(max(y + dy, 0), h - 1)
                        alpha = 0.8
                        img_array[ny, nx] = (img_array[ny, nx] * (1 - alpha) + np.array([255, 255, 255]) * alpha).astype(np.uint8)
        return Image.fromarray(img_array)
    
    @staticmethod
    def apply_spatter_effect(img: Image.Image, density: float = 0.03, color: Tuple[int, int, int] = (139, 69, 19)) -> Image.Image:
        img_array = np.array(img)
        h, w, _ = img_array.shape
        num_spots = int(h * w * density / 50)
        for _ in range(num_spots):
            x = random.randint(0, w - 1)
            y = random.randint(0, h - 1)
            size = random.randint(5, 20)
            for dy in range(-size, size + 1):
                for dx in range(-size, size + 1):
                    dist = (dx**2 + dy**2) ** 0.5
                    if dist <= size * (0.5 + random.random() * 0.5):
                        nx = min(max(x + dx, 0), w - 1)
                        ny = min(max(y + dy, 0), h - 1)
                        alpha = 0.6 + random.random() * 0.3
                        img_array[ny, nx] = (img_array[ny, nx] * (1 - alpha) + np.array(color) * alpha).astype(np.uint8)
        return Image.fromarray(img_array)
    
    @classmethod
    def get_attack_configs(cls) -> dict:
        return {
            "low_light_mild": {"func": cls.apply_low_light, "params": {"brightness_factor": 0.3}},
            "low_light_severe": {"func": cls.apply_low_light, "params": {"brightness_factor": 0.1}},
            "overexposure_mild": {"func": cls.apply_overexposure, "params": {"brightness_factor": 2.0}},
            "overexposure_severe": {"func": cls.apply_overexposure, "params": {"brightness_factor": 3.0}},
            "compression_mild": {"func": cls.apply_heavy_compression, "params": {"quality": 15}},
            "compression_severe": {"func": cls.apply_heavy_compression, "params": {"quality": 3}},
            "pixelation_mild": {"func": cls.apply_pixelation, "params": {"pixel_size": 8}},
            "pixelation_severe": {"func": cls.apply_pixelation, "params": {"pixel_size": 24}},
            "rain_mild": {"func": cls.apply_rain_effect, "params": {"density": 0.01}},
            "rain_severe": {"func": cls.apply_rain_effect, "params": {"density": 0.04}},
            "snow_mild": {"func": cls.apply_snow_effect, "params": {"density": 0.02}},
            "snow_severe": {"func": cls.apply_snow_effect, "params": {"density": 0.08}},
            "spatter_mild": {"func": cls.apply_spatter_effect, "params": {"density": 0.01}},
            "spatter_severe": {"func": cls.apply_spatter_effect, "params": {"density": 0.05}},
        }
    
    @classmethod
    def apply_attack(cls, img: Image.Image, attack_name: str) -> Image.Image:
        configs = cls.get_attack_configs()
        if attack_name not in configs:
            raise ValueError(f"Unknown attack: {attack_name}")
        config = configs[attack_name]
        return config["func"](img, **config["params"])
