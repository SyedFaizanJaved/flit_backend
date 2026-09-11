import os
import uuid
import re
from io import BytesIO

import pillow_heif
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps

# Teach Pillow (and so every Django/DRF ImageField) to read HEIC/HEIF — the default
# format for Mac/iPhone photos. Without it they fail as "Upload a valid image".
pillow_heif.register_heif_opener()

# Formats every browser renders in an <img> (MPO = iPhone multi-picture JPEG). Anything
# else Pillow can read — HEIC/HEIF, TIFF, JPEG 2000, ICNS, ICO... — gets re-encoded.
BROWSER_VIEWABLE_FORMATS = {'JPEG', 'MPO', 'PNG', 'GIF', 'WEBP', 'AVIF', 'BMP'}


def to_web_image(file_obj):
    """
    Re-encode an already-validated image the browser can't display (HEIC/HEIF, TIFF,
    JPEG 2000, ICNS...) as JPEG, or PNG when it has transparency. Browser-viewable
    formats are returned untouched.
    """
    file_obj.seek(0)
    with Image.open(file_obj) as img:
        if img.format in BROWSER_VIEWABLE_FORMATS:
            file_obj.seek(0)
            return file_obj
        img = ImageOps.exif_transpose(img)
        buf = BytesIO()
        if img.mode in ('RGBA', 'LA') or 'transparency' in img.info:
            img.save(buf, format='PNG')
            ext, content_type = '.png', 'image/png'
        else:
            img.convert('RGB').save(buf, format='JPEG', quality=90)
            ext, content_type = '.jpg', 'image/jpeg'
    name = os.path.splitext(file_obj.name)[0] + ext
    return SimpleUploadedFile(name, buf.getvalue(), content_type=content_type)


def sanitize_filename(file_obj, max_length=50):
    """
    Sanitize and truncate the filename of an uploaded file.
    This prevents Django's ImageField validation from failing on long original filenames.
    """
    if file_obj and hasattr(file_obj, 'name'):
        name, ext = os.path.splitext(file_obj.name)
        if len(name) > max_length:
            file_obj.name = name[:max_length] + ext
    return file_obj

def custom_s3_upload_path(instance, filename, folder):
    """
    Generate a custom upload path with a UUID suffix to prevent filename collisions.
    Spaces and special characters in filename are replaced with hyphens to avoid URL encoding issues.
    Multiple consecutive spaces/special characters are collapsed into a single hyphen.
    
    Args:
        instance: The model instance where the FileField is defined.
        filename: Original filename.
        folder: The base folder path where the file should be stored.
    
    Returns:
        str: The generated file path.
    """
    # Split filename into name and extension
    name, ext = os.path.splitext(filename)
    
    # Replace spaces and special characters (except alphanumeric, dots, hyphens, underscores) with hyphens
    # This includes: +, *, &, %, $, #, @, !, etc.
    name = re.sub(r'[^a-zA-Z0-9._-]', '-', name)
    
    # Collapse multiple consecutive hyphens into a single hyphen
    name = re.sub(r'-+', '-', name)
    
    # Remove leading and trailing hyphens
    name = name.strip('-')
    
    # Truncate to max 50 chars to avoid DB max_length issues (typically 100 chars)
    # folder(max ~30) + / + name(50) + _ + suffix(6) + ext(max ~10) ~= 97 chars
    if len(name) > 50:
        name = name[:50].rstrip('-')
    
    # Generate UUID suffix
    suffix = uuid.uuid4().hex[:6]
    
    return f"{folder}/{name}_{suffix}{ext}"

def resume_upload_path(instance, filename):
    """Generate upload path for resume files."""
    return custom_s3_upload_path(instance, filename, "candidates/resumes")

def image_upload_path(instance, filename):
    """Generate upload path for profile image files."""
    return custom_s3_upload_path(instance, filename, "candidates/profile_images")

def video_upload_path(instance, filename):
    """Generate upload path for video files."""
    return custom_s3_upload_path(instance, filename, "candidates/videos")

def document_upload_path(instance, filename):
    """Generate upload path for general document files."""
    return custom_s3_upload_path(instance, filename, "documents")

def achievement_image_upload_path(instance, filename):
    """Generate upload path for achievement image files."""
    return custom_s3_upload_path(instance, filename, "candidates/achievements")


def company_logo_upload_path(instance, filename):
    """Generate upload path for company logos."""
    return custom_s3_upload_path(instance, filename, "companies/logos")


def company_gallery_upload_path(instance, filename):
    """Generate upload path for company gallery images."""
    return custom_s3_upload_path(instance, filename, "companies/gallery")
