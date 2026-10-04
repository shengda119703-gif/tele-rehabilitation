"""Existing product widgets shared by page adapters; styling is unchanged."""
import html
from .product_theme import SPACING
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QLabel, QPushButton, QFrame, QVBoxLayout, QTableWidget,
    QHeaderView, QAbstractItemView, QTableWidgetItem)

escape = lambda text: html.escape(str(text))


def visual(widget, *, typography=None, appearance=None, status=None):
    """Presentation properties only: never replaces a widget, signal or action identity."""
    for key,value in (('fluentType',typography),('fluentAppearance',appearance),('fluentStatus',status)):
        if value is not None:widget.setProperty(key,value)
    widget.style().unpolish(widget);widget.style().polish(widget);widget.update()
    return widget


def core_card(title='',hero=False,*,kind='information'):
    item,box=card('',hero)
    item.setProperty('fluentCard','hero' if hero else 'true')
    item.setProperty('fluentCardKind',kind)
    box.setContentsMargins(*([SPACING['xl']]*4));box.setSpacing(SPACING['md'])
    box.setAlignment(Qt.AlignTop)
    if title:box.addWidget(visual(label(title),typography='card'))
    return item,box


def empty_state(title,description):
    item,box=core_card(title,kind='empty')
    box.addWidget(visual(label(description),typography='secondary'))
    return item


def conversation_html(messages,colors):
    """Native rich text, escaped data, explicit speaker labels even without color."""
    if not messages:
        return f'<p style="color:{colors["secondary"]}">可以说说今天的身体感受，或查询已保存的康复记录。</p>'
    result=[]
    for message in messages[-60:]:
        user=message['role']=='elder'
        name='我' if user else '安康 · 康复管家'
        content=escape(message['text']).replace('\n','<br>')
        result.append(f'<table width="100%" cellspacing="0" cellpadding="12"><tr><td bgcolor="{colors["soft"] if user else colors["surface"]}"><p style="color:{colors["secondary"]}"><b>{name}</b> · {escape(message["time"])}</p><p style="color:{colors["text"]}">{content}</p></td></tr></table><br>')
    return ''.join(result)


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


def rows(widget, values, *, keys=None):
    def identity(item):
        key=item.data(Qt.UserRole)
        return ('key',key) if key is not None else ('label',item.text())
    selected=widget.currentRow()
    anchor=identity(widget.item(selected,0)) if selected>=0 and widget.item(selected,0) else None
    scroll=widget.verticalScrollBar().value()
    previous=widget.blockSignals(True)
    widget.clearSelection()
    widget.setCurrentCell(-1,-1)
    widget.setRowCount(len(values))
    for r,row in enumerate(values):
        for c,value in enumerate(row):
            widget.setItem(r,c,QTableWidgetItem(str(value if value is not None else '未记录')))
        if keys is not None and widget.item(r,0):widget.item(r,0).setData(Qt.UserRole,keys[r])
    matches=[r for r in range(widget.rowCount()) if widget.item(r,0) and identity(widget.item(r,0))==anchor]
    if len(matches)==1:widget.selectRow(matches[0])
    widget.verticalScrollBar().setValue(scroll)
    widget.blockSignals(previous)
