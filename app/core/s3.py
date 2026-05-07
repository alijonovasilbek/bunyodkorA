import boto3
import io
import mimetypes
import os
from uuid import uuid4
from fastapi import UploadFile
from PIL import Image
import fitz  # PyMuPDF
from .config import settings

AWS_ACCESS_KEY_ID = settings.AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = settings.AWS_SECRET_ACCESS_KEY
AWS_BUCKET_NAME = settings.AWS_BUCKET_NAME
AWS_REGION = settings.AWS_REGION

s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

S3_FOLDER_RENAMES = {
    "student-documents": "student-documentsa",
    "konspekts": "konspektsa",
}


def remap_s3_folder(folder: str) -> str:
    normalized_folder = (folder or "").strip("/")
    if not normalized_folder:
        return normalized_folder

    for source_prefix, target_prefix in S3_FOLDER_RENAMES.items():
        if normalized_folder == source_prefix:
            return target_prefix
        if normalized_folder.startswith(f"{source_prefix}/"):
            suffix = normalized_folder[len(source_prefix):]
            return f"{target_prefix}{suffix}"

    return normalized_folder

async def upload_image_to_s3(file: UploadFile, folder: str = "uploads") -> str:
    """
    Upload image to S3 with automatic format conversion.

    Supported formats:
    - Images: JPG, JPEG, PNG
    - Documents: PDF (converts to JPG automatically)

    NOT supported: DOCX, DOC, XLS, XLSX, TXT
    (Please convert office documents to PDF before uploading)

    Returns:
        S3 URL of uploaded JPG/PNG file
    """
    if not file:
        return None

    try:
        folder = remap_s3_folder(folder)

        # Read file content
        content = await file.read()

        # Get file extension and content type
        extension = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
        content_type = (file.content_type or "").lower()

        # Block unsupported formats (Office documents)
        unsupported_formats = ['docx', 'doc', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv']
        if extension in unsupported_formats:
            raise ValueError(
                f"❌ {extension.upper()} format is not supported.\n"
                f"✅ Please convert your file to PDF first, then upload.\n"
                f"Supported formats: JPG, PNG, PDF"
            )

        # Check if content type suggests office document
        office_content_types = ['word', 'excel', 'powerpoint', 'msword', 'ms-excel', 'sheet', 'document']
        if any(office_type in content_type for office_type in office_content_types):
            raise ValueError(
                f"❌ Office documents are not supported.\n"
                f"✅ Please convert to PDF first.\n"
                f"Supported formats: JPG, PNG, PDF"
            )

        # Check if it's a PDF
        is_pdf = extension == "pdf" or "pdf" in content_type

        if is_pdf:
            # Convert PDF to JPG (first page only)
            try:
                pdf_document = fitz.open(stream=content, filetype="pdf")

                if pdf_document.page_count == 0:
                    raise ValueError("PDF file is empty or corrupted")

                # Get first page
                page = pdf_document[0]

                # Render page to pixmap (high quality)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x resolution

                # Convert pixmap to JPEG bytes
                img_data = pix.tobytes("jpeg")

                # Save to buffer
                buffer = io.BytesIO(img_data)
                buffer.seek(0)

                pdf_document.close()

                # Set extension and content type
                extension = "jpg"
                final_content_type = "image/jpeg"

            except Exception as pdf_error:
                raise ValueError(f"Failed to convert PDF to JPG: {str(pdf_error)}")

        else:
            # For regular images (JPG, PNG, JPEG)
            buffer = io.BytesIO(content)

            # Validate it's actually an image
            try:
                img = Image.open(buffer)
                img.verify()  # Verify it's a valid image
                buffer.seek(0)  # Reset buffer position after verify

                # Normalize extension
                if extension in ["jpg", "jpeg"]:
                    extension = "jpg"
                    final_content_type = "image/jpeg"
                elif extension == "png":
                    final_content_type = "image/png"
                elif extension in ["gif", "bmp", "webp"]:
                    # Convert other formats to JPG
                    img = Image.open(buffer)
                    if img.mode in ("RGBA", "LA", "P"):
                        # Convert transparency to white background
                        background = Image.new("RGB", img.size, (255, 255, 255))
                        if img.mode == "P":
                            img = img.convert("RGBA")
                        background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                        img = background
                    elif img.mode != "RGB":
                        img = img.convert("RGB")

                    # Save as JPG
                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=95)
                    buffer.seek(0)
                    extension = "jpg"
                    final_content_type = "image/jpeg"
                else:
                    raise ValueError(
                        f"Unsupported image format: {extension}.\n"
                        f"Supported formats: JPG, PNG, PDF"
                    )

            except Exception as img_error:
                error_msg = str(img_error)
                if "cannot identify image file" in error_msg.lower():
                    raise ValueError(
                        f"❌ File is not a valid image or PDF.\n"
                        f"✅ Please upload: JPG, PNG, or PDF files only.\n"
                        f"If you have a DOCX/DOC file, convert it to PDF first."
                    )
                raise ValueError(f"Invalid image file: {error_msg}")

        # Create S3 key
        key = f"{folder}/{uuid4()}.{extension}"

        # Upload to S3
        s3.upload_fileobj(
            Fileobj=buffer,
            Bucket=AWS_BUCKET_NAME,
            Key=key,
            ExtraArgs={
                "ContentType": final_content_type,
            }
        )

        return f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"

    except ValueError as ve:
        # Re-raise validation errors with clear message
        raise Exception(f"File validation error: {str(ve)}")
    except Exception as e:
        raise Exception(f"S3 upload error: {str(e)}")


async def upload_as_pdf_to_s3(file: UploadFile, folder: str = "student-documents") -> str:
    """
    Upload any file (image or PDF) to S3 as PDF format.

    - JPG/PNG images → Convert to PDF (single page)
    - PDF files → Upload as-is

    This reduces RAM usage during contract generation since all files are
    already in PDF format and can be merged directly without conversion.

    Returns:
        S3 URL of uploaded PDF file
    """
    import asyncio
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    import tempfile
    import os

    if not file:
        return None

    try:
        folder = remap_s3_folder(folder)

        # Read file content
        content = await file.read()

        # Get file extension and content type
        extension = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
        content_type = (file.content_type or "").lower()

        # Check if it's a PDF
        is_pdf = (
            extension == "pdf" or
            "pdf" in content_type or
            content.startswith(b'%PDF')
        )

        def _convert_and_upload():
            if is_pdf:
                # PDF file - upload directly
                print(f"📄 Uploading PDF directly: {file.filename}")
                buffer = io.BytesIO(content)
            else:
                # Image file - convert to PDF
                print(f"🖼 Converting image to PDF: {file.filename}")

                # Open image
                img_buffer = io.BytesIO(content)
                img = Image.open(img_buffer)

                # Convert to RGB if needed
                if img.mode in ("RGBA", "LA", "P"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    if img.mode in ("RGBA", "LA"):
                        background.paste(img, mask=img.split()[-1])
                    else:
                        background.paste(img)
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Save image to temp file
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_img:
                    img.save(temp_img.name, format="PNG")
                    temp_img_path = temp_img.name

                # Create PDF from image
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
                    temp_pdf_path = temp_pdf.name

                c = canvas.Canvas(temp_pdf_path, pagesize=A4)

                # Calculate image dimensions to fit A4
                w, h = img.size
                aspect = h / w
                max_width = A4[0] - 30 * mm
                max_height = A4[1] - 30 * mm
                width = max_width
                height = width * aspect
                if height > max_height:
                    height = max_height
                    width = height / aspect
                x = (A4[0] - width) / 2
                y = (A4[1] - height) / 2

                c.drawImage(temp_img_path, x, y, width=width, height=height)
                c.showPage()
                c.save()

                # Read PDF into buffer
                with open(temp_pdf_path, 'rb') as f:
                    pdf_content = f.read()
                buffer = io.BytesIO(pdf_content)

                # Cleanup temp files
                try:
                    os.unlink(temp_img_path)
                    os.unlink(temp_pdf_path)
                except:
                    pass

                print(f"✓ Image converted to PDF successfully")

            # Create S3 key (always .pdf extension)
            key = f"{folder}/{uuid4()}.pdf"

            # Upload to S3
            s3.upload_fileobj(
                Fileobj=buffer,
                Bucket=AWS_BUCKET_NAME,
                Key=key,
                ExtraArgs={"ContentType": "application/pdf"}
            )

            return f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"

        # Run in thread pool to avoid blocking
        return await asyncio.to_thread(_convert_and_upload)

    except Exception as e:
        raise Exception(f"Failed to upload file as PDF: {str(e)}")


from urllib.parse import urlparse

def extract_key_from_url(url: str) -> str:
    return urlparse(url).path.lstrip("/")


def normalize_s3_key(value: str) -> str:
    # Eski URL bo‘lsa -> key chiqarib oladi
    # Yangi key bo‘lsa -> o‘sha holicha ishlaydi
    if value.startswith("http"):
        return extract_key_from_url(value)
    return value


def generate_signed_url(value: str, expires_seconds: int = 180) -> str:
    """
    Universal:
    - URL bo‘lsa ham ishlaydi
    - Key bo‘lsa ham ishlaydi
    - 3 minutlik link qaytaradi
    """
    try:
        key = normalize_s3_key(value)

        return s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": AWS_BUCKET_NAME,
                "Key": key
            },
            ExpiresIn=expires_seconds
        )
    except Exception as e:
        raise Exception(f"Signed URL error: {str(e)}")


async def upload_private_file_to_s3(
    file: UploadFile,
    folder: str,
    allowed_extensions: set[str] | None = None,
) -> str:
    """
    Upload a private file to S3 and return the stored object key.

    By default supports common document and image formats used by student attachments.
    """
    import asyncio

    if not file:
        return None

    folder = remap_s3_folder(folder)
    extension = os.path.splitext(file.filename or "")[1].lower()
    allowed_extensions = allowed_extensions or {
        ".pdf",
        ".doc",
        ".docx",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".bmp",
    }
    if extension not in allowed_extensions:
        raise Exception(
            "Unsupported file format. Allowed formats: PDF, DOC, DOCX, PNG, JPG, JPEG, WEBP, GIF, BMP"
        )

    content = await file.read()
    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    key = f"{folder}/{uuid4()}{extension}"

    def _upload() -> None:
        buffer = io.BytesIO(content)
        s3.upload_fileobj(
            Fileobj=buffer,
            Bucket=AWS_BUCKET_NAME,
            Key=key,
            ExtraArgs={"ContentType": content_type},
        )

    await asyncio.to_thread(_upload)
    return key


async def upload_private_document_to_s3(file: UploadFile, folder: str = "president_documents") -> str:
    """
    Upload a private document to S3 and return the stored object key.

    Supported formats:
    - PDF
    - DOC
    - DOCX
    """
    return await upload_private_file_to_s3(
        file=file,
        folder=folder,
        allowed_extensions={".pdf", ".doc", ".docx"},
    )


async def download_s3_object(key: str) -> tuple[bytes, str | None]:
    """
    Download a private S3 object by key.
    Returns file bytes and detected content type.
    """
    import asyncio

    normalized_key = normalize_s3_key(key)

    def _download() -> tuple[bytes, str | None]:
        response = s3.get_object(Bucket=AWS_BUCKET_NAME, Key=normalized_key)
        data = response["Body"].read()
        return data, response.get("ContentType")

    return await asyncio.to_thread(_download)

