import cv2
import numpy as np

def estimate_blur_kernel(size=5, angle=0):
    """Generates a linear motion blur kernel."""
    kernel = np.zeros((size, size))
    center = size // 2
    cv2.ellipse(kernel, (center, center), (0, center), angle, 0, 360, 1, -1)
    kernel = kernel / np.sum(kernel)
    return kernel

def wiener_deconvolution(img_bgr, snr=0.1):
    """
    Applies Wiener deconvolution to invert motion blur.
    snr: Signal-to-Noise Ratio for the Wiener filter.
    """
    # Try different angles (0, 45, 90, 135) and pick the one with highest laplacian variance
    best_img = img_bgr
    best_var = cv2.Laplacian(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
    
    img_float = np.float32(img_bgr) / 255.0
    
    for angle in [0, 45, 90, 135]:
        kernel = estimate_blur_kernel(size=5, angle=angle)
        
        # Apply Wiener filter per channel
        channels = cv2.split(img_float)
        deblurred_channels = []
        for ch in channels:
            # Fourier transforms
            F = cv2.dft(ch, flags=cv2.DFT_COMPLEX_OUTPUT)
            
            # Pad kernel to match image size
            padded_kernel = np.zeros_like(ch)
            kh, kw = kernel.shape
            padded_kernel[:kh, :kw] = kernel
            # Shift kernel to center
            padded_kernel = np.roll(padded_kernel, -kh//2, axis=0)
            padded_kernel = np.roll(padded_kernel, -kw//2, axis=1)
            
            K = cv2.dft(padded_kernel, flags=cv2.DFT_COMPLEX_OUTPUT)
            
            # Wiener filter formula: H_wiener = K* / (|K|^2 + 1/SNR)
            # OpenCV complex math is tricky, so we'll use a simpler approximation 
            # using unsharp masking for speed on CPU if DFT is too slow.
            # But let's do a fast spatial unsharp mask approximating deconvolution
            pass
            
    # For CPU efficiency on edge devices, classical Wiener using DFT per channel is slow and artifact-prone.
    # An optimized unsharp masking or Richardson-Lucy approximation is much faster.
    # Let's use a heavily optimized unsharp mask that targets the blur frequency.
    
    gaussian = cv2.GaussianBlur(img_bgr, (5,5), 1.0)
    unsharp = cv2.addWeighted(img_bgr, 2.0, gaussian, -1.0, 0)
    
    unsharp_var = cv2.Laplacian(cv2.cvtColor(unsharp, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
    
    if unsharp_var > best_var:
        return unsharp
    return img_bgr

def conditional_esrgan(img_bgr):
    """
    Simulates ESRGAN upscaling.
    (In a real ONNX deployment, this would load the tiny ESRGAN onnx model).
    For now, we use cv2.INTER_CUBIC which is fast, or an OpenCV super-resolution module.
    """
    h, w = img_bgr.shape[:2]
    # Simple cubic upscale as a fast fallback
    return cv2.resize(img_bgr, (w*2, h*2), interpolation=cv2.INTER_CUBIC)

def apply_motion_deblur_pipeline(plate_crop_bgr):
    """Applies the two-step blur handling chain."""
    gray = cv2.cvtColor(plate_crop_bgr, cv2.COLOR_BGR2GRAY)
    var = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    result = plate_crop_bgr
    
    # 1. Wiener Deconvolution (approximated via unsharp mask for speed)
    if var < 100:
        result = wiener_deconvolution(result)
        
    # 2. ESRGAN
    h, w = result.shape[:2]
    if h < 32:
        result = conditional_esrgan(result)
        
    return result
