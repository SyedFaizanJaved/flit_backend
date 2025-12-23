import os
import uuid

def custom_s3_upload_path(instance, filename, folder):
    """
    Generate a custom upload path with a UUID suffix to prevent filename collisions.
    
    Args:
        instance: The model instance where the FileField is defined.
        filename: Original filename.
        folder: The base folder path where the file should be stored.
    
    Returns:
        str: The generated file path.
    """
    name, ext = os.path.splitext(filename)
    suffix = uuid.uuid4().hex[:6]
    return f"{folder}/{name}_{suffix}{ext}"

def resume_upload_path(instance, filename):
    """Generate upload path for resume files."""
    return custom_s3_upload_path(instance, filename, "resumes")

def image_upload_path(instance, filename):
    """Generate upload path for image files."""
    return custom_s3_upload_path(instance, filename, "images")

def video_upload_path(instance, filename):
    """Generate upload path for video files."""
    return custom_s3_upload_path(instance, filename, "videos")

def document_upload_path(instance, filename):
    """Generate upload path for general document files."""
    return custom_s3_upload_path(instance, filename, "documents")
