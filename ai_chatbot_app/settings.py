import json
import requests
from PySide6.QtWidgets import (QCheckBox, QGroupBox, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget, QComboBox, QLabel, QTabWidget, QLineEdit)


class SettingsWindow(QWidget):
    def __init__(self, menu_config, settings_file, rebuild_menu_callback, parent=None):

        super().__init__(parent)
        self.menu_config = menu_config
        self.settings_file = settings_file
        self.rebuild_menu_callback = rebuild_menu_callback
        self.settings = self._load_settings()
        self.checkboxes = {}  # Stores references to all checkboxes and groupboxes

        self.setWindowTitle("Menu Settings")
        self.setGeometry(100, 100, 400, 500)

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)
        
        # --- Tab Widget for Organization ---
        tabs = QTabWidget()
        main_layout.addWidget(tabs)

        # --- Appearance Tab ---
        appearance_tab = QWidget()
        appearance_layout = QVBoxLayout(appearance_tab)
        tabs.addTab(appearance_tab,"Appearance")

        # --- Theme Selection ---
        theme_label = QLabel("Select Theme:")
        self.theme_combobox = QComboBox()
        self.theme_combobox.addItems(["Light", "Dark"])
        current_theme = self.settings.get("theme", "Light")
        self.theme_combobox.setCurrentText(current_theme)
        appearance_layout.addWidget(theme_label)
        appearance_layout.addWidget(self.theme_combobox)
        appearance_layout.addStretch() # Pushes the theme selector to the top

        # --- Item Visibility Tab ---
        visibility_tab = QWidget()
        visibility_layout = QVBoxLayout(visibility_tab)
        tabs.addTab(visibility_tab, "Visibility")

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        visibility_layout.addWidget(scroll_area)

        container = QWidget()
        self.container_layout = QVBoxLayout(container)
        scroll_area.setWidget(container)

        self._populate_settings_from_config()

        # --- Ollama Settings Tab ---
        ollama_tab = QWidget()
        ollama_layout = QVBoxLayout(ollama_tab)
        tabs.addTab(ollama_tab, "Ollama")

        ollama_server_label = QLabel("Ollama Server Address:")
        self.ollama_server_input = QLineEdit()
        self.ollama_server_input.setPlaceholderText("e.g., http://localhost:11434")
        current_ollama_server = self.settings.get("ollama_server_address", "http://localhost:11434")
        self.ollama_server_input.setText(current_ollama_server)
        ollama_layout.addWidget(ollama_server_label)
        ollama_layout.addWidget(self.ollama_server_input)

        # --- Ollama Model Selection ---
        ollama_model_label = QLabel("Select Ollama Model:")
        self.ollama_model_combobox = QComboBox()
        ollama_layout.addWidget(ollama_model_label)
        ollama_layout.addWidget(self.ollama_model_combobox)

        refresh_models_button = QPushButton("Refresh Models")
        refresh_models_button.clicked.connect(self._fetch_ollama_models)
        ollama_layout.addWidget(refresh_models_button)
        
        self._fetch_ollama_models() # Fetch models on init
        
        current_ollama_model = self.settings.get("ollama_model", "")
        if current_ollama_model:
            self.ollama_model_combobox.setCurrentText(current_ollama_model)


        ollama_layout.addStretch()

        # --- Save Button ---
        save_button = QPushButton("Save and Reload")
        save_button.clicked.connect(self._save_settings_and_close)
        main_layout.addWidget(save_button)

    def _fetch_ollama_models(self):
        self.ollama_model_combobox.clear()
        try:
            server_address = self.ollama_server_input.text()
            if not server_address:
                # Handle case where server address is empty
                self.ollama_model_combobox.addItem("Enter server address first")
                return

            response = requests.get(f"{server_address}/api/tags")
            response.raise_for_status()  # Raise an exception for bad status codes
            models = response.json().get("models", [])
            model_names = [model["name"] for model in models]
            self.ollama_model_combobox.addItems(model_names)
            
            current_ollama_model = self.settings.get("ollama_model", "")
            if current_ollama_model:
                self.ollama_model_combobox.setCurrentText(current_ollama_model)

        except requests.exceptions.RequestException as e:
            self.ollama_model_combobox.addItem(f"Error: {e}")
        except json.JSONDecodeError:
            self.ollama_model_combobox.addItem("Error: Invalid response from server")


    def _load_settings(self):
        try:
            with open(self.settings_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"theme": "Light", "ollama_server_address": "http://localhost:11434", "ollama_model": ""}

    def _populate_settings_from_config(self):
        self._populate_recursive(self.menu_config, self.container_layout)

    def _populate_recursive(self, menu_items, parent_layout):
        for item in menu_items:
            label = item.get('label')
            if not label or item.get('type') == 'separator':
                continue

            is_visible = self.settings.get(label, True)

            if 'items' in item:
                group_box = QGroupBox(label)
                group_layout = QVBoxLayout(group_box)
                group_box.setCheckable(True)
                
                if label == "More":
                    group_box.setChecked(True)
                    group_box.setEnabled(False)
                else:
                    group_box.setChecked(is_visible)
                
                self.checkboxes[label] = group_box
                self._populate_recursive(item['items'], group_layout)
                parent_layout.addWidget(group_box)
            else:
                checkbox = QCheckBox(label)
                checkbox.setChecked(is_visible)
                self.checkboxes[label] = checkbox
                parent_layout.addWidget(checkbox)

    def _save_settings_and_close(self):
        self._save_recursive(self.menu_config)
        self.settings["theme"] = self.theme_combobox.currentText()
        self.settings["ollama_server_address"] = self.ollama_server_input.text()
        self.settings["ollama_model"] = self.ollama_model_combobox.currentText()

        with open(self.settings_file, 'w') as f:
            json.dump(self.settings, f, indent=4)

        if self.rebuild_menu_callback:
            self.rebuild_menu_callback()

        self.close()

    def _save_recursive(self, menu_items):
        for item in menu_items:
            label = item.get('label')
            if not label:
                continue

            if label in self.checkboxes:
                if label == "More":
                    self.settings[label] = True
                else:
                    self.settings[label] = self.checkboxes[label].isChecked()

            if 'items' in item:
                self._save_recursive(item['items'])
