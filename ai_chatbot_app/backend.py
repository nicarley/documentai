from pathlib import Path
import os
import shutil
import json
import requests

from langchain.chains import RetrievalQA
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader, UnstructuredExcelLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.prompts import PromptTemplate

class ChatbotBackend:
    """
    Handles the RAG (Retrieval-Augmented Generation) logic.
    - Loads documents from a specified directory.
    - Creates a separate vector store for each document.
    - Sets up a retrieval chain to answer questions based on a selected document.
    """

    def __init__(self, docs_folder_path: str, vector_store_path: str = "faiss_index", ollama_base_url: str = "http://localhost:11434"):
        """
        Initializes the backend.

        Args:
            docs_folder_path (str): Path to the folder containing documents.
            vector_store_path (str): Path to the root directory for FAISS vector stores.
            ollama_base_url (str): The base URL of the Ollama server.
        """
        self.docs_folder_path = Path(docs_folder_path)
        self.vector_store_path = Path(vector_store_path)
        self.vector_store_path.mkdir(exist_ok=True)
        
        self.ollama_base_url = ollama_base_url

        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.qa_chains = {}

    def update_ollama_url(self, new_url: str):
        self.ollama_base_url = new_url
        # Clear existing QA chains as they depend on the Ollama URL
        self.qa_chains = {}

    def get_ollama_models(self) -> list[str]:
        """
        Fetches the list of available models from the Ollama server.
        """
        if not self.ollama_base_url:
            return []
        try:
            # Adjust the endpoint to match the Ollama API for listing local models
            response = requests.get(f"{self.ollama_base_url}/api/tags")
            response.raise_for_status()
            models_data = response.json().get("models", [])
            return sorted([model["name"] for model in models_data])
        except requests.exceptions.RequestException as e:
            print(f"Could not connect to Ollama server at {self.ollama_base_url}. Error: {e}")
            return []

    def get_document_name(self, doc_path: Path) -> str:
        """Returns the document name from a document path (filename without extension)."""
        return doc_path.stem

    def get_vector_store_for_document(self, document_name: str) -> Path:
        """Returns the path to the vector store for a given document."""
        return self.vector_store_path / document_name

    def setup_vector_stores(self):
        """
        Creates or loads vector stores for each document in the docs folder.
        """
        print("Setting up vector stores...")
        doc_files = (
            list(self.docs_folder_path.glob("**/*.pdf")) + 
            list(self.docs_folder_path.glob("**/*.docx")) + 
            list(self.docs_folder_path.glob("**/*.txt")) +
            list(self.docs_folder_path.glob("**/*.xls")) +
            list(self.docs_folder_path.glob("**/*.xlsx"))
        )

        if not doc_files:
            print(f"No documents found in {self.docs_folder_path}")
            return

        for doc_path in doc_files:
            document_name = self.get_document_name(doc_path)
            document_vector_store_path = self.get_vector_store_for_document(document_name)

            if document_vector_store_path.exists():
                print(f"Vector store for {document_name} already exists. Skipping creation.")
            else:
                print(f"Creating vector store for {document_name}...")
                try:
                    if doc_path.suffix.lower() == '.pdf':
                        loader = PyPDFLoader(str(doc_path))
                    elif doc_path.suffix.lower() == '.docx':
                        loader = Docx2txtLoader(str(doc_path))
                    elif doc_path.suffix.lower() == '.txt':
                        loader = TextLoader(str(doc_path))
                    elif doc_path.suffix.lower() in ['.xls', '.xlsx']:
                        loader = UnstructuredExcelLoader(str(doc_path), mode="elements")
                    else:
                        continue

                    documents = loader.load()
                    if not documents:
                        print(f"Warning: No content loaded from {doc_path.name}. Skipping.")
                        continue
                    
                    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
                    texts = text_splitter.split_documents(documents)
                    
                    db = FAISS.from_documents(texts, self.embeddings)
                    db.save_local(str(document_vector_store_path))
                    print(f"Saved vector store for {document_name}.")

                except Exception as e:
                    print(f"Error processing {doc_path.name}: {e}")

        print("Vector stores are ready.")

    def get_available_documents(self) -> list[str]:
        """
        Scans the documents folder and returns a list of available document names.
        A document name is the filename without its extension.
        """
        documents = set()
        supported_extensions = ['.pdf', '.docx', '.txt', '.xls', '.xlsx']
        for ext in supported_extensions:
            for doc_path in self.docs_folder_path.glob(f"**/*{ext}"):
                documents.add(doc_path.stem)
        return sorted(list(documents))

    def delete_document(self, document_name: str):
        """
        Deletes a document and its associated vector store.
        """
        # Find and delete the document file
        doc_path = None
        for ext in ['.pdf', '.docx', '.txt', '.xls', '.xlsx']:
            path = self.docs_folder_path / f"{document_name}{ext}"
            if path.exists():
                doc_path = path
                break
        if doc_path:
            doc_path.unlink()

        # Delete the vector store
        vector_store_path = self.get_vector_store_for_document(document_name)
        if vector_store_path.exists():
            shutil.rmtree(vector_store_path)

        # Remove from QA chains
        if document_name in self.qa_chains:
            del self.qa_chains[document_name]

    def setup_qa_chain(self, document_name: str, ollama_model: str):
        """
        Sets up the Question-Answerin g chain for a specific document.
        """
        # Re-initialize LLM with the selected model
        llm = OllamaLLM(model=ollama_model, base_url=self.ollama_base_url, request_timeout=10.0)

        print(f"Setting up QA chain for {document_name}...")
        document_vector_store_path = self.get_vector_store_for_document(document_name)

        if not document_vector_store_path.exists():
            raise ValueError(f"Vector store for document '{document_name}' not found.")

        db = FAISS.load_local(str(document_vector_store_path), self.embeddings, allow_dangerous_deserialization=True)
        retriever = db.as_retriever(search_kwargs={"k": 3})

        # Define a more verbose prompt
        prompt_template = """Use the following pieces of context to answer the user's question.
Provide a detailed and comprehensive answer based on the context.
If you don't know the answer, just say that you don't know, don't try to make up an answer.

Context: {context}
Question: {question}

Helpful and detailed answer:"""
        PROMPT = PromptTemplate(
            template=prompt_template, input_variables=["context", "question"]
        )
        chain_type_kwargs = {"prompt": PROMPT}

        self.qa_chains[document_name] = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever,
            return_source_documents=True,
            chain_type_kwargs=chain_type_kwargs
        )
        print(f"QA chain for {document_name} is ready.")

    def ask(self, question: str, document_name: str, ollama_model: str) -> str:
        """
        Asks a question to the QA chain for a specific document.
        """
        if document_name not in self.qa_chains:
            self.setup_qa_chain(document_name, ollama_model)

        qa_chain = self.qa_chains.get(document_name)
        if not qa_chain:
            return f"Error: QA chain for document '{document_name}' is not initialized."

        response = qa_chain.invoke({"query": question})
        return response.get("result", "Sorry, I could not find an answer.")
