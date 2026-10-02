"""Existing product widgets shared by page adapters; styling is unchanged."""
import html
from PySide6.QtWidgets import (QLabel, QPushButton, QFrame, QVBoxLayout, QTableWidget,
    QHeaderView, QAbstractItemView, QTableWidgetItem)

escape = lambda text: html.escape(str(text))


def label(text='', style=None):
    item = QLabel(text)
    item.setWordWrap(True)
    if style:
        item.setObjectName(style)
    return item


def button(text, callback, primary=False):
    item = QPushButton(text)
    if primary:
        item.setObjectName('productPrimary')
    item.clicked.connect(callback)
    return item


def card(title, hero=False):
    item = QFrame()
    item.setObjectName('productHero' if hero else 'productCard')
    box = QVBoxLayout(item)
    box.setContentsMargins(22,20,22,20)
    box.setSpacing(12)
    if title:
        box.addWidget(label(title,'productSection'))
    return item,box


def table(headers):
    item = QTableWidget(0,len(headers))
    item.setHorizontalHeaderLabels(headers)
    item.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    item.verticalHeader().hide()
    item.setEditTriggers(QAbstractItemView.NoEditTriggers)
    item.setSelectionBehavior(QAbstractItemView.SelectRows)
    item.setSelectionMode(QAbstractItemView.SingleSelection)
    item.setAlternatingRowColors(True)
    item.setMinimumHeight(165)
    return item


def rows(widget, values):
    widget.setRowCount(len(values))
    for r,row in enumerate(values):
        for c,value in enumerate(row):
            widget.setItem(r,c,QTableWidgetItem(str(value if value is not None else '未记录')))
