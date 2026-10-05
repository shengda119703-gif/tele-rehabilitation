"""Native product controls and responsive reading layouts; domain actions stay with page adapters."""
import html
from datetime import datetime
from .product_theme import SPACING
from .product_segments import SegmentTabs
from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QLabel, QPushButton, QFrame, QVBoxLayout, QTableWidget,
    QHeaderView, QAbstractItemView, QTableWidgetItem, QWidget, QGridLayout, QSizePolicy,
    QHBoxLayout, QStylePainter, QStyleOptionButton, QStyle, QTabWidget, QStackedWidget)

escape = lambda text: html.escape(str(text))


class CurrentStack(QStackedWidget):
    """Inactive detail panes must not make a short overview scroll unnecessarily."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.currentChanged.connect(self._fit_current)

    def addWidget(self,widget):
        index=super().addWidget(widget)
        self._fit_current(self.currentIndex())
        return index

    def _fit_current(self,index):
        for i in range(self.count()):
            policy=QSizePolicy.Preferred if i==index else QSizePolicy.Ignored
            self.widget(i).setSizePolicy(policy,policy)
        self.updateGeometry()
        self._fit_height()

    def _fit_height(self):
        if not self.property('activeHeightOnly') or not self.currentWidget():return
        height=self.heightForWidth(max(1,self.width()))
        if height>0 and self.maximumHeight()!=height:self.setMaximumHeight(height)

    def resizeEvent(self,event):
        super().resizeEvent(event);self._fit_height()

    def event(self,event):
        result=super().event(event)
        if event.type()==QEvent.LayoutRequest:self._fit_height()
        return result

    def sizeHint(self):
        return self.currentWidget().sizeHint() if self.currentWidget() else super().sizeHint()

    def minimumSizeHint(self):
        return self.currentWidget().minimumSizeHint() if self.currentWidget() else super().minimumSizeHint()

    def hasHeightForWidth(self):
        return bool(self.currentWidget() and self.currentWidget().hasHeightForWidth())

    def heightForWidth(self, width):
        # QStackedLayout otherwise takes the tallest *hidden* wrapping page.
        # SizeHint alone cannot prevent the scroll area's phantom vertical range.
        current=self.currentWidget()
        if current is None:return super().heightForWidth(width)
        height=current.heightForWidth(width)
        return height if height>=0 else current.sizeHint().height()


def display_time(value):
    """Local reading label only; stored timestamps and export data remain untouched."""
    if not value:return '时间未记录'
    if len(str(value))==10:return str(value)
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone().strftime('%Y-%m-%d %H:%M')
    except ValueError:return str(value)


class ContentTabs(SegmentTabs):
    """Size a short settings pane to the active content, not its tallest sibling."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(self._fit_current)

    def _fit_current(self, index):
        for i in range(self.count()):
            policy=QSizePolicy.Preferred if i==index else QSizePolicy.Ignored
            self.widget(i).setSizePolicy(policy,policy)
        self.updateGeometry()
        self._fit_height()

    def _fit_height(self):
        if self.currentWidget() is None:return
        layout=self.currentWidget().layout()
        height=layout.heightForWidth(max(1,self.width()-4)) if layout and layout.hasHeightForWidth() else -1
        if height<0:height=self.currentWidget().sizeHint().height()
        height+=self.tabBar().sizeHint().height()+14  # core pane padding-top
        if self.maximumHeight()!=height:self.setMaximumHeight(height)

    def resizeEvent(self,event):
        super().resizeEvent(event);self._fit_height()

    def event(self,event):
        result=super().event(event)
        if event.type()==QEvent.LayoutRequest:self._fit_height()
        return result

    def tabInserted(self,index):
        super().tabInserted(index);self._fit_current(self.currentIndex())

    def sizeHint(self):
        if self.currentWidget() is None:return super().sizeHint()
        size=self.currentWidget().sizeHint()
        return QSize(max(size.width(),self.tabBar().sizeHint().width()),size.height()+self.tabBar().sizeHint().height()+14)

    def minimumSizeHint(self):
        if self.currentWidget() is None:return super().minimumSizeHint()
        size=self.currentWidget().minimumSizeHint()
        return QSize(size.width(),size.height()+self.tabBar().sizeHint().height()+14)


class WrappingLabel(QLabel):
    """Reserve the actual wrapped text height inside nested responsive layouts."""
    def setText(self,text):
        super().setText(text);self._fit_text()

    def resizeEvent(self,event):
        super().resizeEvent(event);self._fit_text()

    def _fit_text(self):
        if self.wordWrap() and self.width()>0:
            height=self.heightForWidth(self.width())
            if height>0 and self.minimumHeight()!=height:self.setMinimumHeight(height)


class EntryButton(QPushButton):
    """A native button with separately wrapping title and supporting text."""
    def __init__(self, title, description):
        super().__init__(title)
        self.setAccessibleName(title);self.setAccessibleDescription(description)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout=QHBoxLayout(self);layout.setContentsMargins(16,16,16,16);layout.setSpacing(16)
        self.symbol=QLabel();self.symbol.setFixedSize(24,24);layout.addWidget(self.symbol,0,Qt.AlignTop)
        text=QVBoxLayout();text.setSpacing(6)
        self.heading=visual(label(title),typography='card')
        self.detail=visual(label(description),typography='secondary')
        text.addWidget(self.heading);text.addWidget(self.detail);layout.addLayout(text,1)
        for child in self.findChildren(QLabel):child.setAttribute(Qt.WA_TransparentForMouseEvents)

    def setDescription(self, text):
        self.detail.setText(text);self.setAccessibleDescription(text)

    def description(self):return self.detail.text()

    def setIcon(self, icon):
        super().setIcon(icon);self.symbol.setPixmap(icon.pixmap(QSize(24,24)))

    def sizeHint(self):return self.layout().sizeHint()

    def minimumSizeHint(self):return self.layout().minimumSize()

    def paintEvent(self, event):
        option=QStyleOptionButton();self.initStyleOption(option)
        option.text='';option.icon=QIcon()
        painter=QStylePainter(self);painter.drawControl(QStyle.CE_PushButton,option)


class ResponsiveGrid(QWidget):
    """Reflow existing native controls without recreating them or changing tab order."""
    def __init__(self, columns=2, threshold=880, parent=None):
        super().__init__(parent)
        self.columns=columns;self.threshold=threshold;self.items=[];self.current_columns=0
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(SPACING['lg'])

    def add(self, widget):
        self.items.append(widget);self._reflow()

    def resizeEvent(self,event):
        super().resizeEvent(event);self._reflow()

    def _reflow(self):
        columns=self.columns if self.width()>=self.threshold else max(1,self.columns//2)
        if columns==self.current_columns and self.grid.count()==len(self.items):return
        while self.grid.count():self.grid.takeAt(0)
        for column in range(self.columns):self.grid.setColumnStretch(column,1 if column<columns else 0)
        for index,widget in enumerate(self.items):self.grid.addWidget(widget,index//columns,index%columns)
        self.current_columns=columns


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
    box.setContentsMargins(0,18,0,12);box.setSpacing(SPACING['md'])
    if hero:box.setContentsMargins(22,12,12,12)
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
        blocks=message.get('blocks') or []
        if not user and blocks:
            parts=[]
            for block in blocks:
                title={'main':'','receipt':'记录回执 · ','privacy':'可见范围 · '}.get(block.get('kind'),'')
                color=colors['text'] if block.get('kind')=='main' else colors['secondary']
                parts.append('<p style="color:'+color+'">'+escape(title+block.get('text','')).replace('\n','<br>')+'</p>')
            content=''.join(parts)
        else:content=escape(message['text']).replace('\n','<br>')
        spacer='<td width="22%"></td>' if user else ''
        result.append(f'<table width="100%" cellspacing="0" cellpadding="12"><tr>{spacer}<td bgcolor="{colors["soft"] if user else colors["surface"]}"><p style="color:{colors["secondary"]}"><b>{name}</b> · {escape(message["time"])}</p><p style="color:{colors["text"]}">{content}</p></td></tr></table><br>')
    return ''.join(result)


def label(text='', style=None):
    item = QLabel(text)
    item.setWordWrap(True)
    if style:
        item.setObjectName(style)
    return item


def button(text, callback, primary=False):
    item = QPushButton(text)
    item.setSizePolicy(QSizePolicy.Maximum,QSizePolicy.Fixed)
    if primary:
        item.setObjectName('productPrimary')
    item.clicked.connect(callback)
    return item


def card(title, hero=False):
    item = QFrame()
    item.setObjectName('productHero' if hero else 'productCard')
    box = QVBoxLayout(item)
    box.setContentsMargins(0,18,0,12)
    box.setSpacing(12)
    if title:
        box.addWidget(label(title,'productSection'))
    return item,box


def table(headers):
    item = QTableWidget(0,len(headers))
    item.setHorizontalHeaderLabels(headers)
    item.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    item.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    item.verticalHeader().hide()
    item.setEditTriggers(QAbstractItemView.NoEditTriggers)
    item.setSelectionBehavior(QAbstractItemView.SelectRows)
    item.setSelectionMode(QAbstractItemView.SingleSelection)
    item.setAlternatingRowColors(True)
    item.setShowGrid(False)
    item.setMinimumHeight(165)
    item.setProperty('productTable',True)
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
            header=widget.horizontalHeaderItem(c)
            text=display_time(value) if header and header.text() in ('时间','保存时间','创建时间') and value else str(value if value is not None else '未记录')
            widget.setItem(r,c,QTableWidgetItem(text))
        if keys is not None and widget.item(r,0):widget.item(r,0).setData(Qt.UserRole,keys[r])
    matches=[r for r in range(widget.rowCount()) if widget.item(r,0) and identity(widget.item(r,0))==anchor]
    if len(matches)==1:widget.selectRow(matches[0])
    widget.verticalScrollBar().setValue(scroll)
    widget.blockSignals(previous)
    if widget.property('productTable') and not widget.property('compactSummary'):
        widget.resizeRowsToContents()
        height=widget.horizontalHeader().height()+sum(max(36,widget.rowHeight(r)) for r in range(min(len(values),8)))+6 if values else 70
        widget.setMinimumHeight(min(height,380));widget.setMaximumHeight(min(height,380))
    if widget.property('compactSummary'):
        widget.setVisible(bool(values))
        widget.resizeRowsToContents()
        height=widget.horizontalHeader().height()+sum(widget.rowHeight(r) for r in range(min(len(values),4)))+4
        widget.setMinimumHeight(height);widget.setMaximumHeight(height)
