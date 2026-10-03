"""Ankang desktop visual system: quiet green, clear hierarchy, native controls."""
import re
import colorsys
import json
from pathlib import Path
from PySide6.QtGui import QColor, QPalette

# Product aliases are the only visual values consumed by migrated pages.
SPACING = dict(xs=4, sm=8, md=12, lg=16, xl=24, xxl=32)
RADIUS = dict(control=6, card=12, hero=16)
TYPE = dict(display=(28,700), section=(20,600), card=(16,600),
            body=(14,400), secondary=(14,400), caption=(12,400))
METRICS = dict(overview=300, overview_collapsed=60, chat_minimum=170,
               input_minimum=64, input_maximum=88, reference_width=280, module_minimum=126)


def design_tokens(mode='light', palette=None):
    """Resolve pinned Fluent neutrals; project brand/status aliases stay centralized."""
    source = Path(__file__).resolve().parents[2]/'assets/ui/fluent'
    official = json.loads((source/'fluent2-official-web-theme-tokens.json').read_text(encoding='utf-8'))
    aliases = json.loads((source/'qt-token-map.json').read_text(encoding='utf-8'))['aliases']['colors']
    theme = official['webDarkTheme' if mode=='dark' else 'webLightTheme']
    c = {key:theme[value['token']] for key,value in aliases.items()}
    dark = mode=='dark'
    c.update(window='#1f2522' if dark else '#f6f7f4', surface=c['canvas_background'],
        text=c['text_primary'], secondary=c['text_secondary'],
        brand='#95d4bc' if dark else '#286354', on_brand='#153a2d' if dark else '#ffffff',
        brand_hover='#afe3ce' if dark else '#205446', brand_pressed='#79bba1' if dark else '#194638',
        soft='#283e34' if dark else '#e9f2ec', border='#52645b' if dark else '#d5e0d8',
        disabled_bg='#303833' if dark else '#edf0ec', disabled_text='#acb5ae' if dark else '#606d64',
        info_bg='#283942' if dark else '#edf4f7', info='#b5d5e3' if dark else '#345c6c',
        success_bg='#253e32' if dark else '#eaf3ec', success='#a1dab5' if dark else '#286342',
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
    q+='QPushButton#productNav:focus { border:2px solid #286354; padding:12px 16px; }\n'
    q+='QPushButton#productNav:pressed { background:#d8e8df; }\n'
    return q


class ProductTheme:
    """Single theme owner; dark/contrast are validation paths for the three migrated pages."""
    def __init__(self,window):
        self.window=window
        self.apply()

    def apply(self,mode='light',palette=None):
        self.mode=mode;self.colors=design_tokens(mode,palette)
        self.window.setStyleSheet(PRODUCT_STYLE+core_style(self.colors))
        p=QPalette(palette or self.window.palette())
        for role,key in ((QPalette.Window,'window'),(QPalette.Base,'surface'),(QPalette.Text,'text'),
                         (QPalette.WindowText,'text'),(QPalette.ButtonText,'text'),(QPalette.Button,'surface'),
                         (QPalette.PlaceholderText,'secondary'),(QPalette.Highlight,'brand'),(QPalette.HighlightedText,'on_brand')):
            p.setColor(role,QColor(self.colors[key]))
        for role in (QPalette.Text,QPalette.WindowText,QPalette.ButtonText):
            p.setColor(QPalette.Disabled,role,QColor(self.colors['disabled_text']))
        from PySide6.QtWidgets import QWidget
        for widget in self.window.findChildren(QWidget):
            if widget.property('visualScope')=='core':widget.setPalette(p)
        # Existing non-core pages keep their light stylesheet. Native Qt can
        # retain a system dark palette on their child labels/item views; set
        # their existing light text roles explicitly so data stays readable.
        light=design_tokens('light');compat=QPalette(p)
        for role in (QPalette.Text,QPalette.WindowText):
            compat.setColor(role,QColor(light['text']))
            compat.setColor(QPalette.Disabled,role,QColor(light['disabled_text']))
        for key,page in self.window.page_widgets.items():
            if key not in ('home','assistant','rehab'):
                for widget in page.findChildren(QWidget):widget.setPalette(compat)
        if self.window.snapshot:self.window._render_conversation()


def rehab_product_style(style):
    """Recolor the retained rehabilitation widgets without changing geometry or behavior."""
    def recolor(match):
        code = match.group(0)
        if code.lower() in ('#7048df','#7048cf'):
            return '#285e52'
        if code.lower() == '#5c37c6':
            return '#347360'
        r,g,b = (int(code[i:i+2],16)/255 for i in (1,3,5))
        hue,light,saturation = colorsys.rgb_to_hls(r,g,b)
        if .64 <= hue <= .87:
            r,g,b = colorsys.hls_to_rgb(.43,light,saturation*.60)
            return '#'+''.join(f'{round(v*255):02x}' for v in (r,g,b))
        return code
    return re.sub(r'#[0-9a-fA-F]{6}',recolor,style)

PRODUCT_STYLE = '''
QMainWindow#productWindow { background:#f4f7f5; }
QWidget#productRoot { color:#243b34; font-family:'Microsoft YaHei UI'; font-size:14px; }
QFrame#productSidebar { background:#ffffff; border-right:1px solid #e1e9e4; }
QLabel#productBrand { font-size:25px; font-weight:700; color:#285e52; }
QLabel#productBrandSub { color:#768980; font-size:12px; }
QPushButton#productNav { text-align:left; padding:14px 18px; border:0; border-radius:10px; background:transparent; font-size:15px; }
QPushButton#productNav:hover { background:#f0f6f2; }
QPushButton#productNav:checked { background:#e3f0e9; color:#215d49; font-weight:700; }
QFrame#productCard { background:white; border:1px solid #e1e9e4; border-radius:14px; }
QFrame#productHero { background:#e3eee7; border:0; border-radius:16px; }
QLabel#productTitle { font-size:26px; font-weight:700; color:#243b34; }
QLabel#productSection { font-size:18px; font-weight:700; color:#285e52; }
QLabel#productMuted { color:#708177; }
QLabel#productValue { font-size:23px; font-weight:700; }
QPushButton { background:white; border:1px solid #d8e4dc; border-radius:8px; padding:9px 14px; color:#285e52; }
QPushButton:hover { background:#edf5f0; }
QPushButton:disabled { color:#9aa9a1; background:#f2f5f3; }
QPushButton#productPrimary { background:#285e52; color:white; border:0; font-weight:600; }
QPushButton#productPrimary:hover { background:#347360; }
QPushButton#productDanger { color:#a64f42; background:#fff5f1; border:1px solid #eed8d0; }
QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox { background:white; color:#243b34; border:1px solid #d8e4dc; border-radius:8px; padding:8px; }
QTableWidget, QListWidget { background:white; border:1px solid #e1e9e4; border-radius:9px; alternate-background-color:#f6f9f7; }
QHeaderView::section { background:#edf4ef; border:0; padding:10px; color:#526c5d; }
QTableWidget::item, QListWidget::item { padding:8px; }
QTabWidget::pane { border:0; }
QTabBar::tab { padding:11px 18px; background:#eff4f0; color:#5b7164; }
QTabBar::tab:selected { background:white; color:#285e52; }
QLabel#productNotice { background:#fff5e4; color:#775e2d; padding:10px; border-radius:8px; }
QScrollArea { background:#f4f7f5; border:0; }
QScrollArea > QWidget > QWidget { background:#f4f7f5; }
'''
