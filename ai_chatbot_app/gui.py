import sys
import os
from pathlib import Path
from PySide6.QtCore import QThread
from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTextBrowser, QLineEdit, QPushButton,
    QHBoxLayout, QLabel, QStatusBar, QComboBox, QFileDialog, QMessageBox, QTabWidget
)
import shutil
import json

# Add project root to sys.path to import global_vars
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from global_vars import AppTitle, HDVersion

from ai_chatbot_app.backend import ChatbotBackend
from ai_chatbot_app.worker import Worker

class ChatWindow(QWidget):
    def __init__(self, backend: ChatbotBackend, initial_ollama_model: str = None):
        super().__init__()
        self.backend = backend
        self.initial_ollama_model = initial_ollama_model
        self.thread = None
        self.worker = None
        self.current_document = None
        self.init_ui()
        self.run_backend_setup()

    def init_ui(self):
        self.setWindowTitle(f'Americana Document AI / {AppTitle} {HDVersion} / EXPERIMENTAL')
        icon_path = project_root / "resources" / "documentai.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.load_stylesheet()

        # Create Tab Widget
        self.tabs = QTabWidget()
        self.chat_tab = QWidget()
        self.settings_tab = QWidget()

        self.tabs.addTab(self.chat_tab, "Chat")
        self.tabs.addTab(self.settings_tab, "Settings")

        # --- Chat Tab Layout ---
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

        # --- Settings Tab Layout ---
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

        # --- Main Layout ---
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
            self.ollama_model_dropdown.addItems(models)
            if current_model in models:
                self.ollama_model_dropdown.setCurrentText(current_model)
            self.update_status("Ollama models refreshed.")
        except Exception as e:
            self.update_status(f"Error refreshing Ollama models: {e}")
            QMessageBox.warning(self, "Error refreshing models", f"Could not fetch models from the Ollama server: {e}")

    def save_settings(self):
        new_url = self.ollama_url_input.text().strip()
        selected_model = self.ollama_model_dropdown.currentText()
        if new_url and selected_model:
            self.backend.update_ollama_url(new_url)
            
            settings_path = project_root / "settings.json"
            try:
                with open(settings_path, "r+", encoding="utf-8") as f:
                    settings = json.load(f)
                    settings["ollama_server_address"] = new_url
                    settings["ollama_model"] = selected_model
                    f.seek(0)
                    json.dump(settings, f, indent=4)
                    f.truncate()
                QMessageBox.information(self, "Settings Saved", "Ollama settings updated. The AI will now reload.")
                self.reload_ai()
            except Exception as e:
                QMessageBox.critical(self, "Error Saving Settings", f"Failed to save settings: {e}")
        else:
            QMessageBox.warning(self, "Incomplete Settings", "Please provide both a server URL and select a model.")

    def load_stylesheet(self):
        """Loads and applies the QSS stylesheet from the resources folder."""
        qss_path = project_root / "resources" / "style.qss"
        if qss_path.exists():
            try:
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
            except Exception as e:
                print(f"Error loading stylesheet: {e}")

    def open_selected_file(self):
        if self.current_document:
            # Find the full filename with extension
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
                    else: # linux
                        os.system(f'xdg-open "{file_path}"')
                except Exception as e:
                    self.add_message("Error", f"Failed to open file: {e}")
            else:
                self.add_message("Error", "Could not find the selected file.")

    def upload_document(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Upload Document", "", "Documents (*.pdf *.docx *.txt *.xls *.xlsx );;All Files (*)", options=options)
        if file_path:
            try:
                shutil.copy(file_path, self.backend.docs_folder_path)
                self.add_message("System", f"Document '{Path(file_path).name}' uploaded successfully. Reloading AI...")
                self.reload_ai()
            except Exception as e:
                self.add_message("Error", f"Failed to upload document: {e}")

    def save_chat(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Chat", "", "Text Files (*.txt);;All Files (*)", options=options)
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
            self.add_message("System", f"Document set to: {self.current_document}. You can now ask questions about this document.")

    def clear_chat(self):
        self.chat_display.clear()

    def reload_ai(self):
        self.clear_chat()
        self.update_status("Reloading AI... This may take a moment.")
        self.run_backend_setup()

    def run_backend_setup(self):
        self.thread = QThread()
        self.worker = Worker(self.backend)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.setup_backend)
        self.worker.signals.finished.connect(self.thread.quit)
        self.worker.signals.finished.connect(self.worker.deleteLater)
        self.worker.signals.finished.connect(self.thread.deleteLater)
        self.worker.signals.finished.connect(self.populate_documents_dropdown)
        self.worker.signals.status.connect(self.update_status)
        self.worker.signals.error.connect(self.handle_error)

        self.thread.start()
        self.send_button.setEnabled(False)
        self.input_box.setEnabled(False)

    def send_message(self):
        if not self.current_document:
            self.add_message("System", "Please select a document first.")
            return

        question = self.input_box.text().strip()
        if not question:
            return

        self.add_message("You", question)
        self.input_box.clear()

        self.thread = QThread()
        self.worker = Worker(self.backend)
        self.worker.question = question
        self.worker.document_name = self.current_document
        self.worker.ollama_model = self.ollama_model_dropdown.currentText()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.ask_question)
        self.worker.signals.result.connect(self.handle_ai_response)
        self.worker.signals.finished.connect(self.thread.quit)
        self.worker.signals.finished.connect(self.worker.deleteLater)
        self.worker.signals.finished.connect(self.thread.deleteLater)

        self.thread.start()
        self.send_button.setEnabled(False)
        self.input_box.setEnabled(False)
        self.add_message("AI", "<i>Thinking...</i>")

    def handle_ai_response(self, response):
        self.chat_display.moveCursor(QTextCursor.End)
        self.chat_display.moveCursor(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        self.chat_display.moveCursor(QTextCursor.End, QTextCursor.KeepAnchor)
        self.chat_display.textCursor().removeSelectedText()
        self.add_message("AI", response)
        self.send_button.setEnabled(True)
        self.input_box.setEnabled(True)
        self.input_box.setFocus()

    def add_message(self, sender, message):
        self.chat_display.append(f"<b>{sender}:</b> {message}")

    def update_status(self, status):
        self.status_bar.showMessage(status)
        if status == "Vector stores are ready.":
            self.send_button.setEnabled(True)
            self.input_box.setEnabled(True)

    def handle_error(self, error_tuple):
        self.add_message("Error", str(error_tuple[1]))
        self.update_status("Error occurred. Please check the console.")
