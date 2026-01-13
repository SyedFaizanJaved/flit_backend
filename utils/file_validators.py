import os
import uuid
import re

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
