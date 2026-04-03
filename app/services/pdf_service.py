"""
PDF operations service for contract management.

Handles:
- Merging multiple documents into single PDF
- Inserting digital signatures into PDF at specific positions
- Generating final contract PDFs
"""
import base64
import io
from typing import List, Optional
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter


class PDFServiceError(Exception):
    """Base exception for PDF service errors"""
    pass


class PDFService:
    """Service for PDF operations"""

    @staticmethod
    def decode_signature(signature_data: str) -> Image.Image:
        """
        Decode base64 signature data to PIL Image.

        Args:
            signature_data: Base64 encoded image string (with or without data URI prefix)

        Returns:
            PIL Image object

        Raises:
            PDFServiceError: If signature data is invalid
        """
        try:
            # Remove data URI prefix if present (e.g., "data:image/png;base64,")
            if "base64," in signature_data:
                signature_data = signature_data.split("base64,")[1]

            # Decode base64
            signature_bytes = base64.b64decode(signature_data)

            # Open as PIL Image
            signature_image = Image.open(io.BytesIO(signature_bytes))

            return signature_image
        except Exception as e:
            raise PDFServiceError(f"Failed to decode signature data: {str(e)}")

    @staticmethod
    def create_signature_overlay(signature_image: Image.Image, page_width: float, page_height: float,
                                 position: str = "bottom") -> bytes:
        """
        Create a PDF overlay with signature at specified position.

        Args:
            signature_image: PIL Image of the signature
            page_width: Width of the PDF page
            page_height: Height of the PDF page
            position: "top" for first signature field or "bottom" for last signature field

        Returns:
            PDF bytes containing the signature overlay
        """
        # Create a PDF in memory
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=(page_width, page_height))

        # Save signature image temporarily
        sig_temp = io.BytesIO()
        signature_image.save(sig_temp, format='PNG')
        sig_temp.seek(0)

        # Calculate signature position and size
        sig_width = 150  # pixels
        sig_height = 50  # pixels

        if position == "top":
            # Position for first signature field (top right area)
            x = page_width - sig_width - 50
            y = page_height - sig_height - 150
        else:
            # Position for last signature field (bottom right area)
            x = page_width - sig_width - 50
            y = 100

        # Draw signature on canvas
        can.drawImage(sig_temp, x, y, width=sig_width, height=sig_height, mask='auto')
        can.save()

        packet.seek(0)
        return packet.getvalue()

    @staticmethod
    def insert_signature_to_pdf(pdf_bytes: bytes, signature_image: Image.Image,
                                first_page_index: int = 0, last_page_index: int = -1) -> bytes:
        """
        Insert signature into PDF at first and last signature positions.

        Args:
            pdf_bytes: Original PDF bytes
            signature_image: PIL Image of the signature
            first_page_index: Index of first page to add signature (default: 0 - first page)
            last_page_index: Index of last page to add signature (default: -1 - last page)

        Returns:
            Modified PDF bytes with signatures inserted

        Raises:
            PDFServiceError: If PDF operations fail
        """
        try:
            # Read original PDF
            reader = PdfReader(io.BytesIO(pdf_bytes))
            writer = PdfWriter()

            # Get page dimensions from first page
            first_page = reader.pages[0]
            page_width = float(first_page.mediabox.width)
            page_height = float(first_page.mediabox.height)

            # Normalize last page index
            if last_page_index < 0:
                last_page_index = len(reader.pages) + last_page_index

            # Process each page
            for page_num, page in enumerate(reader.pages):
                if page_num == first_page_index:
                    # Add signature to first page
                    overlay_bytes = PDFService.create_signature_overlay(
                        signature_image, page_width, page_height, position="top"
                    )
                    overlay_pdf = PdfReader(io.BytesIO(overlay_bytes))
                    page.merge_page(overlay_pdf.pages[0])

                if page_num == last_page_index:
                    # Add signature to last page
                    overlay_bytes = PDFService.create_signature_overlay(
                        signature_image, page_width, page_height, position="bottom"
                    )
                    overlay_pdf = PdfReader(io.BytesIO(overlay_bytes))
                    page.merge_page(overlay_pdf.pages[0])

                writer.add_page(page)

            # Write to bytes
            output = io.BytesIO()
            writer.write(output)
            output.seek(0)

            return output.getvalue()
        except Exception as e:
            raise PDFServiceError(f"Failed to insert signature into PDF: {str(e)}")

    @staticmethod
    def merge_pdfs(pdf_files: List[bytes]) -> bytes:
        """
        Merge multiple PDF documents into a single PDF.

        Args:
            pdf_files: List of PDF file bytes to merge

        Returns:
            Merged PDF bytes

        Raises:
            PDFServiceError: If merge operation fails
        """
        try:
            writer = PdfWriter()

            for pdf_bytes in pdf_files:
                reader = PdfReader(io.BytesIO(pdf_bytes))
                for page in reader.pages:
                    writer.add_page(page)

            # Write to bytes
            output = io.BytesIO()
            writer.write(output)
            output.seek(0)

            return output.getvalue()
        except Exception as e:
            raise PDFServiceError(f"Failed to merge PDFs: {str(e)}")

    @staticmethod
    async def process_contract_signature(
        contract_images_urls: List[str],
        supporting_doc_urls: List[str],
        signature_data: str
    ) -> bytes:
        """
        Complete contract signature workflow:
        1. Decode signature
        2. Insert signature into contract pages (first and last)
        3. Merge all documents (5 contract pages + 4 supporting docs)
        4. Return final PDF

        Args:
            contract_images_urls: List of 5 contract page image URLs
            supporting_doc_urls: List of 4 supporting document URLs
            signature_data: Base64 encoded signature image

        Returns:
            Final merged PDF bytes with signatures

        Raises:
            PDFServiceError: If any operation fails
        """
        # Note: This is a placeholder. In production, you would:
        # 1. Download files from URLs (S3, local storage, etc.)
        # 2. Convert images to PDF if needed
        # 3. Process and merge
        # For now, we'll return a simplified implementation

        raise NotImplementedError(
            "Full contract signature processing requires file storage integration. "
            "Implement file download from URLs and image-to-PDF conversion based on your storage solution."
        )


# Create singleton instance
pdf_service = PDFService()
