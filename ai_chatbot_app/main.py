import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
import json

from .gui import ChatWindow
from .backend import ChatbotBackend

def main():
    # --- Define paths ---
    # Assumes the 'AI' folder is in the parent directory of this app
    project_root = Path(__file__).parent.parent
    docs_folder = project_root / "AIDocs"
    vector_store_folder = project_root / "ai_chatbot_app" / "faiss_index"
    settings_file = project_root / "settings.json"

    # --- Load settings ---
    ollama_server_address = "http://localhost:11434" # Default value
    ollama_model = "" # Default value
    try:
        with open(settings_file, 'r') as f:
            settings = json.load(f)
            ollama_server_address = settings.get("ollama_server_address", ollama_server_address)
            ollama_model = settings.get("ollama_model", ollama_model)
    except (FileNotFoundError, json.JSONDecodeError):
        pass # Use default if file not found or corrupted

    # --- Initialize Application ---
    app = QApplication(sys.argv)

    # --- Initialize Backend and Frontend ---
    backend = ChatbotBackend(docs_folder_path=str(docs_folder), vector_store_path=str(vector_store_folder), ollama_base_url=ollama_server_address)
    window = ChatWindow(backend, initial_ollama_model=ollama_model)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()