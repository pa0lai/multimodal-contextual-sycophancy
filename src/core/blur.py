import io
import base64
from PIL import Image, ImageFilter

def apply_blur_in_memory(image_path: str, level: float) -> str:
    """
    Applies Gaussian blur to an image and returns the base64 encoded string.
    
    Args:
        image_path: Path to the image file.
        level: Radius of the Gaussian blur. 0 means no blur.
        
    Returns:
        Base64 encoded string of the processed image (JPEG format).
    """
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            
            if level > 0:
                img = img.filter(ImageFilter.GaussianBlur(radius=level))
            
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{img_str}"
            
    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        raise e
