#!/usr/bin/env python3
"""
Create a test PDF for testing PDF upload and preview
"""

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    
    def create_test_pdf():
        filename = "test_document.pdf"
        
        # Create PDF
        c = canvas.Canvas(filename, pagesize=letter)
        width, height = letter
        
        # Add title
        c.setFont("Helvetica-Bold", 24)
        c.drawString(50, height - 100, "Second Brain PDF Test")
        
        # Add content
        c.setFont("Helvetica", 12)
        content = [
            "This is a test PDF document for the Second Brain application.",
            "",
            "Features being tested:",
            "• PDF text extraction",
            "• PDF preview in browser",
            "• File upload and storage",
            "• Document search indexing",
            "",
            "Page 1 of 2"
        ]
        
        y = height - 150
        for line in content:
            c.drawString(50, y, line)
            y -= 20
        
        # Add a new page
        c.showPage()
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50, height - 100, "Second Page Content")
        
        c.setFont("Helvetica", 12)
        page2_content = [
            "This is the second page of the test PDF.",
            "",
            "Additional test content:",
            "- Multi-page document handling",
            "- Text extraction from multiple pages",
            "- PDF metadata processing",
            "",
            "End of test document."
        ]
        
        y = height - 150
        for line in page2_content:
            c.drawString(50, y, line)
            y -= 20
        
        c.save()
        print(f"✅ Created {filename}")
        
        # Return file size
        import os
        size = os.path.getsize(filename)
        print(f"📁 File size: {size} bytes")
        
        return filename

except ImportError:
    def create_test_pdf():
        print("❌ reportlab not available. Creating simple text file instead.")
        filename = "test_document.txt"
        with open(filename, 'w') as f:
            f.write("""Second Brain Document Test

This is a test document for the Second Brain application.

Features being tested:
• Document text extraction
• File upload and storage  
• Document search indexing

This would be a PDF in production.
""")
        print(f"✅ Created {filename} (text fallback)")
        return filename

if __name__ == "__main__":
    create_test_pdf()