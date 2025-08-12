from PySide6.QtCore import QObject, Signal, Slot
from .backend import ChatbotBackend

class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.
    Supported signals are:
    - finished: No data
    - error: tuple (exctype, value, traceback.format_exc())
    - result: object data returned from processing
    - status: str message for status updates
    """
    finished = Signal()
    error = Signal(tuple)
    result = Signal(str)
    status = Signal(str)

class Worker(QObject):
    """
    Worker thread for running background tasks like setting up the vector store
    or asking a question.
    """
    def __init__(self, backend: ChatbotBackend):
        super().__init__()
        self.backend = backend
        self.signals = WorkerSignals()

    @Slot()
    def setup_backend(self):
        """
        Initializes the backend by setting up the vector stores for all documents.
        """
        try:
            self.signals.status.emit("Initializing knowledge base... This may take a moment.")
            self.backend.setup_vector_stores()
            self.signals.status.emit("Vector stores are ready.")
        except Exception as e:
            self.signals.error.emit((type(e), e, str(e)))
        finally:
            self.signals.finished.emit()

    @Slot(str, str, str)
    def ask_question(self, question: str, document_name: str, ollama_model: str):
        """
        Asks a question to the backend using the specified document.
        """
        if question and document_name:
            try:
                response = self.backend.ask(question, document_name, ollama_model)
                self.signals.result.emit(response)
            except Exception as e:
                self.signals.error.emit((type(e), e, str(e)))
