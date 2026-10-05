"""Ankang desktop visual system: neutral surfaces, clear hierarchy, native controls."""
import re
import colorsys
import json
from pathlib import Path
from PySide6.QtGui import QColor, QPalette, QPixmap, QPainter, QIcon
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt

# Product aliases are the only visual values consumed by migrated pages.
SPACING = dict(xs=4, sm=8, md=12, lg=16, xl=24, xxl=32)
RADIUS = dict(control=6, card=8, hero=10)
TYPE = dict(display=(28,700), section=(20,600), card=(16,600),
            body=(14,400), secondary=(14,400), caption=(12,400))
METRICS = dict(overview=300, overview_collapsed=60, chat_minimum=110,
               input_minimum=52, input_maximum=72, reference_width=280, module_minimum=126)


def design_tokens(mode='light', palette=None):
    """Resolve pinned Fluent neutrals; project brand/status aliases stay centralized."""
    source = Path(__file__).resolve().parents[2]/'assets/ui/fluent'
    official = json.loads((source/'fluent2-official-web-theme-tokens.json').read_text(encoding='utf-8'))
    aliases = json.loads((source/'qt-token-map.json').read_text(encoding='utf-8'))['aliases']['colors']
    theme = official['webDarkTheme' if mode=='dark' else 'webLightTheme']
    c = {key:theme[value['token']] for key,value in aliases.items()}
    dark = mode=='dark'
    c.update(window='#171717' if dark else '#f7f7f7', surface=c['canvas_background'],
        text=c['text_primary'], secondary=c['text_secondary'],
        brand='#eeeeee' if dark else '#252525', on_brand='#171717' if dark else '#ffffff',
        brand_hover='#ffffff' if dark else '#3d3d3d', brand_pressed='#d6d6d6' if dark else '#111111',
        soft='#303030' if dark else '#ededed', border='#656565' if dark else '#d4d4d4',
        disabled_bg='#303030' if dark else '#eeeeee', disabled_text='#adadad' if dark else '#666666',
        info_bg='#292f36' if dark else '#eef2f6', info='#c1d5eb' if dark else '#375570',
        success_bg='#25382c' if dark else '#eef5ef', success='#a1dab5' if dark else '#286342',
        warning_bg='#493b24' if dark else '#fff5e3', warning='#f0d197' if dark else '#765525',
        danger_bg='#482d2d' if dark else '#fff0ed', danger='#f4b8ad' if dark else '#a13f35')
    if mode=='high-contrast':
        p=palette or QPalette()
        c.update(window=p.color(QPalette.Window).name(), surface=p.color(QPalette.Base).name(),
            text=p.color(QPalette.Text).name(), secondary=p.color(QPalette.Text).name(),
            brand=p.color(QPalette.Highlight).name(), on_brand=p.color(QPalette.HighlightedText).name(),
            brand_hover=p.color(QPalette.Highlight).name(), brand_pressed=p.color(QPalette.Highlight).name(),
            border=p.color(QPalette.Text).name(), soft=p.color(QPalette.Base).name(),
            disabled_bg=p.color(QPalette.Window).name(),disabled_text=p.color(QPalette.Disabled,QPalette.Text).name())
        for status in ('info','success','warning','danger'):
            c[status]=c['text'];c[status+'_bg']=c['surface']
    c.update(selected_bg=c['brand'] if mode=='high-contrast' else c['soft'], selected_text=c['on_brand'] if mode=='high-contrast' else c['text'])
    return c


def core_style(c):
    """Scoped native Widgets QSS. The retained rehab workspace keeps its own style."""
    s='QWidget[visualScope="core"]'
    q=f'''
{s} {{ background:{c['window']}; color:{c['text']}; }}
{s} QLabel {{ background:transparent; color:{c['text']}; font-size:{TYPE['body'][0]}px; }}
{s} QFrame#productCard[fluentCard="true"] {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:{RADIUS['card']}px; }}
{s} QFrame#productHero[fluentCard="hero"] {{ background:{c['soft']}; border:1px solid {c['border']}; border-radius:{RADIUS['hero']}px; }}
{s} QLabel#productTitle {{ font-size:{TYPE['display'][0]}px; color:{c['text']}; }}
{s} QLabel#productMuted {{ color:{c['secondary']}; }}
{s} QPushButton#productPrimary {{ background:{c['brand']}; color:{c['on_brand']}; border:2px solid {c['brand']}; }}
{s} QPushButton#productPrimary:hover {{ background:{c['brand_hover']}; }}
{s} QPushButton#productPrimary:pressed {{ background:{c['brand_pressed']}; }}
{s} QPushButton#productPrimary:focus {{ border-color:{c['text']}; }}
{s} QPushButton#productPrimary:disabled {{ background:{c['disabled_bg']}; color:{c['disabled_text']}; border-color:{c['border']}; }}
{s} QPushButton {{ background:{c['surface']}; color:{c['text']}; border:2px solid {c['border']}; border-radius:{RADIUS['control']}px; padding:8px 12px; min-height:20px; }}
{s} QPushButton:hover {{ background:{c['surface_background_hover']}; }}
{s} QPushButton[fluentAppearance="module"] {{ text-align:left; padding:{SPACING['lg']}px {SPACING['xl']}px; min-height:{METRICS['module_minimum']-2*SPACING['lg']-4}px; border-radius:{RADIUS['card']}px; }}
{s} QPushButton:pressed {{ background:{c['surface_background_pressed']}; }}
{s} QPushButton[fluentAppearance="primary"] {{ background:{c['brand']}; color:{c['on_brand']}; border-color:{c['brand']}; font-weight:600; }}
{s} QPushButton[fluentAppearance="primary"]:hover {{ background:{c['brand_hover']}; }}
{s} QPushButton[fluentAppearance="primary"]:pressed {{ background:{c['brand_pressed']}; }}
{s} QPushButton[fluentAppearance="ghost"] {{ background:transparent; border-color:transparent; color:{c['brand']}; }}
{s} QPushButton[fluentAppearance="ghost"]:hover {{ background:{c['soft']}; }}
{s} QPushButton[fluentAppearance="ghost"]:pressed {{ background:{c['surface_background_pressed']}; }}
{s} QPushButton[fluentAppearance="danger"] {{ color:{c['danger']}; background:{c['danger_bg']}; }}
{s} QPushButton:focus, {s} QPushButton[fluentAppearance]:focus {{ border-color:{c['text']}; }}
{s} QPushButton:disabled, {s} QPushButton[fluentAppearance]:disabled {{ background:{c['disabled_bg']}; color:{c['disabled_text']}; border-color:{c['border']}; }}
{s} QLineEdit, {s} QPlainTextEdit, {s} QTextBrowser, {s} QComboBox {{ background:{c['surface']}; color:{c['text']}; border:2px solid {c['border']}; border-radius:{RADIUS['control']}px; padding:8px; selection-background-color:{c['brand']}; selection-color:{c['on_brand']}; }}
{s} QLineEdit:focus, {s} QPlainTextEdit:focus, {s} QTextBrowser:focus, {s} QComboBox:focus {{ border-color:{c['brand']}; }}
{s} QLineEdit:disabled, {s} QPlainTextEdit:disabled, {s} QComboBox:disabled {{ background:{c['disabled_bg']}; color:{c['disabled_text']}; }}
{s} QLineEdit[validation="error"] {{ border-color:{c['danger']}; }}
{s} QCheckBox {{ color:{c['text']}; spacing:8px; background:transparent; }}
{s} QCheckBox:focus {{ outline:1px solid {c['brand']}; }}
{s} QCheckBox:disabled {{ color:{c['disabled_text']}; }}
{s} QTableWidget, {s} QListWidget {{ background:{c['surface']}; color:{c['text']}; alternate-background-color:{c['surface']}; border:1px solid {c['border']}; border-radius:{RADIUS['control']}px; selection-background-color:{c['soft']}; selection-color:{c['text']}; gridline-color:{c['border']}; }}
{s} QHeaderView::section {{ background:{c['surface']}; color:{c['secondary']}; padding:8px; border:0; border-bottom:1px solid {c['border']}; font-weight:600; }}
{s} QTableWidget::item, {s} QListWidget::item {{ padding:8px; }}
{s} QTableWidget::item:selected, {s} QListWidget::item:selected {{ background:{c['selected_bg']}; color:{c['selected_text']}; }}
{s} QTableWidget:focus, {s} QListWidget:focus {{ border-color:{c['brand']}; }}
{s} QTabWidget::pane {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:{RADIUS['control']}px; }}
{s} QTabBar::tab {{ background:transparent; color:{c['secondary']}; border-bottom:3px solid transparent; padding:10px 16px; }}
{s} QTabBar::tab:hover {{ background:{c['soft']}; }}
{s} QTabBar::tab:selected {{ background:{c['surface']}; color:{c['brand']}; border-bottom-color:{c['brand']}; font-weight:600; }}
{s} QTabBar::tab:focus {{ border-top:1px solid {c['text']}; }}
{s} QTabBar::tab:disabled {{ color:{c['disabled_text']}; }}
{s} QProgressBar {{ border:0; border-radius:4px; background:{c['border']}; max-height:8px; min-height:8px; }}
{s} QProgressBar::chunk {{ background:{c['brand']}; border-radius:4px; }}
'''
    for role,(size,weight) in TYPE.items():
        color=c['secondary'] if role in ('secondary','caption') else c['text']
        q+=f'QLabel[fluentType="{role}"], {s} QLabel[fluentType="{role}"] {{ font-size:{size}px; font-weight:{weight}; color:{color}; }}\n'
    for status in ('info','success','warning','danger'):
        q+=f'{s} QLabel[fluentStatus="{status}"] {{ background:{c[status+"_bg"]}; color:{c[status]}; padding:8px 12px; border-radius:6px; }}\n'
        q+=f'QLabel#productNotice[fluentStatus="{status}"] {{ background:{c[status+"_bg"]}; color:{c[status]}; padding:8px 12px; border-radius:6px; }}\n'

    return q


class ProductTheme:
    """Single theme owner; dark/contrast are validation paths for the three migrated pages."""
    def __init__(self,window):
        self.window=window
        self.apply()

    def apply(self,mode='light',palette=None):
        self.mode=mode;self.colors=design_tokens(mode,palette)
        self.window.setStyleSheet(shell_style(self.colors)+core_style(self.colors))
        p=QPalette(palette or self.window.palette())
        for role,key in ((QPalette.Window,'window'),(QPalette.Base,'surface'),(QPalette.AlternateBase,'surface'),(QPalette.Text,'text'),
                         (QPalette.WindowText,'text'),(QPalette.ButtonText,'text'),(QPalette.Button,'surface'),
                         (QPalette.PlaceholderText,'secondary'),(QPalette.Highlight,'brand'),(QPalette.HighlightedText,'on_brand')):
            p.setColor(role,QColor(self.colors[key]))
        for role in (QPalette.Text,QPalette.WindowText,QPalette.ButtonText):
            p.setColor(QPalette.Disabled,role,QColor(self.colors['disabled_text']))
        self.window.setPalette(p)
        from PySide6.QtWidgets import QAbstractButton
        for button in self.window.findChildren(QAbstractButton):
            name=button.property('iconName')
            if name:button.setIcon(themed_icon(name,self.colors['text']))
        from PySide6.QtWidgets import QWidget
        for widget in self.window.findChildren(QWidget):
            if widget.property('visualScope')=='core':widget.setPalette(p)
        for page in self.window.page_widgets.values():
            for widget in page.findChildren(QWidget):
                if widget is not self.window.legacy and not self.window.legacy.isAncestorOf(widget):
                    widget.setPalette(p)
                    from PySide6.QtWidgets import QAbstractItemView
                    if isinstance(widget,QAbstractItemView):
                        view_palette=QPalette(p);view_palette.setColor(QPalette.Highlight,QColor(self.colors['selected_bg']))
                        view_palette.setColor(QPalette.HighlightedText,QColor(self.colors['selected_text']));widget.setPalette(view_palette)
        self.window.record_dialog.setPalette(p)
        self.window.record_dialog.setStyleSheet('QDialog { background:'+self.colors['window']+'; color:'+self.colors['text']+'; }'+shell_style(self.colors))
        if self.window.snapshot:self.window._render_conversation()


def rehab_product_style(style):
    """Recolor the retained rehabilitation widgets without changing geometry or behavior."""
    def recolor(match):
        code = match.group(0)
        if code.lower() in ('#7048df','#7048cf'):
            return '#252525'
        if code.lower() == '#5c37c6':
            return '#3d3d3d'
        r,g,b = (int(code[i:i+2],16)/255 for i in (1,3,5))
        hue,light,saturation = colorsys.rgb_to_hls(r,g,b)
        if .64 <= hue <= .87:
            r,g,b = colorsys.hls_to_rgb(0,light,0)
            return '#'+''.join(f'{round(v*255):02x}' for v in (r,g,b))
        return code
    return re.sub(r'#[0-9a-fA-F]{6}',recolor,style)

def themed_icon(name,color):
    source=Path(__file__).resolve().parents[2]/'assets/ui/ankang'/f'{name}.svg'
    svg=re.sub(r'#[0-9a-fA-F]{6}',color,source.read_text(encoding='utf-8'))
    icon=QIcon()
    for scale in (1,2):
        pixmap=QPixmap(24*scale,24*scale);pixmap.fill(Qt.transparent)
        painter=QPainter(pixmap);QSvgRenderer(svg.encode('utf-8')).render(painter);painter.end()
        pixmap.setDevicePixelRatio(scale);icon.addPixmap(pixmap)
    return icon


def shell_style(c):
    """One semantic stylesheet for product pages; legacy workspace retains its local owner."""
    return f'''
QWidget {{ font-family:'Microsoft YaHei UI'; }}
QMainWindow#productWindow, QWidget#productRoot {{ background:{c['window']}; color:{c['text']}; font-family:'Microsoft YaHei UI'; font-size:14px; }}
QFrame#productSidebar {{ background:{c['surface']}; border-right:1px solid {c['border']}; }}
QLabel#productBrand {{ font-size:25px; font-weight:700; color:{c['text']}; }}
QLabel#productBrandSub, QLabel#productMuted {{ color:{c['secondary']}; }}
QLabel#productBrandSub {{ font-size:12px; }}
QPushButton#productNav {{ text-align:left; padding:12px 16px; border:2px solid transparent; border-radius:6px; background:transparent; color:{c['secondary']}; font-size:15px; }}
QPushButton#productNav:hover {{ background:{c['soft']}; color:{c['text']}; }}
QPushButton#productNav:checked {{ background:{c['soft']}; color:{c['text']}; font-weight:700; border-left-color:{c['brand']}; }}
QPushButton#productNav:focus {{ border-color:{c['brand']}; }}
QPushButton#productNav:pressed {{ background:{c['surface_background_pressed']}; }}
QFrame#productCard {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:{RADIUS['card']}px; }}
QFrame#productHero {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:{RADIUS['hero']}px; }}
QLabel#productTitle {{ color:{c['text']}; font-size:28px; font-weight:700; }}
QLabel#productSection {{ color:{c['text']}; font-size:18px; font-weight:600; }}
QPushButton, QToolButton {{ background:{c['surface']}; color:{c['text']}; border:2px solid {c['border']}; border-radius:6px; padding:8px 12px; min-height:20px; }}
QPushButton:hover, QToolButton:hover {{ background:{c['surface_background_hover']}; }}
QPushButton:pressed, QToolButton:pressed {{ background:{c['surface_background_pressed']}; }}
QPushButton:focus, QToolButton:focus {{ border-color:{c['brand']}; }}
QPushButton:disabled, QToolButton:disabled {{ color:{c['disabled_text']}; background:{c['disabled_bg']}; }}
QPushButton#productPrimary {{ color:{c['on_brand']}; background:{c['brand']}; border-color:{c['brand']}; font-weight:600; }}
QPushButton#productPrimary:hover {{ background:{c['brand_hover']}; }}
QPushButton#productPrimary:pressed {{ background:{c['brand_pressed']}; }}
QPushButton#productPrimary:focus {{ border-color:{c['secondary']}; }}
QPushButton#productPrimary:disabled {{ background:{c['disabled_bg']}; color:{c['disabled_text']}; border-color:{c['border']}; }}
QPushButton#productDanger {{ color:{c['danger']}; background:{c['danger_bg']}; }}
QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox {{ background:{c['surface']}; color:{c['text']}; border:2px solid {c['border']}; border-radius:6px; padding:8px; selection-background-color:{c['brand']}; selection-color:{c['on_brand']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color:{c['brand']}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ color:{c['disabled_text']}; background:{c['disabled_bg']}; }}
QComboBox QAbstractItemView {{ color:{c['text']}; background:{c['surface']}; selection-background-color:{c['brand']}; selection-color:{c['on_brand']}; }}
QCheckBox {{ color:{c['text']}; spacing:8px; background:transparent; }}
QCheckBox:disabled {{ color:{c['disabled_text']}; }}
QCheckBox:focus {{ outline:1px solid {c['brand']}; }}
QTableWidget, QListWidget {{ color:{c['text']}; background:{c['surface']}; alternate-background-color:{c['surface']}; border:1px solid {c['border']}; border-radius:6px; selection-background-color:{c['soft']}; selection-color:{c['text']}; gridline-color:{c['border']}; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background:{c['selected_bg']}; color:{c['selected_text']}; }}
QTableWidget:focus, QListWidget:focus {{ border-color:{c['brand']}; }}
QHeaderView::section {{ color:{c['secondary']}; background:{c['surface']}; border:0; border-bottom:1px solid {c['border']}; padding:8px; font-weight:600; }}
QTableWidget::item, QListWidget::item {{ padding:8px; }}
QTabWidget::pane {{ border:0; }}
QTabBar::tab {{ color:{c['secondary']}; background:transparent; padding:10px 16px; border-bottom:3px solid transparent; }}
QTabBar::tab:hover {{ background:{c['soft']}; }}
QTabBar::tab:selected {{ color:{c['text']}; background:{c['surface']}; border-bottom-color:{c['brand']}; font-weight:600; }}
QTabBar::tab:focus {{ border-top:1px solid {c['brand']}; }}
QTabBar::tab:disabled {{ color:{c['disabled_text']}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background:{c['window']}; border:0; }}
QScrollBar:vertical {{ width:10px; background:transparent; }}
QScrollBar:horizontal {{ height:10px; background:transparent; }}
QScrollBar::handle {{ background:{c['border']}; border-radius:4px; min-height:32px; min-width:32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QToolTip {{ color:{c['text']}; background:{c['surface']}; border:1px solid {c['border']}; padding:8px; }}
'''
