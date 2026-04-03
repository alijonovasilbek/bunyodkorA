"""
File upload service for AWS S3.

Handles uploading files to AWS S3 and returning public URLs.
"""
import os
import uuid
from datetime import datetime
from typing import BinaryIO, Optional
import boto3
from botocore.exceptions import ClientError
from fastapi import UploadFile


class FileUploadError(Exception):
    """Base exception for file upload errors"""
    pass


class S3FileUploadService:
    """Service for uploading files to AWS S3"""

    def __init__(
        self,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_region: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ):
        """
        Initialize S3 client.

        Args:
            aws_access_key_id: AWS access key (defaults to env var AWS_ACCESS_KEY_ID)
            aws_secret_access_key: AWS secret key (defaults to env var AWS_SECRET_ACCESS_KEY)
            aws_region: AWS region (defaults to env var AWS_REGION or 'us-east-1')
            bucket_name: S3 bucket name (defaults to env var S3_BUCKET_NAME)
        """
        self.aws_access_key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        self.aws_region = aws_region or os.getenv("AWS_REGION", "us-east-1")
        self.bucket_name = bucket_name or os.getenv("S3_BUCKET_NAME")

        if not all([self.aws_access_key_id, self.aws_secret_access_key, self.bucket_name]):
            raise FileUploadError(
                "AWS credentials and bucket name must be provided via constructor or environment variables "
                "(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME)"
            )

        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.aws_region
        )

    def generate_unique_filename(self, original_filename: str, prefix: str = "") -> str:
        """
        Generate a unique filename for S3 storage.

        Args:
            original_filename: Original file name
            prefix: Optional prefix for the file path (e.g., "contracts/", "students/")

        Returns:
            Unique filename with timestamp and UUID
        """
        # Extract file extension
        _, ext = os.path.splitext(original_filename)

        # Generate unique name: prefix/YYYY-MM-DD/uuid_timestamp.ext
        date_prefix = datetime.utcnow().strftime("%Y-%m-%d")
        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.utcnow().strftime("%H%M%S")

        filename = f"{unique_id}_{timestamp}{ext}"

        if prefix:
            return f"{prefix.rstrip('/')}/{date_prefix}/{filename}"
        else:
            return f"{date_prefix}/{filename}"

    async def upload_file(
        self,
        file: UploadFile,
        prefix: str = "",
        make_public: bool = True
    ) -> str:
        """
        Upload file to S3 and return public URL.

        Args:
            file: FastAPI UploadFile object
            prefix: Optional prefix for the file path (e.g., "contracts/", "students/")
            make_public: Make file publicly accessible (default: True)

        Returns:
            Public URL of the uploaded file

        Raises:
            FileUploadError: If upload fails
        """
        try:
            # Generate unique filename
            s3_key = self.generate_unique_filename(file.filename, prefix)

            # Read file content
            file_content = await file.read()

            # Determine content type
            content_type = file.content_type or "application/octet-stream"

            # Upload to S3 (without ACL - modern S3 buckets don't support ACLs by default)
            extra_args = {
                'ContentType': content_type,
            }

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_content,
                **extra_args
            )

            # Generate URL
            # For long-term access (konspekts), bucket policy should allow public read
            # See: AWS Console → S3 → Bucket → Permissions → Bucket Policy
            # Example policy to allow public read for konspekts folder:
            # {
            #   "Version": "2012-10-17",
            #   "Statement": [{
            #     "Effect": "Allow",
            #     "Principal": "*",
            #     "Action": "s3:GetObject",
            #     "Resource": "arn:aws:s3:::BUCKET_NAME/konspekts/*"
            #   }]
            # }
            url = f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{s3_key}"

            # Reset file pointer for potential reuse
            await file.seek(0)

            return url

        except ClientError as e:
            raise FileUploadError(f"Failed to upload file to S3: {str(e)}")
        except Exception as e:
            raise FileUploadError(f"Unexpected error during file upload: {str(e)}")

    async def upload_multiple_files(
        self,
        files: list[UploadFile],
        prefix: str = "",
        make_public: bool = True
    ) -> list[str]:
        """
        Upload multiple files to S3.

        Args:
            files: List of FastAPI UploadFile objects
            prefix: Optional prefix for the file paths
            make_public: Make files publicly accessible

        Returns:
            List of public URLs in the same order as input files

        Raises:
            FileUploadError: If any upload fails
        """
        urls = []
        for file in files:
            url = await self.upload_file(file, prefix, make_public)
            urls.append(url)
        return urls

    def delete_file(self, url: str) -> bool:
        """
        Delete file from S3 by URL.

        Args:
            url: Public URL of the file

        Returns:
            True if successful, False otherwise
        """
        try:
            # Extract S3 key from URL
            # URL format: https://{bucket}.s3.{region}.amazonaws.com/{key}
            if self.bucket_name in url and ".amazonaws.com/" in url:
                s3_key = url.split(".amazonaws.com/")[1]

                self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=s3_key
                )
                return True
            else:
                return False

        except ClientError:
            return False


# Create singleton instance (will be initialized when AWS credentials are available)
try:
    from app.core.config import settings

    file_upload_service = S3FileUploadService(
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        aws_region=settings.AWS_REGION or "us-east-1",
        bucket_name=settings.AWS_BUCKET_NAME or None,
    )
except FileUploadError:
    # Service will be None if AWS credentials are not configured
    # This allows the app to start even without S3 configured
    file_upload_service = None
