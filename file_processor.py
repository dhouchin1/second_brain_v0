#!/usr/bin/env python3
"""
File Processing Module for Second Brain
Handles images, PDFs, and documents with OCR and text extraction
"""

import io
import uuid
import hashlib
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
import json
import base64
from datetime import datetime
import logging
import shutil
import subprocess

# Optional dependencies
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False

# Image processing
try:
    from PIL import Image, ExifTags
    import pytesseract
    IMAGING_AVAILABLE = True
except ImportError:
    IMAGING_AVAILABLE = False

# Optional HEIC/HEIF support via pillow-heif
try:
    import pillow_heif  # type: ignore
    pillow_heif.register_heif_opener()  # enable PIL to open HEIC/HEIF
except Exception:
    pass

# PDF processing
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

from config import settings

logger = logging.getLogger(__name__)

class FileProcessor:
    """Handles processing of various file types for Second Brain"""
    
    SUPPORTED_IMAGE_TYPES = {
        'image/jpeg': '.jpg',
        'image/jpg': '.jpg', 
        'image/png': '.png',
        'image/gif': '.gif',
        'image/bmp': '.bmp',
        'image/tiff': '.tiff',
        'image/webp': '.webp'
    }
    
    SUPPORTED_DOCUMENT_TYPES = {
        'application/pdf': '.pdf'
    }
    
    SUPPORTED_AUDIO_TYPES = {
        'audio/mpeg': '.mp3',
        'audio/mp3': '.mp3',
        'audio/wav': '.wav',
        'audio/wave': '.wav',
        'audio/x-pn-wav': '.wav',
        'audio/x-wav': '.wav',
        'audio/mp4': '.m4a',
        'audio/m4a': '.m4a',
        'audio/x-m4a': '.m4a',
        'audio/aac': '.aac',
        'audio/x-aac': '.aac',
        'audio/ogg': '.ogg',
        'audio/webm': '.webm',  # Some browsers use audio/webm for MediaRecorder
        'video/webm': '.webm'  # Browser audio recordings often use WebM container
    }
    
    def __init__(self):
        """Initialize file processor"""
        self.uploads_dir = settings.uploads_dir
        self.audio_dir = settings.audio_dir
        self.max_size = settings.max_file_size
        
        # Ensure directories exist
        self.uploads_dir.mkdir(exist_ok=True)
        self.audio_dir.mkdir(exist_ok=True)
        
    def detect_file_type(self, file_content: bytes, filename: str) -> Tuple[str, str]:
        """
        Detect file type using python-magic or filename fallback
        Returns (mime_type, category)
        """
        mime_type = None
        
        if MAGIC_AVAILABLE:
            try:
                mime_type = magic.from_buffer(file_content, mime=True)
            except Exception as e:
                logger.warning(f"Could not detect MIME type with magic: {e}")
        
        # Normalize MIME (strip parameters like ;codecs=opus)
        if mime_type:
            try:
                mime_type = mime_type.split(';', 1)[0].strip().lower()
            except Exception:
                pass

        # Fallback to filename extension if magic failed, unavailable, or returned generic type
        if not mime_type or mime_type == 'application/octet-stream':
            ext = Path(filename).suffix.lower()
            if ext in ['.jpg', '.jpeg']:
                mime_type = 'image/jpeg'
            elif ext == '.png':
                mime_type = 'image/png'
            elif ext == '.gif':
                mime_type = 'image/gif'
            elif ext in ['.bmp']:
                mime_type = 'image/bmp'
            elif ext in ['.tiff', '.tif']:
                mime_type = 'image/tiff'
            elif ext == '.webp':
                mime_type = 'image/webp'
            elif ext == '.pdf':
                mime_type = 'application/pdf'
            elif ext == '.mp3':
                mime_type = 'audio/mpeg'
            elif ext == '.wav':
                mime_type = 'audio/wav'
            elif ext == '.m4a':
                mime_type = 'audio/mp4'
            elif ext == '.ogg':
                mime_type = 'audio/ogg'
            elif ext == '.webm':
                mime_type = 'video/webm'  # Browser audio recordings
            else:
                mime_type = 'application/octet-stream'
        
        # Categorize
        if mime_type.startswith('image/'):
            return mime_type, 'image'
        elif mime_type.startswith('audio/') or mime_type == 'video/webm':
            return mime_type, 'audio'
        elif mime_type == 'application/pdf':
            return mime_type, 'document'
        else:
            return mime_type, 'unknown'

    def detect_file_type_from_path(self, file_path: Path, filename: str) -> Tuple[str, str]:
        """Detect file type using python-magic on a saved file path, with extension fallback."""
        mime_type = None
        if MAGIC_AVAILABLE:
            try:
                # type: ignore[attr-defined]
                mime_type = magic.from_file(str(file_path), mime=True)
            except Exception as e:
                logger.warning(f"Could not detect MIME type with magic.from_file: {e}")
        if mime_type:
            try:
                mime_type = mime_type.split(';', 1)[0].strip().lower()
            except Exception:
                pass
        if not mime_type or mime_type == 'application/octet-stream':
            # Fallback to the filename extension
            return self.detect_file_type(b'', filename)
        # Categorize
        if mime_type.startswith('image/'):
            return mime_type, 'image'
        elif mime_type.startswith('audio/') or mime_type == 'video/webm':
            return mime_type, 'audio'
        elif mime_type == 'application/pdf':
            return mime_type, 'document'
        else:
            return mime_type, 'unknown'

    def process_saved_file(self, saved_path: Path, original_filename: str) -> Dict[str, Any]:
        """Process a file that is already saved to disk at saved_path.

        - Detects MIME/category from path/extension
        - Moves to final target dir with a safe filename
        - Performs type-specific processing (image OCR, PDF extraction)
        - For audio, preserves container and queues for transcription
        """
        result: Dict[str, Any] = {
            'success': False,
            'error': None,
            'file_info': {},
            'stored_filename': None,
            'extracted_text': '',
            'metadata': {},
            'processing_type': 'unknown'
        }
        try:
            # Validate size
            size_bytes = saved_path.stat().st_size
            if size_bytes > self.max_size:
                try:
                    saved_path.unlink(missing_ok=True)
                except Exception:
                    pass
                result['error'] = f"File too large ({size_bytes} bytes, max {self.max_size})"
                return result

            mime_type, category = self.detect_file_type_from_path(saved_path, original_filename)
            all_supported = {**self.SUPPORTED_IMAGE_TYPES, **self.SUPPORTED_DOCUMENT_TYPES, **self.SUPPORTED_AUDIO_TYPES}
            if mime_type not in all_supported:
                try:
                    saved_path.unlink(missing_ok=True)
                except Exception:
                    pass
                result['error'] = f"Unsupported file type: {mime_type}"
                return result

            file_info = {
                'original_filename': original_filename,
                'mime_type': mime_type,
                'category': category,
                'size_bytes': size_bytes,
                'extension': all_supported[mime_type],
            }
            result['file_info'] = file_info

            # Determine final destination and name
            safe_filename = self.generate_safe_filename(original_filename, mime_type)
            target_dir = self.audio_dir if category == 'audio' else self.uploads_dir
            target_dir.mkdir(exist_ok=True)
            final_path = target_dir / safe_filename

            # Move into place
            shutil.move(str(saved_path), str(final_path))
            result['stored_filename'] = safe_filename

            # Type-specific processing
            if category == 'image':
                try:
                    converted_path = self.convert_image_to_png(final_path)
                    if converted_path and converted_path.exists():
                        if converted_path != final_path:
                            try:
                                final_path.unlink(missing_ok=True)
                            except Exception:
                                pass
                            final_path = converted_path
                            result['stored_filename'] = converted_path.name
                            file_info['extension'] = '.png'
                            file_info['mime_type'] = 'image/png'
                            file_info['size_bytes'] = converted_path.stat().st_size
                except Exception as e:
                    logger.warning(f"Image conversion to PNG failed: {e}")

                text, metadata = self.extract_image_text(final_path)
                result['extracted_text'] = text
                result['metadata'] = metadata
                result['processing_type'] = 'image_ocr'

            elif category == 'document':
                text, metadata = self.extract_pdf_text(final_path)
                result['extracted_text'] = text
                result['metadata'] = metadata
                result['processing_type'] = 'pdf_extraction'

            elif category == 'audio':
                result['processing_type'] = 'audio_transcription'
                result['metadata'] = {
                    'note': 'Audio queued for whisper transcription',
                    'stored_container': file_info.get('mime_type'),
                    'stored_filename': result['stored_filename']
                }

            result['success'] = True
            return result
        except Exception as e:
            logger.error(f"process_saved_file failed for {saved_path}: {e}")
            result['error'] = str(e)
            return result
    
    def validate_file(self, file_content: bytes, filename: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate uploaded file
        Returns (is_valid, error_message, file_info)
        """
        if len(file_content) > self.max_size:
            return False, f"File too large ({len(file_content)} bytes, max {self.max_size})", {}
        
        mime_type, category = self.detect_file_type(file_content, filename)
        
        # Check if file type is supported
        all_supported = {**self.SUPPORTED_IMAGE_TYPES, **self.SUPPORTED_DOCUMENT_TYPES, **self.SUPPORTED_AUDIO_TYPES}
        if mime_type not in all_supported:
            return False, f"Unsupported file type: {mime_type}", {}
        
        file_info = {
            'original_filename': filename,
            'mime_type': mime_type,
            'category': category,
            'size_bytes': len(file_content),
            'extension': all_supported[mime_type]
        }
        
        return True, "", file_info
    
    def generate_safe_filename(self, original_filename: str, mime_type: str) -> str:
        """Generate a safe, unique filename for storage"""
        # Include microseconds and a short random suffix to avoid collisions
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S-%f")
        rand = uuid.uuid4().hex[:6]
        # Hash the original filename for stability across browsers that reuse names
        file_hash = hashlib.md5(original_filename.encode()).hexdigest()[:6]
        
        # Get appropriate extension
        all_supported = {**self.SUPPORTED_IMAGE_TYPES, **self.SUPPORTED_DOCUMENT_TYPES, **self.SUPPORTED_AUDIO_TYPES}
        extension = all_supported.get(mime_type, '.bin')
        
        return f"{timestamp}-{file_hash}{rand}{extension}"
    
    def save_file(self, file_content: bytes, file_info: Dict[str, Any]) -> Tuple[Path, str]:
        """
        Save file to appropriate directory
        Returns (file_path, stored_filename)
        """
        safe_filename = self.generate_safe_filename(
            file_info['original_filename'], 
            file_info['mime_type']
        )
        
        # Choose directory based on category
        if file_info['category'] == 'audio':
            target_dir = self.audio_dir
        else:
            target_dir = self.uploads_dir
        
        file_path = target_dir / safe_filename
        
        # Save file
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        return file_path, safe_filename
    
    def extract_image_text(self, file_path: Path) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text from image using OCR
        Returns (extracted_text, metadata)
        """
        if not IMAGING_AVAILABLE:
            return "", {"error": "Image processing not available"}
        
        try:
            with Image.open(file_path) as img:
                # Get basic image info
                metadata = {
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'mode': img.mode
                }
                
                # Extract EXIF data if available
                if hasattr(img, '_getexif') and img._getexif():
                    exif = img._getexif()
                    if exif:
                        exif_data = {}
                        for tag_id, value in exif.items():
                            tag = ExifTags.TAGS.get(tag_id, tag_id)
                            exif_data[tag] = value
                        metadata['exif'] = exif_data
                
                # Perform OCR
                try:
                    text = pytesseract.image_to_string(img, config='--psm 3')
                    text = text.strip()
                    metadata['ocr_success'] = True
                    metadata['text_length'] = len(text)
                    return text, self._json_safe(metadata)
                except Exception as ocr_error:
                    logger.warning(f"OCR failed for {file_path}: {ocr_error}")
                    metadata['ocr_error'] = str(ocr_error)
                    return "", self._json_safe(metadata)
                    
        except Exception as e:
            logger.error(f"Failed to process image {file_path}: {e}")
            return "", {"error": str(e)}
    
    def extract_pdf_text(self, file_path: Path) -> Tuple[str, Dict[str, Any]]:
        """
        Extract text from PDF
        Returns (extracted_text, metadata)
        """
        if not PDF_AVAILABLE:
            return "", {"error": "PDF processing not available"}
        
        try:
            text_content = []
            metadata = {'pages': 0, 'extraction_method': 'PyPDF2'}
            
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                metadata['pages'] = len(pdf_reader.pages)
                
                # Extract metadata
                if pdf_reader.metadata:
                    pdf_metadata = {}
                    for key, value in pdf_reader.metadata.items():
                        if isinstance(value, str):
                            pdf_metadata[key.replace('/', '')] = value
                    metadata['pdf_info'] = pdf_metadata
                
                # Extract text from all pages
                for page_num, page in enumerate(pdf_reader.pages, 1):
                    try:
                        page_text = page.extract_text()
                        if page_text.strip():
                            text_content.append(f"[Page {page_num}]\n{page_text.strip()}")
                    except Exception as page_error:
                        logger.warning(f"Failed to extract text from page {page_num}: {page_error}")
                        continue
                
                full_text = "\n\n".join(text_content)
                metadata['text_length'] = len(full_text)
                metadata['extraction_success'] = True
                
                return full_text, self._json_safe(metadata)
                
        except Exception as e:
            logger.error(f"Failed to process PDF {file_path}: {e}")
            return "", {"error": str(e)}
    
    def process_file(self, file_content: bytes, original_filename: str) -> Dict[str, Any]:
        """
        Main file processing method
        Returns comprehensive processing result
        """
        result = {
            'success': False,
            'error': None,
            'file_info': {},
            'stored_filename': None,
            'extracted_text': '',
            'metadata': {},
            'processing_type': 'unknown'
        }
        
        try:
            # Validate file
            is_valid, error_msg, file_info = self.validate_file(file_content, original_filename)
            if not is_valid:
                result['error'] = error_msg
                return result
            
            result['file_info'] = file_info
            
            # Save file
            file_path, stored_filename = self.save_file(file_content, file_info)
            result['stored_filename'] = stored_filename
            
            # Process based on category
            category = file_info['category']
            
            if category == 'image':
                # Normalize images to PNG to improve rendering compatibility
                try:
                    converted_path = self.convert_image_to_png(file_path)
                    if converted_path and converted_path.exists():
                        if converted_path != file_path:
                            # Remove original file to avoid storing both
                            try:
                                file_path.unlink(missing_ok=True)
                            except Exception:
                                pass
                            file_path = converted_path
                            result['stored_filename'] = converted_path.name
                            file_info['extension'] = '.png'
                            file_info['mime_type'] = 'image/png'
                            file_info['size_bytes'] = converted_path.stat().st_size
                except Exception as e:
                    logger.warning(f"Image conversion to PNG failed: {e}")

                text, metadata = self.extract_image_text(file_path)
                result['extracted_text'] = text
                result['metadata'] = metadata
                result['processing_type'] = 'image_ocr'
                
            elif category == 'document':
                text, metadata = self.extract_pdf_text(file_path)
                result['extracted_text'] = text
                result['metadata'] = metadata
                result['processing_type'] = 'pdf_extraction'
                
            elif category == 'audio':
                # Keep original container/extension; transcription will convert to WAV
                try:
                    from config import settings
                    audio_dir = settings.audio_dir
                    audio_dir.mkdir(exist_ok=True)

                    # file_path is already saved under audio_dir with detected extension
                    # Preserve stored filename; downstream pipeline converts to .converted.wav
                    result['processing_type'] = 'audio_transcription'
                    result['metadata'] = {
                        'note': 'Audio queued for whisper transcription',
                        'stored_container': file_info.get('mime_type'),
                        'stored_filename': result['stored_filename']
                    }
                except Exception as audio_error:
                    logger.error(f"Audio file handling failed: {audio_error}")
                    result['processing_type'] = 'audio_transcription'
                    result['metadata'] = {'note': 'Audio queued for whisper transcription'}
                
            result['success'] = True
            
        except Exception as e:
            logger.error(f"File processing failed: {e}")
            result['error'] = str(e)
        
        return result
    
    def get_file_preview(self, file_path: Path, category: str) -> Dict[str, Any]:
        """Generate preview information for a file"""
        preview = {'available': False}
        
        try:
            if category == 'image' and IMAGING_AVAILABLE:
                with Image.open(file_path) as img:
                    # Create thumbnail
                    thumbnail_size = (200, 200)
                    img.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
                    
                    # Convert to base64 for embedding
                    buffer = io.BytesIO()
                    img.save(buffer, format='PNG')
                    thumbnail_data = base64.b64encode(buffer.getvalue()).decode()
                    
                    preview = {
                        'available': True,
                        'type': 'image',
                        'thumbnail': f"data:image/png;base64,{thumbnail_data}",
                        'dimensions': f"{img.width}x{img.height}"
                    }
                    
        except Exception as e:
            logger.warning(f"Failed to generate preview for {file_path}: {e}")
        
        return preview

    def convert_image_to_png(self, input_path: Path) -> Path:
        """Convert image to PNG using ffmpeg if available; fallback to Pillow.

        Returns the path to the PNG file (may be identical to input if already PNG).
        """
        try:
            # If already PNG, return as-is
            if input_path.suffix.lower() == '.png':
                return input_path
            # Preserve GIF to keep animation intact
            if input_path.suffix.lower() == '.gif':
                return input_path

            target_path = input_path.with_suffix('.png')
            # Ensure unique target if a different file already exists with that name
            if target_path.exists() and input_path.resolve() != target_path.resolve():
                stem = input_path.stem
                h = hashlib.md5(str(input_path).encode()).hexdigest()[:6]
                target_path = input_path.with_name(f"{stem}-{h}.png")

            # Prefer ffmpeg if available
            if shutil.which('ffmpeg'):
                cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', str(input_path), str(target_path)]
                subprocess.run(cmd, check=True)
                if target_path.exists():
                    return target_path

            # Fallback to Pillow
            if IMAGING_AVAILABLE:
                with Image.open(input_path) as img:
                    # Convert to a PNG-friendly mode
                    if img.mode not in ('RGB', 'RGBA'):
                        img = img.convert('RGBA' if 'A' in img.getbands() else 'RGB')
                    img.save(target_path, format='PNG')
                if target_path.exists():
                    return target_path

        except Exception as e:
            logger.warning(f"convert_image_to_png error for {input_path}: {e}")
        # If conversion failed, return original path
        return input_path

    def _json_safe(self, obj: Any) -> Any:
        """Recursively convert values to JSON-serializable types.

        - Attempts float() for rationals (e.g., PIL IFDRational)
        - Encodes bytes as base64 strings
        - Converts sets/tuples to lists
        - Falls back to str() for unknown objects
        """
        try:
            json.dumps(obj)
            return obj
        except Exception:
            pass

        if isinstance(obj, dict):
            return {str(self._json_safe(k)): self._json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [self._json_safe(x) for x in obj]
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode('ascii')
        try:
            return float(obj)
        except Exception:
            try:
                return int(obj)
            except Exception:
                return str(obj)
