import os
import subprocess
import tempfile
from typing import List, Dict, Any, Optional
from langchain_community.document_loaders import (
    PyPDFLoader, TextLoader, PythonLoader,
    Docx2txtLoader, UnstructuredWordDocumentLoader,
    UnstructuredMarkdownLoader, UnstructuredFileLoader,
    UnstructuredPDFLoader
)
from langchain_core.documents import Document

SUPPORTED_EXTENSIONS = {
    ".pdf": "PDF Document",
    ".py": "Python Source Code",
    ".txt": "Text File",
    ".docx": "Word Document",
    ".md": "Markdown Document",
    ".R": "R Script",
    ".Rmd": "R Markdown Document"
}

def extract_scanned_pdf_ocr(file_path: str) -> List[Document]:
    """Perform OCR on scanned / image-based PDF using pypdfium2 page rendering and Tesseract OCR."""
    docs = []
    tess_bin = "/opt/homebrew/bin/tesseract" if os.path.exists("/opt/homebrew/bin/tesseract") else "tesseract"
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(file_path)
        for page_idx in range(len(pdf)):
            page = pdf[page_idx]
            image = page.render(scale=2).to_pil()
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                image.save(tmp.name)
                tmp_path = tmp.name
            try:
                cmd = [tess_bin, tmp_path, "stdout", "-l", "eng"]
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                page_text = res.stdout.strip()
            except Exception as ocr_err:
                print(f"OCR error on page {page_idx + 1} of {os.path.basename(file_path)}: {ocr_err}")
                page_text = ""
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

            if page_text:
                doc = Document(
                    page_content=page_text,
                    metadata={"page": page_idx + 1, "is_ocr": True}
                )
                docs.append(doc)
    except Exception as e:
        print(f"Failed to process scanned PDF with OCR ({file_path}): {e}")
    return docs

def load_single_file(file_path: str, course_name: Optional[str] = None) -> List[Document]:
    """Load and parse a single document file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        # Fallback to TextLoader for text-based unknown extensions
        try:
            loader = TextLoader(file_path, encoding='utf-8', autodetect_encoding=True)
            docs = loader.load()
        except Exception as e:
            print(f"Skipping unsupported file type {ext}: {e}")
            return []
    elif ext == ".pdf":
        try:
            loader = PyPDFLoader(file_path)
            docs = loader.load()
        except Exception:
            try:
                loader = UnstructuredPDFLoader(file_path)
                docs = loader.load()
            except Exception:
                docs = []
        
        # Detect image-based or scanned PDFs where standard text extraction yields minimal text
        total_text = "".join([d.page_content.strip() for d in docs])
        if len(total_text) < 50:
            print(f"📄 Detected scanned/image-based PDF ({os.path.basename(file_path)}). Running OCR fallback...")
            ocr_docs = extract_scanned_pdf_ocr(file_path)
            if ocr_docs:
                docs = ocr_docs

    elif ext == ".py":
        loader = PythonLoader(file_path)
        docs = loader.load()
    elif ext == ".txt" or ext == ".r":
        loader = TextLoader(file_path, encoding='utf-8', autodetect_encoding=True)
        docs = loader.load()
    elif ext == ".docx":
        try:
            loader = Docx2txtLoader(file_path)
            docs = loader.load()
        except Exception:
            loader = UnstructuredWordDocumentLoader(file_path)
            docs = loader.load()
    elif ext == ".md":
        try:
            loader = UnstructuredMarkdownLoader(file_path)
            docs = loader.load()
        except Exception:
            loader = TextLoader(file_path, encoding='utf-8', autodetect_encoding=True)
            docs = loader.load()
    elif ext == ".rmd":
        loader = UnstructuredFileLoader(file_path)
        docs = loader.load()
    else:
        loader = TextLoader(file_path, encoding='utf-8', autodetect_encoding=True)
        docs = loader.load()

    # Determine course folder name
    if not course_name:
        parent_dir = os.path.basename(os.path.dirname(file_path))
        course_name = parent_dir if parent_dir != "GT-Courses" else "General"

    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    for doc in docs:
        doc.metadata["file_path"] = file_path
        doc.metadata["filename"] = filename
        doc.metadata["course"] = course_name
        doc.metadata["file_type"] = SUPPORTED_EXTENSIONS.get(ext, "Other File")
        doc.metadata["file_size"] = file_size

    return docs

def scan_courses_dir(base_dir: str = "GT-Courses") -> List[Document]:
    """Scan all files inside the specified courses folder."""
    all_docs = []
    if not os.path.exists(base_dir):
        os.makedirs(base_dir, exist_ok=True)
        return all_docs

    IGNORE_DIRS = {".venv", "venv", "node_modules", "__pycache__", ".git", ".idea", ".vscode", "env", "site-packages", "dist", "build"}
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for file in files:
            if file.startswith("."):
                continue  # Skip hidden files
            file_path = os.path.join(root, file)
            ext = os.path.splitext(file)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                try:
                    course = os.path.relpath(root, base_dir).split(os.sep)[0]
                    if course == ".":
                        course = "General"
                    docs = load_single_file(file_path, course_name=course)
                    rel_path = os.path.relpath(file_path, base_dir)
                    for d in docs:
                        d.metadata["original_path"] = rel_path
                    all_docs.extend(docs)
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")

    return all_docs

def list_workspace_documents(base_dir: str = "GT-Courses") -> List[Dict[str, Any]]:
    """Get metadata for all files in the courses directory."""
    file_list = []
    if not os.path.exists(base_dir):
        return file_list

    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.startswith("."):
                continue
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, base_dir)
            ext = os.path.splitext(file)[1].lower()
            course = os.path.relpath(root, base_dir).split(os.sep)[0]
            if course == ".":
                course = "General"

            size_bytes = os.path.getsize(full_path)
            file_list.append({
                "filename": file,
                "relative_path": rel_path,
                "full_path": full_path,
                "course": course,
                "extension": ext,
                "file_type": SUPPORTED_EXTENSIONS.get(ext, "Document"),
                "size_bytes": size_bytes,
                "size_formatted": f"{round(size_bytes / 1024, 1)} KB" if size_bytes < 1024 * 1024 else f"{round(size_bytes / (1024 * 1024), 2)} MB"
            })
    return file_list
