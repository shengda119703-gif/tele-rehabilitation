"""Hidden developer credential dialog; no provider configuration."""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from ..deepseek_config import load_key, save_key, clear_key


class DeepSeekDeveloperDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('开发者')
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('DeepSeek API Key'))
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.Password)
        self.key_input.setText(load_key())
        layout.addWidget(self.key_input)
        self.save_button = QPushButton('确定')
        self.save_button.clicked.connect(self._save)
        layout.addWidget(self.save_button)
        self.clear_button = QPushButton('清除 Key')
        self.clear_button.clicked.connect(self._clear)
        layout.addWidget(self.clear_button)

    def _save(self):
        try:
            save_key(self.key_input.text())
        except (OSError, ValueError):
            QMessageBox.warning(self, '开发者', '无法保存 Key，请检查输入及本机配置目录权限。')
            return
        self.key_input.clear()
        self.accept()

    def _clear(self):
        try:
            clear_key()
        except (OSError, ValueError):
            QMessageBox.warning(self, '开发者', '无法清除 Key，请检查本机配置目录权限。')
            return
        self.key_input.clear()
        self.accept()
