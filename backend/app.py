import os
import shutil
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from backend.rag_engine import RAGManager, build_rag_agent, COURSES_DIR
from backend.scanner import list_workspace_documents

app = FastAPI(title="AI Learning Assistant API", version="2.0.0")

# CORS middleware for development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global RAG Manager instance
rag_manager = RAGManager()

class APIKeyRequest(BaseModel):
    api_key: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = []
    api_key: Optional[str] = None

class DeleteDocumentRequest(BaseModel):
    filepath: str

class ClearDatabaseRequest(BaseModel):
    delete_files: Optional[bool] = True

# Global progress tracker
indexing_progress = {
    "status": "idle",
    "current": 0,
    "total": 0,
    "percent": 0,
    "message": "Ready"
}

def update_progress_callback(current, total, percent, message):
    indexing_progress["current"] = current
    indexing_progress["total"] = total
    indexing_progress["percent"] = percent
    indexing_progress["message"] = message
    indexing_progress["status"] = "completed" if percent >= 100 else "indexing"

@app.get("/api/stats")
async def get_system_stats():
    """Retrieve database, file, and API key status."""
    return rag_manager.get_stats()

@app.post("/api/config/api-key")
async def set_api_key(req: APIKeyRequest):
    """Set or update the Google Gemini API key dynamically."""
    key = req.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key cannot be empty.")
    rag_manager.update_api_key(key)
    try:
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        with open(env_path, "w") as f:
            f.write(f"GOOGLE_API_KEY={key}\n")
    except Exception as e:
        print(f"Warning: Could not save API key to .env: {e}")
    return {"status": "success", "message": "API key updated successfully."}

@app.delete("/api/config/api-key")
async def clear_api_key():
    """Clear configured API key."""
    rag_manager.clear_api_key()
    try:
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path, "w") as f:
                f.write("GOOGLE_API_KEY=\n")
    except Exception:
        pass
    return {"status": "success", "message": "API key cleared."}

@app.get("/api/documents/reindex/progress")
async def get_reindex_progress():
    """Fetch real-time indexing progress percentage."""
    return indexing_progress

@app.get("/api/documents")
async def get_documents():
    """List all documents currently in the course workspace."""
    docs = list_workspace_documents(COURSES_DIR)
    return {"documents": docs, "count": len(docs)}

@app.get("/api/documents/preview")
async def preview_document(filepath: str = Query(..., description="Path to document file")):
    """Fetch content of a document file for previewing."""
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found.")
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(50000)  # Read up to 50KB for safe modal viewing
        return {
            "filename": os.path.basename(filepath),
            "filepath": filepath,
            "content": content
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read document: {str(e)}")

@app.post("/api/documents/upload")
async def upload_documents(
    files: List[UploadFile] = File(...),
    relative_paths: Optional[List[str]] = Form(None),
    course: str = Form("General")
):
    """Upload new study documents/folders and ingest into vector database."""
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    uploaded_summary = []
    
    # Process files and optional folder relative paths
    for idx, file in enumerate(files):
        rel_path = relative_paths[idx] if relative_paths and idx < len(relative_paths) else file.filename
        # Normalize relative path separators
        rel_path = rel_path.replace("\\", "/").strip("/")

        path_parts = rel_path.split("/")
        if len(path_parts) > 1:
            # First directory level is detected as course folder
            course_name = path_parts[0]
            sub_path = os.path.join(*path_parts)
        else:
            course_name = "".join(c for c in course if c.isalnum() or c in ("-", "_", " ")).strip() or "General"
            sub_path = os.path.join(course_name, file.filename)

        full_dest_path = os.path.join(COURSES_DIR, sub_path)
        os.makedirs(os.path.dirname(full_dest_path), exist_ok=True)

        with open(full_dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Ingest file into vector DB if API key is active
        ingest_res = {"status": "saved"}
        if rag_manager.api_key:
            try:
                ingest_res = rag_manager.ingest_single_file(full_dest_path, course_name=course_name)
            except Exception as e:
                ingest_res = {"status": "saved_unindexed", "error": str(e)}

        uploaded_summary.append({
            "filename": os.path.basename(full_dest_path),
            "filepath": full_dest_path,
            "course": course_name,
            "ingest_result": ingest_res
        })

    return {
        "status": "success",
        "message": f"Successfully uploaded {len(files)} document(s)/file(s) across folders.",
        "files": uploaded_summary
    }

@app.post("/api/documents/delete")
async def delete_document(req: DeleteDocumentRequest):
    """Delete a document file from the workspace."""
    filepath = req.filepath
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File does not exist.")

    try:
        os.remove(filepath)
        # Clean up empty parent dir if not root COURSES_DIR
        parent = os.path.dirname(filepath)
        if parent != COURSES_DIR and os.path.exists(parent) and not os.listdir(parent):
            os.rmdir(parent)

        return {"status": "success", "message": f"File {os.path.basename(filepath)} deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")

@app.post("/api/documents/reindex")
async def reindex_documents():
    """Rebuild the vector database from all workspace documents."""
    if not rag_manager.api_key:
        raise HTTPException(status_code=400, detail="Google Gemini API key required. Please configure API key in Settings.")

    try:
        res = rag_manager.index_all_documents(progress_callback=update_progress_callback)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Re-indexing failed: {str(e)}")

@app.post("/api/documents/clear")
async def clear_database(req: Optional[ClearDatabaseRequest] = None):
    """Completely clear vector database and optionally wipe uploaded course files."""
    delete_files = req.delete_files if (req and req.delete_files is not None) else True
    try:
        res = rag_manager.clear_database(delete_files=delete_files)
        # Reset indexing progress tracker
        indexing_progress["status"] = "idle"
        indexing_progress["current"] = 0
        indexing_progress["total"] = 0
        indexing_progress["percent"] = 0
        indexing_progress["message"] = "Database cleared."

        # Fetch remaining workspace documents
        docs = list_workspace_documents(COURSES_DIR)
        res["documents"] = docs
        res["documents_count"] = len(docs)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear database: {str(e)}")


def sanitize_chat_history(history: List[Dict[str, str]], current_message: str) -> List[Any]:
    """Clean and build strictly alternating user-assistant message sequence."""
    formatted = []
    for msg in history or []:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if not content or content.startswith("⚠️"):
            continue

        if role == "user":
            if formatted and isinstance(formatted[-1], HumanMessage):
                formatted[-1] = HumanMessage(content=formatted[-1].content + "\n" + content)
            else:
                formatted.append(HumanMessage(content=content))
        elif role == "assistant":
            if formatted and isinstance(formatted[-1], HumanMessage):
                formatted.append(AIMessage(content=content))
            elif formatted and isinstance(formatted[-1], AIMessage):
                formatted[-1] = AIMessage(content=formatted[-1].content + "\n" + content)

    # Discard trailing user message without an assistant reply
    if formatted and isinstance(formatted[-1], HumanMessage):
        formatted.pop()

    current_prompt = current_message.strip() if current_message else "Hello"
    formatted.append(HumanMessage(content=current_prompt))
    return formatted

@app.post("/api/chat")
async def chat_with_assistant(req: ChatRequest):
    """Process prompt through LangGraph RAG agent workflow."""
    if req.api_key:
        rag_manager.update_api_key(req.api_key)

    if not rag_manager.api_key:
        raise HTTPException(
            status_code=400,
            detail="Google Gemini API Key missing. Please click the API Key button in top right corner to set your key."
        )

    try:
        agent = build_rag_agent(rag_manager)

        # Build clean, strictly alternating history payload
        formatted_messages = sanitize_chat_history(req.history, req.message)

        # Execute graph workflow
        result = agent.invoke({
            "messages": formatted_messages,
            "citations": [],
            "tool_calls_history": []
        })

        last_message = result["messages"][-1]
        response_text = last_message.content if hasattr(last_message, "content") else str(last_message)
        citations = result.get("citations", [])
        tool_history = result.get("tool_calls_history", [])

        return {
            "response": response_text,
            "citations": citations,
            "tool_calls": tool_history
        }

    except Exception as e:
        print(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=f"AI Agent error: {str(e)}")

# Mount static files for Frontend UI
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
