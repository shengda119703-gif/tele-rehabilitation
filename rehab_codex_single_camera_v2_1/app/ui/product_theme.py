"""Ankang desktop visual system: quiet green, clear hierarchy, native controls."""
import re
import colorsys


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
