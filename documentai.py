import sys
import os
from pathlib import Path
import shutil
import json
import traceback

from PySide6.QtCore import QObject, Signal, Slot, QThread
from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTextBrowser, QLineEdit, QPushButton,
    QHBoxLayout, QLabel, QStatusBar, QComboBox, QFileDialog, QMessageBox, QTabWidget
)

import langchain
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    DirectoryLoader,
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
    UnstructuredExcelLoader,
)
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings
from langchain.chains import RetrievalQA
from langchain_ollama import OllamaLLM

# --- Global Variables ---
AppTitle = "DocumentAI"
HDVersion = "1.0"


# --- Backend Code ---
class ChatbotBackend:
    def __init__(self, docs_folder_path: str, vector_store_path: str, ollama_base_url: str):
        self.docs_folder_path = Path(docs_folder_path)
        self.vector_store_path = Path(vector_store_path)
        self.ollama_base_url = ollama_base_url
        self.llm = None
        self.vector_stores = {}

        self.docs_folder_path.mkdir(exist_ok=True)
        self.vector_store_path.mkdir(exist_ok=True)

    def update_ollama_url(self, new_url: str):
        self.ollama_base_url = new_url

    def get_ollama_models(self):
        try:
            import requests
            response = requests.get(f"{self.ollama_base_url}/api/tags")
            response.raise_for_status()
            models = [model['name'] for model in response.json()['models']]
            return models
        except Exception as e:
            print(f"Error fetching Ollama models: {e}")
            raise

    def setup_vector_stores(self):
        self.vector_stores = {}
        document_names = [f.stem for f in self.docs_folder_path.iterdir() if f.is_file()]

        for doc_name in document_names:
            sanitized_name = self._sanitize_filename(doc_name)
            faiss_index_path = self.vector_store_path / sanitized_name

            if faiss_index_path.exists():
                try:
                    embeddings = OllamaEmbeddings(base_url=self.ollama_base_url, model="llama3")
                    self.vector_stores[doc_name] = FAISS.load_local(str(faiss_index_path), embeddings,
                                                                    allow_dangerous_deserialization=True)
                except Exception as e:
                    print(f"Error loading vector store for {doc_name}: {e}")
            else:
                try:
                    loader = self._get_loader_for_document(doc_name)
                    if loader:
                        docs = loader.load()
                        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
                        texts = text_splitter.split_documents(docs)
                        embeddings = OllamaEmbeddings(base_url=self.ollama_base_url, model="llama3")
                        db = FAISS.from_documents(texts, embeddings)
                        db.save_local(str(faiss_index_path))
                        self.vector_stores[doc_name] = db
                except Exception as e:
                    print(f"Error creating vector store for {doc_name}: {e}")

    def _get_loader_for_document(self, doc_name):
        doc_path = None
        for ext in ['.pdf', '.docx', '.txt', '.xls', '.xlsx']:
            if (self.docs_folder_path / (doc_name + ext)).exists():
                doc_path = self.docs_folder_path / (doc_name + ext)
                break

        if not doc_path:
            return None

        if doc_path.suffix == '.pdf':
            return PyPDFLoader(str(doc_path))
        elif doc_path.suffix == '.docx':
            return Docx2txtLoader(str(doc_path))
        elif doc_path.suffix == '.txt':
            return TextLoader(str(doc_path))
        elif doc_path.suffix in ['.xls', '.xlsx']:
            return UnstructuredExcelLoader(str(doc_path))
        return None

    def ask(self, question: str, document_name: str, ollama_model: str):
        if document_name not in self.vector_stores:
            return "Vector store for the selected document is not ready."

        db = self.vector_stores[document_name]
        self.llm = OllamaLLM(base_url=self.ollama_base_url, model=ollama_model)

        qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=db.as_retriever()
        )
        response = qa_chain.invoke(question)
        return response['result']

    def get_available_documents(self):
        return [f.stem for f in self.docs_folder_path.iterdir() if f.is_file()]

    def delete_document(self, document_name: str):
        sanitized_name = self._sanitize_filename(document_name)

        # Release the vector store from memory if it's loaded
        if document_name in self.vector_stores:
            del self.vector_stores[document_name]
            # Force garbage collection to release file handles
            import gc
            gc.collect()

        # Delete the source document file
        for ext in ['.pdf', '.docx', '.txt', '.xls', '.xlsx']:
            doc_path = self.docs_folder_path / (document_name + ext)
            if doc_path.exists():
                doc_path.unlink()
                break

        # Delete the FAISS index folder
        faiss_index_path = self.vector_store_path / sanitized_name
        if faiss_index_path.exists():
            try:
                shutil.rmtree(faiss_index_path)
            except OSError:
                # A second try after a short delay, ignoring errors on the second attempt.
                # This can help with lingering file locks on Windows.
                import time
                time.sleep(0.5)
                shutil.rmtree(faiss_index_path, ignore_errors=True)

    def _sanitize_filename(self, filename):
        return "".join(c for c in filename if c.isalnum() or c in (' ', '_', '-')).rstrip()


# --- Worker Code ---
class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(tuple)
    result = Signal(str)
    status = Signal(str)


class Worker(QObject):
    def __init__(self, backend: ChatbotBackend):
        super().__init__()
        self.backend = backend
        self.signals = WorkerSignals()

    @Slot()
    def setup_backend(self):
        try:
            self.signals.status.emit("Initializing knowledge base... This may take a moment.")
            self.backend.setup_vector_stores()
            self.signals.status.emit("Vector stores are ready.")
        except Exception as e:
            self.signals.error.emit((type(e), e, traceback.format_exc()))
        finally:
            self.signals.finished.emit()

    @Slot(str, str, str)
    def ask_question(self, question: str, document_name: str, ollama_model: str):
        if question and document_name:
            try:
                response = self.backend.ask(question, document_name, ollama_model)
                self.signals.result.emit(response)
            except Exception as e:
                self.signals.error.emit((type(e), e, traceback.format_exc()))


# --- GUI Code ---
class ChatWindow(QWidget):
    ask_question_signal = Signal(str, str, str)
    setup_backend_signal = Signal()

    def __init__(self, backend: ChatbotBackend, initial_ollama_model: str = None):
        super().__init__()
        self.backend = backend
        self.initial_ollama_model = initial_ollama_model
        self.current_document = None
        self.init_ui()

        self.thread = QThread()
        self.worker = Worker(self.backend)
        self.worker.moveToThread(self.thread)

        self.worker.signals.result.connect(self.handle_ai_response)
        self.worker.signals.status.connect(self.update_status)
        self.worker.signals.error.connect(self.handle_error)

        self.ask_question_signal.connect(self.worker.ask_question)
        self.setup_backend_signal.connect(self.worker.setup_backend)

        self.thread.start()

        self.reload_ai()
        self.refresh_ollama_models()

    def init_ui(self):
        self.setWindowTitle(f' {AppTitle} {HDVersion} / EXPERIMENTAL')
        project_root = Path(__file__).resolve().parent
        icon_path = project_root / "resources" / "documentai.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.load_stylesheet()

        self.tabs = QTabWidget()
        self.chat_tab = QWidget()
        self.settings_tab = QWidget()

        self.tabs.addTab(self.chat_tab, "Chat")
        self.tabs.addTab(self.settings_tab, "Settings")

        chat_layout = QVBoxLayout(self.chat_tab)

        self.chat_display = QTextBrowser()
        self.chat_display.setReadOnly(True)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Ask a question...")
        self.input_box.returnPressed.connect(self.send_message)

        self.send_button = QPushButton("Chat")
        self.send_button.clicked.connect(self.send_message)

        self.document_label = QLabel("Document:")
        self.document_dropdown = QComboBox()
        self.document_dropdown.currentTextChanged.connect(self.set_current_document)

        self.open_file_button = QPushButton("Open File")
        self.open_file_button.clicked.connect(self.open_selected_file)

        document_layout = QHBoxLayout()
        document_layout.addWidget(self.document_label)
        document_layout.addWidget(self.document_dropdown)
        document_layout.addWidget(self.open_file_button)

        input_layout = QHBoxLayout()
        input_layout.addWidget(self.input_box)
        input_layout.addWidget(self.send_button)

        self.clear_button = QPushButton("Clear Chat")
        self.clear_button.clicked.connect(self.clear_chat)

        self.reload_button = QPushButton("Reload AI")
        self.reload_button.clicked.connect(self.reload_ai)

        self.upload_button = QPushButton("Upload Document")
        self.upload_button.clicked.connect(self.upload_document)

        self.save_chat_button = QPushButton("Save Chat")
        self.save_chat_button.clicked.connect(self.save_chat)

        self.delete_document_button = QPushButton("Delete Document")
        self.delete_document_button.clicked.connect(self.delete_document)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.reload_button)
        button_layout.addWidget(self.upload_button)
        button_layout.addWidget(self.save_chat_button)
        button_layout.addWidget(self.delete_document_button)
        button_layout.addStretch()

        chat_layout.addLayout(document_layout)
        chat_layout.addWidget(self.chat_display)
        chat_layout.addLayout(button_layout)
        chat_layout.addLayout(input_layout)

        settings_layout = QVBoxLayout(self.settings_tab)
        self.ollama_url_label = QLabel("Ollama Server URL:")
        self.ollama_url_input = QLineEdit()
        self.ollama_url_input.setText(self.backend.ollama_base_url)

        self.ollama_model_label = QLabel("Ollama Model:")
        self.ollama_model_dropdown = QComboBox()
        if self.initial_ollama_model:
            self.ollama_model_dropdown.addItem(self.initial_ollama_model)

        self.refresh_models_button = QPushButton("Refresh Models")
        self.refresh_models_button.clicked.connect(self.refresh_ollama_models)

        self.save_settings_button = QPushButton("Save Settings")
        self.save_settings_button.clicked.connect(self.save_settings)

        settings_layout.addWidget(self.ollama_url_label)
        settings_layout.addWidget(self.ollama_url_input)
        settings_layout.addWidget(self.ollama_model_label)

        model_layout = QHBoxLayout()
        model_layout.addWidget(self.ollama_model_dropdown)
        model_layout.addWidget(self.refresh_models_button)

        settings_layout.addLayout(model_layout)
        settings_layout.addWidget(self.save_settings_button)
        settings_layout.addStretch()

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Initializing...")
        main_layout.addWidget(self.status_bar)

        self.setLayout(main_layout)
        self.setMinimumSize(700, 500)

    def refresh_ollama_models(self):
        self.update_status("Refreshing Ollama models...")
        try:
            models = self.backend.get_ollama_models()
            current_model = self.ollama_model_dropdown.currentText()
            self.ollama_model_dropdown.clear()
            if self.initial_ollama_model and self.initial_ollama_model not in models:
                self.ollama_model_dropdown.addItem(self.initial_ollama_model)
            self.ollama_model_dropdown.addItems(models)
            if current_model in models:
                self.ollama_model_dropdown.setCurrentText(current_model)
            elif self.initial_ollama_model in models:
                self.ollama_model_dropdown.setCurrentText(self.initial_ollama_model)

            self.update_status("Ollama models refreshed.")
        except Exception as e:
            self.update_status(f"Error refreshing Ollama models: {e}")
            QMessageBox.warning(self, "Error", f"Could not fetch models from the Ollama server: {e}")

    def save_settings(self):
        new_url = self.ollama_url_input.text().strip()
        selected_model = self.ollama_model_dropdown.currentText()
        project_root = Path(__file__).resolve().parent
        if new_url and selected_model:
            self.backend.update_ollama_url(new_url)

            settings_path = project_root / "settings.json"
            try:
                if settings_path.exists():
                    with open(settings_path, "r", encoding="utf-8") as f:
                        settings = json.load(f)
                else:
                    settings = {}

                settings["ollama_server_address"] = new_url
                settings["ollama_model"] = selected_model

                with open(settings_path, "w", encoding="utf-8") as f:
                    json.dump(settings, f, indent=4)

                QMessageBox.information(self, "Settings Saved", "Ollama settings updated. The AI will now reload.")
                self.reload_ai()
            except Exception as e:
                QMessageBox.critical(self, "Error Saving Settings", f"Failed to save settings: {e}")
        else:
            QMessageBox.warning(self, "Incomplete Settings", "Please provide both a server URL and select a model.")

    def load_stylesheet(self):
        project_root = Path(__file__).resolve().parent
        qss_path = project_root / "resources" / "style.qss"
        if qss_path.exists():
            try:
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
            except Exception as e:
                print(f"Error loading stylesheet: {e}")

    def open_selected_file(self):
        if self.current_document:
            full_filename = ""
            for f in os.listdir(self.backend.docs_folder_path):
                if os.path.splitext(f)[0] == self.current_document:
                    full_filename = f
                    break

            if full_filename:
                file_path = os.path.join(self.backend.docs_folder_path, full_filename)
                try:
                    if sys.platform == "win32":
                        os.startfile(file_path)
                    elif sys.platform == "darwin":
                        os.system(f'open "{file_path}"')
                    else:  # linux
                        os.system(f'xdg-open "{file_path}"')
                except Exception as e:
                    self.add_message("Error", f"Failed to open file: {e}")
            else:
                self.add_message("Error", "Could not find the selected file.")

    def upload_document(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Upload Document", "",
                                                   "Documents (*.pdf *.docx *.txt *.xls *.xlsx );;All Files (*)",
                                                   options=options)
        if file_path:
            try:
                shutil.copy(file_path, self.backend.docs_folder_path)
                self.add_message("System", f"Document '{Path(file_path).name}' uploaded successfully. Reloading AI...")
                self.reload_ai()
            except Exception as e:
                self.add_message("Error", f"Failed to upload document: {e}")

    def save_chat(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Chat", "", "Text Files (*.txt);;All Files (*)",
                                                   options=options)
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.chat_display.toPlainText())
                self.add_message("System", f"Chat saved to {file_path}")
            except Exception as e:
                self.add_message("Error", f"Failed to save chat: {e}")

    def delete_document(self):
        if not self.current_document:
            self.add_message("System", "Please select a document to delete.")
            return

        document_to_delete = self.current_document
        reply = QMessageBox.question(self, 'Delete Document',
                                     f"Are you sure you want to delete '{document_to_delete}' and its associated data?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                self.backend.delete_document(document_to_delete)
                self.add_message("System", f"Document '{document_to_delete}' deleted successfully. Reloading AI...")
                self.reload_ai()
            except Exception as e:
                self.add_message("Error", f"Failed to delete document: {e}")

    def populate_documents_dropdown(self):
        self.document_dropdown.clear()
        documents = self.backend.get_available_documents()
        if documents:
            self.document_dropdown.addItems(documents)
            self.set_current_document(documents[0])
        else:
            self.update_status("No documents found. Please add documents to chat.")
            self.current_document = None
            self.clear_chat()

    def set_current_document(self, document_name):
        self.current_document = document_name
        self.clear_chat()
        if document_name:
            self.add_message("System",
                             f"Document set to: {self.current_document}. You can now ask questions about this document.")

    def clear_chat(self):
        self.chat_display.clear()

    def reload_ai(self):
        self.clear_chat()
        self.update_status("Reloading AI... This may take a moment.")
        self.send_button.setEnabled(False)
        self.input_box.setEnabled(False)
        self.setup_backend_signal.emit()

    def send_message(self):
        if not self.current_document:
            self.add_message("System", "Please select a document first.")
            return

        question = self.input_box.text().strip()
        if not question:
            return

        self.add_message("You", question)
        self.input_box.clear()

        ollama_model = self.ollama_model_dropdown.currentText()
        self.ask_question_signal.emit(question, self.current_document, ollama_model)

        self.send_button.setEnabled(False)
        self.input_box.setEnabled(False)
        self.add_message("AI", "<i>Thinking...</i>")

    def handle_ai_response(self, response):
        self.chat_display.moveCursor(QTextCursor.End)
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        if "<i>Thinking...</i>" in cursor.selectedText():
            cursor.removeSelectedText()
            self.add_message("AI", response)
        else:
            self.add_message("AI", response)

        self.send_button.setEnabled(True)
        self.input_box.setEnabled(True)
        self.input_box.setFocus()

    def add_message(self, sender, message):
        self.chat_display.append(f"<b>{sender}:</b> {message}")

    def update_status(self, status):
        self.status_bar.showMessage(status)
        if "Vector stores are ready." in status:
            self.populate_documents_dropdown()
            self.send_button.setEnabled(True)
            self.input_box.setEnabled(True)

    def handle_error(self, error_tuple):
        error_message = str(error_tuple[1])
        self.add_message("Error", error_message)
        self.update_status(f"Error: {error_message}")
        self.send_button.setEnabled(True)
        self.input_box.setEnabled(True)

    def closeEvent(self, event):
        self.thread.quit()
        self.thread.wait()
        super().closeEvent(event)


# --- Main Application ---
def main():
    project_root = Path(__file__).parent
    docs_folder = project_root / "AIDocs"
    vector_store_folder = project_root / "faiss_index"
    settings_file = project_root / "settings.json"

    ollama_server_address = "http://localhost:11434"
    ollama_model = ""
    try:
        with open(settings_file, 'r') as f:
            settings = json.load(f)
            ollama_server_address = settings.get("ollama_server_address", ollama_server_address)
            ollama_model = settings.get("ollama_model", ollama_model)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    app = QApplication(sys.argv)

    backend = ChatbotBackend(docs_folder_path=str(docs_folder), vector_store_path=str(vector_store_folder),
                             ollama_base_url=ollama_server_address)
    window = ChatWindow(backend, initial_ollama_model=ollama_model)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
