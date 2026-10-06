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
RADIUS = dict(control=6, card=0, hero=0)
TYPE = dict(display=(30,600), section=(20,600), card=(17,600),
            body=(15,400), secondary=(15,400), caption=(12,400))
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
    c.update(window='#171717' if dark else '#ffffff', surface=c['canvas_background'],
        text=c['text_primary'], secondary=c['text_secondary'],
        brand='#eeeeee' if dark else '#252525', on_brand='#171717' if dark else '#ffffff',
        brand_hover='#ffffff' if dark else '#3d3d3d', brand_pressed='#d6d6d6' if dark else '#111111',
        soft='#303030' if dark else '#ededed', border='#656565' if dark else '#d4d4d4',
        disabled_bg='#303030' if dark else '#eeeeee', disabled_text='#adadad' if dark else '#666666',
        info_bg='#292f36' if dark else '#eef2f6', info='#c1d5eb' if dark else '#375570',
        success_bg='#25382c' if dark else '#eef5ef', success='#a1dab5' if dark else '#286342',
        warning_bg='#493b24' if dark else '#fff5e3', warning='#f0d197' if dark else '#765525',
        danger_bg='#482d2d' if dark else '#fff0ed', danger='#f4b8ad' if dark else '#a13f35')
    # Shared care palette; the existing status aliases retain their meanings.
    c.update(window='#18201b' if dark else '#f7f8f5', surface='#202a23' if dark else '#ffffff',
        text='#edf3ed' if dark else '#25322b',secondary='#b5c2b7' if dark else '#5c6b60',
        brand='#b8d7bc' if dark else '#345b44',on_brand='#18291d' if dark else '#ffffff',
        brand_hover='#cee4ce' if dark else '#264a35',brand_pressed='#a2c4a6' if dark else '#1f3d2c',
        soft='#2b392f' if dark else '#e9efe7',border='#526456' if dark else '#cbd6cb',
        surface_background_hover='#303e33' if dark else '#edf2eb',
        surface_background_pressed='#35483a' if dark else '#dce7d9')
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
{s} QFrame#productCard[fluentCard="true"] {{ background:transparent; border:0; border-top:1px solid {c['border']}; border-radius:0px; }}
{s} QFrame#productHero[fluentCard="hero"] {{ background:{c['surface']}; border:0; border-left:3px solid {c['brand']}; border-radius:0px; }}
{s} QLabel#productTitle {{ font-size:{TYPE['display'][0]}px; color:{c['text']}; }}
{s} QLabel#productMuted {{ color:{c['secondary']}; }}
{s} QFrame#careConversation {{ background:{c['soft']}; border:0; border-radius:12px; }}
{s} QFrame#careNext {{ background:{c['soft']}; border:0; border-left:4px solid {c['brand']}; border-radius:12px; }}
{s} QWidget#carePlanTools {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:8px; }}
{s} QLabel[careSchedule="true"] {{ padding:16px 0; font-size:16px; }}
{s} QLabel[careInstruction="true"] {{ font-size:16px; }}
{s} QLabel[careSummary="true"] {{ background:{c['soft']}; border:0; border-radius:8px; padding:18px; }}
{s} QLabel[careEmpty="true"] {{ background:transparent; color:{c['secondary']}; padding:12px 0; }}
{s} QPushButton#productPrimary {{ background:{c['brand']}; color:{c['on_brand']}; border:1px solid {c['brand']}; }}
{s} QPushButton#productPrimary:hover {{ background:{c['brand_hover']}; }}
{s} QPushButton#productPrimary:pressed {{ background:{c['brand_pressed']}; }}
{s} QPushButton#productPrimary:focus {{ border-color:{c['text']}; }}
{s} QPushButton#productPrimary:disabled {{ background:{c['disabled_bg']}; color:{c['disabled_text']}; border-color:{c['border']}; }}
{s} QPushButton {{ background:{c['surface']}; color:{c['text']}; border:1px solid {c['border']}; border-radius:{RADIUS['control']}px; padding:8px 12px; min-height:20px; }}
{s} QPushButton:hover {{ background:{c['surface_background_hover']}; }}
{s} QPushButton[fluentAppearance="module"] {{ background:transparent; text-align:left; padding:12px 4px; border:0; border-bottom:1px solid {c['border']}; border-radius:0; font-size:16px; }}
{s} QPushButton[moduleLead="true"] {{ font-size:21px; font-weight:600; }}
{s} QListWidget[readingSurface="true"], {s} QTextBrowser[readingSurface="true"] {{ border:0; padding:10px 0; background:transparent; }}
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
{s} QPushButton[careSend="true"][careCharged="false"]:enabled {{ background:{c['soft']}; color:{c['secondary']}; border-color:{c['border']}; }}
{s} QLineEdit, {s} QPlainTextEdit, {s} QTextBrowser, {s} QComboBox {{ background:{c['surface']}; color:{c['text']}; border:1px solid {c['border']}; border-radius:{RADIUS['control']}px; padding:8px; selection-background-color:{c['brand']}; selection-color:{c['on_brand']}; }}
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
{s} QTabWidget::pane {{ background:{c['window']}; border:0; padding-top:14px; }}
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
        from .theme import STYLE
        self.window.legacy.setStyleSheet(rehab_product_style(STYLE,self.colors))
        from .body_map import BodyMap
        for body in self.window.legacy.findChildren(BodyMap):
            # Existing illustrated control has an intentional local stylesheet.
            # Reuse its state/geometry rules and only supply semantic colors.
            if not hasattr(body,'_care_source_style'):body._care_source_style=body.styleSheet()
            body._care_colors=self.colors
            body.setStyleSheet(rehab_product_style(body._care_source_style,self.colors))
            body.update()
        p=QPalette(palette or self.window.palette())
        for role,key in ((QPalette.Window,'window'),(QPalette.Base,'surface'),(QPalette.AlternateBase,'surface'),(QPalette.Text,'text'),
                         (QPalette.WindowText,'text'),(QPalette.ButtonText,'text'),(QPalette.Button,'surface'),
                         (QPalette.PlaceholderText,'secondary'),(QPalette.Link,'text'),(QPalette.LinkVisited,'text'),(QPalette.Highlight,'brand'),(QPalette.HighlightedText,'on_brand')):
            p.setColor(role,QColor(self.colors[key]))
        for role in (QPalette.Text,QPalette.WindowText,QPalette.ButtonText):
            p.setColor(QPalette.Disabled,role,QColor(self.colors['disabled_text']))
        self.window.setPalette(p)
        from PySide6.QtWidgets import QAbstractButton
        for button in self.window.findChildren(QAbstractButton):
            name=button.property('iconName')
            if name:button.setIcon(themed_icon(name,self.colors['text']))
        from PySide6.QtWidgets import QWidget, QTextEdit
        from PySide6.QtGui import QFont
        family='Microsoft YaHei UI'
        font=QFont(family,10)
        font.setHintingPreference(QFont.PreferNoHinting)
        self.window.setFont(font)
        for widget in self.window.findChildren(QWidget):
            if widget.property('visualScope')=='core':widget.setPalette(p)
        for page in self.window.page_widgets.values():
            for widget in page.findChildren(QWidget):
                if widget is not self.window.legacy and not self.window.legacy.isAncestorOf(widget):
                    widget.setPalette(p)
                    widget.setFont(font)
                    if isinstance(widget,QTextEdit):widget.document().setDefaultFont(font)
                    from PySide6.QtWidgets import QAbstractItemView
                    if isinstance(widget,QAbstractItemView):
                        view_palette=QPalette(p);view_palette.setColor(QPalette.Highlight,QColor(self.colors['selected_bg']))
                        view_palette.setColor(QPalette.HighlightedText,QColor(self.colors['selected_text']));widget.setPalette(view_palette)
        from .product_segments import SegmentBar
        for bar in self.window.findChildren(SegmentBar):
            segment_palette=QPalette(p)
            segment_palette.setColor(QPalette.AlternateBase,QColor(self.colors['soft']))
            segment_palette.setColor(QPalette.Base,QColor(self.colors['brand'] if mode=='high-contrast' else self.colors['window']))
            segment_palette.setColor(QPalette.Text,QColor(self.colors['on_brand'] if mode=='high-contrast' else self.colors['text']))
            segment_palette.setColor(QPalette.WindowText,QColor(self.colors['secondary']))
            bar.setPalette(segment_palette);bar.update()
        from PySide6.QtWidgets import QDateEdit
        for day in self.window.findChildren(QDateEdit):
            if day.calendarPopup():
                calendar=day.calendarWidget();calendar.setPalette(p)
                for view in calendar.findChildren(QAbstractItemView):view.setPalette(p)
                for name,direction in (('qt_calendar_prevmonth',-1),('qt_calendar_nextmonth',1)):
                    control=calendar.findChild(QAbstractButton,name)
                    if control:control.setIcon(calendar_arrow(direction,self.colors['text']))
        self.window.record_dialog.setPalette(p)
        self.window.record_dialog.setStyleSheet('QDialog { background:'+self.colors['window']+'; color:'+self.colors['text']+'; }'+shell_style(self.colors))
        if self.window.snapshot:
            self.window._render_conversation()
            if hasattr(self.window,'product_theme'):self.window._experience_render()


def rehab_product_style(style,colors=None):
    """Recolor the retained rehabilitation widgets without changing geometry or behavior."""
    c=colors or design_tokens()
    def recolor(match):
        code = match.group(0)
        if code.lower() in ('#7048df','#7048cf'):
            return c['brand']
        if code.lower() == '#5c37c6':
            return c['brand_hover']
        r,g,b = (int(code[i:i+2],16)/255 for i in (1,3,5))
        hue,light,saturation = colorsys.rgb_to_hls(r,g,b)
        if .64 <= hue <= .87:
            if light>.92:return c['window']
            if light>.85:return c['soft']
            if light>.7:return c['border']
            if saturation>.4:return c['brand']
            return c['text'] if light<.3 else c['secondary']
        # Existing semantic status hues stay status hues in both themes.
        if saturation>.15:
            status='success' if .2<hue<.5 else 'info' if .5<=hue<.64 else 'warning' if .05<hue<.2 else 'danger'
            return c[status+'_bg'] if light>.7 else c[status]
        if light>.96:return c['surface']
        if light>.85:return c['soft']
        if light>.65:return c['border']
        return c['text'] if light<.3 else c['secondary']
    adapted=re.sub(r'#[0-9a-fA-F]{6}',recolor,style)
    adapted=re.sub(r'background\s*:\s*white\b', 'background:'+c['surface'], adapted)
    adapted=re.sub(r'(?<![-\w])color\s*:\s*white\b', 'color:'+c['on_brand'], adapted)
    adapted+=f"\nQPushButton#primary:disabled {{ color:{c['disabled_text']}; background:{c['disabled_bg']}; border-color:{c['border']}; }}"
    return adapted

def themed_icon(name,color):
    source=Path(__file__).resolve().parents[2]/'assets/ui/ankang'/f'{name}.svg'
    svg=re.sub(r'#[0-9a-fA-F]{6}',color,source.read_text(encoding='utf-8'))
    icon=QIcon()
    for scale in (1,2):
        pixmap=QPixmap(24*scale,24*scale);pixmap.fill(Qt.transparent)
        painter=QPainter(pixmap);QSvgRenderer(svg.encode('utf-8')).render(painter);painter.end()
        pixmap.setDevicePixelRatio(scale);icon.addPixmap(pixmap)
    return icon


def calendar_arrow(direction,color):
    """Recolor the existing native calendar buttons; keep their handlers and names."""
    path='m14 6-6 6 6 6' if direction<0 else 'm10 6 6 6-6 6'
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="{path}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    icon=QIcon()
    for scale in (1,2):
        pixmap=QPixmap(20*scale,20*scale);pixmap.fill(Qt.transparent)
        painter=QPainter(pixmap);QSvgRenderer(svg.encode()).render(painter);painter.end()
        pixmap.setDevicePixelRatio(scale);icon.addPixmap(pixmap)
    return icon


def shell_style(c):
    """One semantic stylesheet for product pages; legacy workspace retains its local owner."""
    check=(Path(__file__).resolve().parents[2]/'assets/ui'/('check-dark.svg' if QColor(c['on_brand']).lightness()<128 else 'check.svg')).as_posix()
    chevron=(Path(__file__).resolve().parents[2]/'assets/ui'/('chevron-dark.svg' if QColor(c['text']).lightness()>128 else 'chevron.svg')).as_posix()
    return f'''
QWidget {{ font-size:14px; font-family:'Microsoft YaHei UI'; }}
QMainWindow#productWindow, QWidget#productRoot {{ background:{c['window']}; color:{c['text']}; font-family:'Microsoft YaHei UI'; font-size:14px; }}
QFrame#productSidebar {{ background:{c['window']}; border-right:1px solid {c['border']}; }}
QLabel#productBrand {{ font-size:25px; font-weight:700; color:{c['text']}; }}
QLabel#productBrandSub, QLabel#productMuted {{ color:{c['secondary']}; }}
QLabel#productBrandSub {{ font-size:12px; }}
QPushButton#productNav {{ text-align:left; padding:10px 14px; border:1px solid transparent; border-radius:7px; background:transparent; color:{c['secondary']}; font-size:15px; }}
QPushButton#productNav:hover {{ background:{c['soft']}; color:{c['text']}; }}
QPushButton#productNav:checked {{ background:transparent; color:{c['brand']}; font-weight:700; border-left-color:transparent; }}
QPushButton#productNav:focus {{ border-color:{c['brand']}; }}
QPushButton#productNav:pressed {{ background:{c['surface_background_pressed']}; }}
QFrame#productCard {{ background:transparent; border:0; border-top:1px solid {c['border']}; border-radius:0px; }}
QFrame#productHero {{ background:{c['surface']}; border:1px solid {c['border']}; border-radius:{RADIUS['hero']}px; }}
QLabel#productTitle {{ color:{c['text']}; font-size:20px; font-weight:600; }}
QLabel#productSection {{ color:{c['text']}; font-size:18px; font-weight:600; }}
QPushButton, QToolButton {{ background:{c['surface']}; color:{c['text']}; border:1px solid {c['border']}; border-radius:6px; padding:8px 12px; min-height:20px; }}
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
QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox {{ background:{c['surface']}; color:{c['text']}; border:1px solid {c['border']}; border-radius:6px; padding:8px; selection-background-color:{c['brand']}; selection-color:{c['on_brand']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color:{c['brand']}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ color:{c['disabled_text']}; background:{c['disabled_bg']}; }}
QComboBox QAbstractItemView {{ color:{c['text']}; background:{c['surface']}; selection-background-color:{c['brand']}; selection-color:{c['on_brand']}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ subcontrol-origin:padding; subcontrol-position:top right; width:28px; border:0; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image:url("{chevron}"); width:14px; height:14px; }}
QComboBox {{ padding-right:30px; }}
QDateEdit, QTimeEdit {{ color:{c['text']}; background:{c['surface']}; border:1px solid {c['border']}; border-radius:6px; padding:8px 12px; min-height:20px; }}
QDateEdit:focus, QTimeEdit:focus {{ border-color:{c['brand']}; }}
QDateEdit:disabled, QTimeEdit:disabled {{ color:{c['disabled_text']}; background:{c['disabled_bg']}; }}
QCalendarWidget QWidget {{ background:{c['window']}; color:{c['text']}; }}
QCalendarWidget QAbstractItemView {{ background:{c['window']}; color:{c['text']}; selection-background-color:{c['brand']}; selection-color:{c['on_brand']}; }}
QCalendarWidget QToolButton {{ color:{c['text']}; background:{c['soft']}; border:0; border-radius:4px; padding:4px 8px; }}
QCalendarWidget QToolButton:hover {{ background:{c['surface_background_hover']}; }}
QCalendarWidget QSpinBox {{ background:{c['surface']}; color:{c['text']}; }}
QCheckBox {{ color:{c['text']}; spacing:8px; background:transparent; }}
QCheckBox:disabled {{ color:{c['disabled_text']}; }}
QCheckBox:focus {{ outline:1px solid {c['brand']}; }}
QCheckBox::indicator {{ width:18px; height:18px; border:1px solid {c['secondary']}; border-radius:3px; background:{c['surface']}; }}
QCheckBox::indicator:checked {{ background:{c['brand']}; border-color:{c['brand']}; image:url("{check}"); }}
QCheckBox::indicator:disabled {{ border-color:{c['border']}; background:{c['disabled_bg']}; }}
QCheckBox::indicator:checked:disabled {{ background:{c['brand']}; border-color:{c['brand']}; }}
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
QFrame#productSelectionRail {{ background:{c['soft']}; border:0; border-left:3px solid {c['brand']}; border-radius:7px; }}
QTextBrowser[readingSurface="true"] {{ border:0; padding:12px 0; background:transparent; }}
QPushButton[fluentAppearance="module"] {{ border:0; border-bottom:1px solid {c['border']}; border-radius:0; text-align:left; padding:14px 0; }}
QFrame#assistantComposer {{ background:{c['soft']}; border:1px solid {c['border']}; border-radius:18px; }}
QPlainTextEdit#assistantEditor {{ background:transparent; border:0; padding:0; }}
QPlainTextEdit#assistantEditor:focus {{ border:0; }}
QToolTip {{ color:{c['text']}; background:{c['surface']}; border:1px solid {c['border']}; padding:8px; }}
'''
