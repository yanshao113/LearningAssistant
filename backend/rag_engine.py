import os
import shutil
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Sequence, TypedDict
from dotenv import load_dotenv

from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END

from backend.scanner import scan_courses_dir, load_single_file, list_workspace_documents

import hashlib
load_dotenv()

DB_DIR = "courses_db"
COLLECTION_NAME = "courses_768d"
COURSES_DIR = "GT-Courses"

def generate_chunk_id(file_path: str, chunk_index: int) -> str:
    """Generate a deterministic hash ID for a document chunk to prevent duplicates."""
    normalized_path = file_path.replace("\\", "/").strip("/")
    return hashlib.md5(f"{normalized_path}_chunk_{chunk_index}".encode("utf-8")).hexdigest()

from langchain_core.embeddings import Embeddings
import chromadb.utils.embedding_functions as ef

class LocalChromaEmbeddings(Embeddings):
    def __init__(self, target_dim: int = 768):
        self.ef = ef.DefaultEmbeddingFunction()
        self.target_dim = target_dim

    def _pad(self, vec: List[float]) -> List[float]:
        vec_list = [float(x) for x in vec]
        if len(vec_list) < self.target_dim:
            return vec_list + [0.0] * (self.target_dim - len(vec_list))
        return vec_list[:self.target_dim]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        res = self.ef(texts)
        return [self._pad(e) for e in res]

    def embed_query(self, text: str) -> List[float]:
        res = self.ef([text])
        return self._pad(res[0])

def create_embeddings_instance(api_key: str):
    """
    Attempts to initialize Google Generative AI Embeddings across supported model names.
    Falls back gracefully to LocalChromaEmbeddings if Google API key has no embedContent access.
    """
    models_to_try = [
        "models/text-embedding-004",
        "text-embedding-004",
        "models/embedding-001",
        "embedding-001"
    ]
    
    if api_key:
        for m in models_to_try:
            try:
                emb = GoogleGenerativeAIEmbeddings(model=m, google_api_key=api_key)
                emb.embed_query("test connection")
                print(f"✅ Successfully initialized Google embeddings model: {m}")
                return emb
            except Exception as e:
                print(f"⚠️ Google embedding model {m} failed: {e}")

    print("🔄 Switching to local ONNX embeddings (LocalChromaEmbeddings)...")
    return LocalChromaEmbeddings()

class RAGManager:
    def __init__(self, custom_api_key: Optional[str] = None):
        self.api_key = custom_api_key or os.getenv('GOOGLE_API_KEY', '')
        self.vector_db = None
        self.retriever = None
        self.embeddings = None
        if self.api_key:
            self._init_vector_db()

    def update_api_key(self, api_key: str):
        """Update API key dynamically and re-initialize components."""
        self.api_key = api_key.strip()
        os.environ['GOOGLE_API_KEY'] = self.api_key
        self._init_vector_db()

    def clear_api_key(self):
        """Clear active Google API Key and reset vector database references."""
        self.api_key = None
        self.vector_db = None
        self.retriever = None
        os.environ.pop('GOOGLE_API_KEY', None)
        self.embeddings = None

    def _init_vector_db(self):
        """Initialize embeddings and load existing ChromaDB vector database."""
        if not self.api_key:
            return
        try:
            self.embeddings = create_embeddings_instance(self.api_key)
            if os.path.exists(DB_DIR):
                self.vector_db = Chroma(
                    persist_directory=DB_DIR,
                    embedding_function=self.embeddings,
                    collection_name=COLLECTION_NAME
                )
                self.retriever = self.vector_db.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": 5}
                )
        except Exception as e:
            print(f"Error initializing vector DB: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Fetch current stats about vector store and course documents."""
        docs = list_workspace_documents(COURSES_DIR)
        total_files = len(docs)
        courses = list(set(d["course"] for d in docs))
        
        chunk_count = 0
        if self.vector_db and hasattr(self.vector_db, '_collection'):
            try:
                chunk_count = self.vector_db._collection.count()
            except Exception:
                chunk_count = 0

        return {
            "total_files": total_files,
            "total_chunks": chunk_count,
            "courses_count": len(courses),
            "courses_list": courses,
            "has_api_key": bool(self.api_key),
            "db_initialized": self.vector_db is not None
        }

    def index_all_documents(self, progress_callback=None) -> Dict[str, Any]:
        """Scan all documents in GT-Courses and save chunks to ChromaDB with progress reporting."""
        if not self.api_key:
            raise ValueError("Google Gemini API Key is missing. Please set your API Key in Settings.")

        all_docs = scan_courses_dir(COURSES_DIR)
        if not all_docs:
            if self.vector_db:
                try:
                    self.vector_db.delete_collection()
                except Exception:
                    pass
                self.vector_db = None
                self.retriever = None
            if progress_callback:
                progress_callback(0, 0, 100, "Knowledge base is empty.")
            return {"status": "warning", "message": "Knowledge base is empty. Upload course documents to build your vector database.", "chunks_stored": 0}

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=5000,
            chunk_overlap=800,
            separators=["\n\n", "\n", " "]
        )

        splits = text_splitter.split_documents(all_docs)
        total_chunks = len(splits)

        if progress_callback:
            progress_callback(0, total_chunks, 0, f"Split {len(all_docs)} documents into {total_chunks} chunks.")

        # Re-initialize embeddings if needed
        if not self.embeddings:
            self.embeddings = create_embeddings_instance(self.api_key)

        # Clear existing collection if present
        if self.vector_db:
            try:
                self.vector_db.delete_collection()
            except Exception:
                pass
            self.vector_db = None
            self.retriever = None

        batch_size = 50
        first_batch = splits[:batch_size]
        first_ids = [generate_chunk_id(doc.metadata.get("file_path", "doc"), idx) for idx, doc in enumerate(first_batch)]

        self.vector_db = Chroma.from_documents(
            documents=first_batch,
            ids=first_ids,
            embedding=self.embeddings,
            persist_directory=DB_DIR,
            collection_name=COLLECTION_NAME
        )

        processed = len(first_batch)
        if progress_callback:
            percent = int((processed / total_chunks) * 100)
            progress_callback(processed, total_chunks, percent, f"Indexed {processed}/{total_chunks} chunks ({percent}%)")

        for i in range(batch_size, len(splits), batch_size):
            batch = splits[i:i + batch_size]
            batch_ids = [generate_chunk_id(doc.metadata.get("file_path", "doc"), i + idx) for idx, doc in enumerate(batch)]
            try:
                self.vector_db.add_documents(batch, ids=batch_ids)
                processed += len(batch)
                if progress_callback:
                    percent = int((processed / total_chunks) * 100)
                    progress_callback(processed, total_chunks, percent, f"Indexed {processed}/{total_chunks} chunks ({percent}%)")
            except Exception as e:
                print(f"Error indexing batch {i}-{i+batch_size}: {e}")

        self.retriever = self.vector_db.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 5}
        )

        chunk_count = self.vector_db._collection.count() if hasattr(self.vector_db, '_collection') else len(splits)
        if progress_callback:
            progress_callback(chunk_count, total_chunks, 100, f"Indexing complete! {chunk_count} chunks active.")

        return {
            "status": "success",
            "message": f"Successfully indexed {len(all_docs)} source documents into {chunk_count} vector chunks.",
            "source_docs": len(all_docs),
            "chunks_stored": chunk_count
        }

    def ingest_single_file(self, file_path: str, course_name: str = "General") -> Dict[str, Any]:
        """Parse and ingest a newly uploaded single file into vector store."""
        if not self.api_key:
            raise ValueError("Google Gemini API Key is missing.")

        docs = load_single_file(file_path, course_name=course_name)
        if not docs:
            return {"status": "error", "message": f"Could not parse document content from {file_path}"}

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=5000,
            chunk_overlap=800,
            separators=["\n\n", "\n", " "]
        )

        splits = text_splitter.split_documents(docs)

        if not self.embeddings:
            self.embeddings = create_embeddings_instance(self.api_key)

        if not self.vector_db:
            self.vector_db = Chroma(
                persist_directory=DB_DIR,
                embedding_function=self.embeddings,
                collection_name=COLLECTION_NAME
            )

        chunk_ids = [generate_chunk_id(file_path, idx) for idx in range(len(splits))]
        self.vector_db.add_documents(splits, ids=chunk_ids)
        self.retriever = self.vector_db.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 5}
        )

        return {
            "status": "success",
            "filename": os.path.basename(file_path),
            "chunks_added": len(splits),
            "total_chunks": self.vector_db._collection.count()
        }

    def search_similar(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search vector database for passages matching query."""
        if not self.vector_db:
            return []
        docs = self.vector_db.similarity_search(query, k=top_k)
        results = []
        for doc in docs:
            results.append({
                "content": doc.page_content,
                "file_path": doc.metadata.get("file_path", "Unknown"),
                "filename": doc.metadata.get("filename", os.path.basename(doc.metadata.get("file_path", ""))),
                "course": doc.metadata.get("course", "General"),
                "chunk_length": len(doc.page_content)
            })
        return results

    def clear_database(self, delete_files: bool = True) -> Dict[str, Any]:
        """Completely delete vector store contents and optionally wipe workspace documents."""
        # 1. Reset vector store collection
        if self.vector_db:
            try:
                self.vector_db.delete_collection()
            except Exception as e:
                print(f"Warning deleting collection: {e}")
            self.vector_db = None
            self.retriever = None

        # 2. Clean persistent DB folder
        if os.path.exists(DB_DIR):
            try:
                shutil.rmtree(DB_DIR)
            except Exception as e:
                print(f"Warning removing DB_DIR: {e}")

        # 3. Optionally delete raw workspace document files
        deleted_files_count = 0
        if delete_files and os.path.exists(COURSES_DIR):
            try:
                for item in os.listdir(COURSES_DIR):
                    item_path = os.path.join(COURSES_DIR, item)
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        deleted_files_count += 1
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        deleted_files_count += 1
            except Exception as e:
                print(f"Warning clearing GT-Courses folder: {e}")

        # Re-init vector DB reference if API key exists
        if self.api_key:
            try:
                self._init_vector_db()
            except Exception:
                pass

        stats = self.get_stats()
        return {
            "status": "success",
            "message": "Knowledge base & workspace files purged successfully." if delete_files else "Vector database index reset to 0 chunks.",
            "delete_files": delete_files,
            "deleted_files_count": deleted_files_count,
            "stats": stats
        }



class AgentState(TypedDict):
    messages: Sequence[BaseMessage]
    citations: List[Dict[str, Any]]
    tool_calls_history: List[Dict[str, Any]]


def build_rag_agent(rag_manager: RAGManager):
    """Build and return a LangGraph workflow instance for handling RAG queries."""

    @tool
    def retrieve_tool(query: str) -> str:
        """Searches and returns relevant information from the course notes vector store."""
        if not rag_manager.retriever:
            return "No vector database found. Please upload course documents and re-index."

        docs = rag_manager.retriever.invoke(query)
        if not docs:
            return "No relevant information found in the course notes."

        results = []
        for doc in docs:
            file_path = doc.metadata.get('file_path', 'Unknown file')
            filename = doc.metadata.get('filename', os.path.basename(file_path))
            course = doc.metadata.get('course', 'General')
            content = doc.page_content
            formatted = f"=== SOURCE FILE: {filename} (Course: {course}, Path: {file_path}) ===\n{content}"
    """Build and return an agent for handling study questions using Direct RAG Execution."""
    if not rag_manager.api_key:
        raise ValueError("Google Gemini API Key is required to run the AI assistant.")

    # Use robust gemini-flash-lite-latest model with full free-tier quota
    llm = ChatGoogleGenerativeAI(
        model="gemini-flash-lite-latest",
        google_api_key=rag_manager.api_key,
        temperature=0.2
    )

    def execute_rag(state: AgentState) -> AgentState:
        messages = list(state['messages'])
        citations = list(state.get("citations", []))
        tool_history = list(state.get("tool_calls_history", []))

        # Find user query from messages
        user_query = "Help me review course materials."
        for m in reversed(messages):
            if isinstance(m, HumanMessage) and getattr(m, "content", "").strip():
                user_query = m.content.strip()
                break

        # 1. Retrieve relevant course materials from vector DB with smart course detection
        context_parts = []
        if rag_manager.vector_db:
            try:
                # Detect if the query targets a specific course
                q_lower = user_query.lower()
                target_course = None
                if any(k in q_lower for k in ["computer network", "computer networks", "networking", "cn", "cs 6250", "cs6250"]):
                    target_course = "CN"
                elif any(k in q_lower for k in ["analytics modeling", "isye 6501", "isye6501", "iam", "isye"]):
                    target_course = "IAM"

                found_docs = []
                if target_course:
                    try:
                        found_docs = rag_manager.vector_db.similarity_search(user_query, k=6, filter={"course": target_course})
                    except Exception:
                        found_docs = []

                # Fallback to global similarity search if course filter returned no results or no course was targeted
                if not found_docs:
                    found_docs = rag_manager.vector_db.similarity_search(user_query, k=6)

                for d in found_docs:
                    fp = d.metadata.get("file_path", "Unknown file")
                    fn = d.metadata.get("filename", os.path.basename(fp))
                    orig_path = d.metadata.get("original_path") or (os.path.relpath(fp, COURSES_DIR) if os.path.exists(fp) else fp)
                    course = d.metadata.get("course", "General")
                    content = d.page_content
                    context_parts.append(f"=== ORIGINAL SOURCE FILE: {orig_path} (Course: {course}) ===\n{content}")

                    citation_obj = {
                        "filename": fn,
                        "original_path": orig_path,
                        "file_path": fp,
                        "course": course,
                        "snippet": content[:300] + "..."
                    }
                    if citation_obj not in citations:
                        citations.append(citation_obj)

                tool_history.append({
                    "tool": "vector_search",
                    "query": user_query,
                    "target_course": target_course or "All Courses",
                    "result_preview": f"Retrieved {len(found_docs)} matching documents.",
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                print(f"Warning: Vector search failed: {e}")

        context_str = "\n\n".join(context_parts) if context_parts else "No specific vector documents found."

        # 2. Construct System Prompt with Course Context
        system_prompt = (
            "You are an intelligent, friendly AI Study & Learning Assistant.\n"
            "Your primary role is to help students learn course material, understand complex topics, solve study problems, "
            "and review lecture/notes content based on the documents loaded into your knowledge base.\n\n"
            "GUIDELINES:\n"
            "1. Answer based on the provided course documents below.\n"
            "2. Provide clear, structured, and insightful answers using markdown (headers, bullet points, code snippets, LaTeX for math formulas).\n"
            "3. At the end of your response, include a clear '**Referenced Source Documents:**' section that lists the exact ORIGINAL file paths (e.g. `IAM/4homeworks/hw9/1hw_description/homework header 9.docx`).\n\n"
            f"=== COURSE MATERIALS KNOWLEDGE BASE ===\n{context_str}"
        )

        # 3. Direct LLM Invocation
        cleaned_history = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                continue
            content = getattr(msg, "content", "")
            if isinstance(content, str) and content.strip():
                if isinstance(msg, HumanMessage):
                    cleaned_history.append(HumanMessage(content=content))
                elif isinstance(msg, AIMessage):
                    cleaned_history.append(AIMessage(content=content))

        final_messages = [SystemMessage(content=system_prompt)] + cleaned_history
        response = llm.invoke(final_messages)

        return {
            "messages": [response],
            "citations": citations,
            "tool_calls_history": tool_history
        }

    workflow = StateGraph(AgentState)
    workflow.add_node("rag_executor", execute_rag)
    workflow.set_entry_point("rag_executor")
    workflow.add_edge("rag_executor", END)

    return workflow.compile()
