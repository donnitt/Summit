"""Stylesheet builder for Summit.

Summit has exactly two themes: Escuro (dark + purple accent) and Claro
(white + purple accent). There is no accent-color picker anymore — the
brand purple is fixed in both modes to keep the app visually consistent
and to avoid mismatched, low-contrast combinations.
"""

from __future__ import annotations


DEFAULT_ACCENT = "#8562ef"


def _clamp(value: int) -> int:
    return max(0, min(255, value))


def _shade(hex_color: str, amount: float) -> str:
    """Lighten (amount > 0) or darken (amount < 0) a #rrggbb color."""
    color = hex_color.lstrip("#")
    if len(color) == 3:
        color = "".join(channel * 2 for channel in color)
    red, green, blue = (int(color[index:index + 2], 16) for index in (0, 2, 4))
    if amount >= 0:
        red = _clamp(int(red + (255 - red) * amount))
        green = _clamp(int(green + (255 - green) * amount))
        blue = _clamp(int(blue + (255 - blue) * amount))
    else:
        red = _clamp(int(red * (1 + amount)))
        green = _clamp(int(green * (1 + amount)))
        blue = _clamp(int(blue * (1 + amount)))
    return f"#{red:02x}{green:02x}{blue:02x}"


def _on_accent_text(hex_color: str) -> str:
    """Return black or white, whichever reads better on top of hex_color."""
    color = hex_color.lstrip("#")
    if len(color) == 3:
        color = "".join(channel * 2 for channel in color)
    red, green, blue = (int(color[index:index + 2], 16) for index in (0, 2, 4))
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return "#0c0912" if luminance > 0.6 else "#ffffff"


_DARK_TEMPLATE = """
* {{
    font-family: "Segoe UI", "Inter", sans-serif;
    color: #f4f0f8;
    font-size: 13px;
}}
QMainWindow, QWidget#Root, QDialog {{ background: #0c0912; }}
QWidget#Content, QWidget#PageContainer, QStackedWidget#Content {{ background: #0c0912; }}
QWidget#Header {{ background: #0c0912; border-bottom: 1px solid #211a2b; }}
QFrame#WelcomePanel {{ background: #211532; border-right: 1px solid #342346; }}
QWidget#Sidebar {{ background: #110d19; border-right: 1px solid #211a2d; }}
QLabel#Brand {{ font-size: 24px; font-weight: 700; color: #ffffff; }}
QLabel#BrandMark {{ background: {accent}; border-radius: 10px; font-size: 16px; font-weight: 800; color: {on_accent}; }}
QLabel#SectionLabel {{ color: #8c8298; font-size: 9px; font-weight: 700; letter-spacing: 1px; }}
QPushButton#NavButton {{
    border: 0; border-radius: 10px; padding: 11px 14px; text-align: left;
    color: #92899e; background: transparent;
}}
QPushButton#NavButton:hover {{ color: #ded7e8; background: #17111f; }}
QPushButton#NavButton:checked {{ color: #eee8f7; background: #211731; border-left: 3px solid {accent}; }}
QFrame#Insight {{ background: #1b1428; border: 1px solid {accent_border}; border-radius: 13px; }}
QFrame#ReceivablesAlert {{ background: #121b24; border: 1px solid #29445c; border-radius: 14px; }}
QFrame#ReceivableRow {{ background: #17232d; border: 1px solid #263b4c; border-radius: 10px; }}
QLabel#AlertCount {{ color: #9bc9f4; background: #1b3143; border-radius: 8px; padding: 5px 9px; font-size: 10px; font-weight: 700; }}
QLabel#AlertOverdue {{ color: #ff8799; font-size: 10px; font-weight: 700; }}
QLabel#AlertToday {{ color: #ffb377; font-size: 10px; font-weight: 700; }}
QLabel#AlertSoon {{ color: #ffd27d; font-size: 10px; font-weight: 700; }}
QLabel#AlertScheduled {{ color: #8ba6bc; font-size: 10px; }}
QLabel#AccountHint {{ color: #9e8fb0; background: #171120; border: 1px solid #30263a; border-radius: 9px; padding: 10px 12px; }}
QLabel#Muted {{ color: #9c93a8; }}
QLabel#Tiny {{ color: #8d8397; font-size: 10px; }}
QLabel#PageTitle {{ color: #ffffff; font-size: 23px; font-weight: 700; }}
QLabel#PanelTitle {{ color: #f6f2fa; font-size: 14px; font-weight: 700; }}
QLabel#MetricValue {{ color: #ffffff; font-size: 23px; font-weight: 700; }}
QLabel#HeroValue {{ color: #ffffff; font-size: 34px; font-weight: 700; }}
QLabel#Positive {{ color: #4bd7b2; }}
QLabel#Purple {{ color: {accent_soft}; }}
QLabel#Orange {{ color: #ff9d66; }}
QFrame#Card, QFrame#Panel {{
    background: #171120; border: 1px solid #292033; border-radius: 14px;
}}
QFrame#MovementColumn {{
    background: #130e1b; border: 1px solid #292033; border-radius: 14px;
}}
QFrame#MovementCard {{
    background: #1a1423; border: 1px solid #30263a; border-radius: 11px;
}}
QFrame#MovementCard:hover, QFrame#MovementCard:focus {{
    background: #21182d; border: 1px solid {accent_border_strong};
}}
QLabel#ColumnTitle {{ color: #ffffff; font-size: 15px; font-weight: 700; }}
QLabel#ColumnHint {{ color: #7f7588; font-size: 10px; min-height: 25px; }}
QLabel#ColumnTotal {{ color: {accent_soft}; font-size: 12px; font-weight: 700; padding: 2px 0 5px 0; }}
QLabel#MovementTitle {{ color: #f5f0f8; font-size: 12px; font-weight: 650; }}
QLabel#FixedSection {{ color: #8b7e94; font-size: 9px; font-weight: 700; letter-spacing: 1px; }}
QLabel#FixedSubtotal {{ color: #aa9cb2; font-size: 10px; padding-bottom: 2px; }}
QLabel#EmptyState {{
    color: #716778; font-size: 10px; background: #17111f;
    border: 1px dashed #33283e; border-radius: 9px; padding: 14px 10px;
}}
QLabel#ScopePersonal, QLabel#ScopeWork {{
    border-radius: 7px; padding: 3px 6px; font-size: 9px; font-weight: 700;
}}
QLabel#ScopePersonal {{ color: {accent_soft}; background: #2b2140; }}
QLabel#ScopeWork {{ color: #83dcc8; background: #18332d; }}
QFrame#MetricPurple {{ background: #191222; border: 1px solid #30233f; border-radius: 14px; }}
QFrame#MetricGreen {{ background: #151c20; border: 1px solid #243638; border-radius: 14px; }}
QFrame#MetricOrange {{ background: #1d151d; border: 1px solid #37272f; border-radius: 14px; }}
QFrame#MetricBlue {{ background: #151825; border: 1px solid #252d44; border-radius: 14px; }}
QPushButton#Primary {{
    background: {accent}; color: {on_accent}; border: 0; border-radius: 10px;
    padding: 11px 18px; font-weight: 700;
}}
QPushButton#Primary:hover {{ background: {accent_hover}; }}
QPushButton#Primary:pressed {{ background: {accent_press}; }}
QPushButton#PagePrimary {{
    background: {accent}; color: {on_accent}; border: 0; border-radius: 10px;
    padding: 10px 17px; font-weight: 700;
}}
QPushButton#PagePrimary:hover {{ background: {accent_hover}; }}
QPushButton#Secondary {{
    background: #1b1524; color: #b1a7bb; border: 1px solid #33283e;
    border-radius: 9px; padding: 9px 14px;
}}
QPushButton#Secondary:hover {{ border-color: {accent_border_strong}; color: white; }}
QPushButton#Secondary:checked {{ background: {accent}; color: {on_accent}; border-color: {accent}; }}
QFrame#PeriodSwitch {{ background: #171120; border: 1px solid #292033; border-radius: 11px; }}
QPushButton#PeriodOption {{
    background: transparent; color: #a79bb2; border: 0; border-radius: 8px;
    padding: 7px 14px; font-weight: 600; font-size: 12px;
}}
QPushButton#PeriodOption:hover {{ color: #eee8f7; }}
QPushButton#PeriodOption:checked {{ background: {accent}; color: {on_accent}; }}
QPushButton#VisibilityToggle {{
    background: transparent; color: #a79bb2; border: 0; border-radius: 7px;
    padding: 4px 6px; font-size: 13px;
}}
QPushButton#VisibilityToggle:hover {{ color: {accent_soft}; background: #211731; }}
QPushButton#DateField {{
    min-height: 39px; padding: 0 12px; background: #100c16; color: #f5f0fa;
    border: 1px solid #30273a; border-radius: 9px; text-align: left;
}}
QPushButton#DateField:hover, QPushButton#DateField:focus {{ border-color: {accent}; background: #15101d; }}
QComboBox#PeriodSelector {{ min-width: 130px; }}
QPushButton#TextButton {{ background: transparent; border: 0; color: {accent_soft}; padding: 6px; }}
QPushButton#TextButton:hover {{ color: {accent_hover}; }}
QPushButton#ConfirmButton {{
    background: #1c4a40; color: #8ff0d6; border: 1px solid #2c6658;
    border-radius: 8px; padding: 7px 10px; font-size: 10px; font-weight: 700;
}}
QPushButton#ConfirmButton:hover {{ background: #245b4e; border-color: #43a087; color: white; }}
QPushButton#ColumnAdd, QPushButton#InlineAdd {{
    background: #251a34; color: {accent_soft}; border: 1px solid #3a2a4d;
    border-radius: 8px; font-size: 17px; font-weight: 600; padding: 0;
}}
QPushButton#ColumnAdd {{ min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; }}
QPushButton#InlineAdd {{ min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; font-size: 14px; }}
QPushButton#ColumnAdd:hover, QPushButton#InlineAdd:hover {{ background: #34224d; border-color: {accent_border_strong}; color: white; }}
QLineEdit, QTextEdit, QDoubleSpinBox, QSpinBox, QComboBox, QDateEdit {{
    min-height: 39px; padding: 0 12px; background: #100c16; color: #f5f0fa;
    border: 1px solid #30273a; border-radius: 9px; selection-background-color: {accent_press};
}}
QTextEdit {{ padding: 9px 12px; }}
QLineEdit:focus, QTextEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus {{ border: 1px solid {accent}; }}
QLineEdit[placeholderText], QTextEdit[placeholderText] {{ color: #f5f0fa; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: 0; width: 26px; }}
QComboBox QAbstractItemView {{ background: #191321; border: 1px solid #33283e; selection-background-color: {accent_press}; }}
QCheckBox {{ color: #b7aebe; spacing: 9px; padding: 5px 0; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid #554466; border-radius: 5px; background: #100c16; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent_soft}; }}
QPushButton#SmallButton, QPushButton#DangerButton {{
    border-radius: 7px; padding: 6px 9px; font-size: 10px; background: #20182a;
    color: #b8adbf; border: 1px solid #362a42;
}}
QPushButton#SmallButton:hover {{ color: white; border-color: {accent_border_strong}; }}
QPushButton#DangerButton {{ color: #f09aa8; }}
QPushButton#DangerButton:hover {{ background: #351923; border-color: #7a3346; color: #ffc1ca; }}
QPushButton#DangerAction {{
    background: #25131b; color: #f3a0af; border: 1px solid #59303e;
    border-radius: 9px; padding: 9px 14px; font-weight: 600;
}}
QPushButton#DangerAction:hover {{ background: #351923; border-color: #8a3e53; color: #ffd0d7; }}
QLabel#FieldLabel {{ color: #a198aa; font-size: 11px; font-weight: 600; }}
QTableWidget {{
    background: transparent; alternate-background-color: #15101d; border: 0; gridline-color: #282030;
    selection-background-color: #2c2040;
}}
QTableWidget::item {{ padding: 9px; border-bottom: 1px solid #241c2d; }}
QHeaderView::section {{ background: #130e1b; color: #776d82; border: 0; padding: 10px; font-size: 10px; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #342943; min-height: 32px; border-radius: 4px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QProgressBar {{ background: #2a2133; border: 0; border-radius: 4px; min-height: 7px; max-height: 7px; }}
QProgressBar::chunk {{ background: {accent_soft}; border-radius: 4px; }}
QMessageBox {{ background: #171120; }}
QWidget#MiniCalendar {{ background: #171120; border: 1px solid #33283e; border-radius: 14px; }}
QWidget#WindowTitleBar {{ background: transparent; border: 0; }}
QPushButton#WindowControl {{
    background: transparent; border: 0; color: #8c8298; font-size: 13px; font-weight: 600;
}}
QPushButton#WindowControl:hover {{ background: #211a2b; color: #eee8f7; }}
QPushButton#WindowControlDanger {{
    background: transparent; border: 0; color: #8c8298; font-size: 15px; font-weight: 600;
}}
QPushButton#WindowControlDanger:hover {{ background: #7a1830; color: #ffd0d7; }}
"""


_LIGHT_TEMPLATE = """
* {{
    font-family: "Segoe UI", "Inter", sans-serif;
    color: #221f29;
    font-size: 13px;
}}
QMainWindow, QWidget#Root, QDialog {{ background: #f5f3fa; }}
QWidget#Content, QWidget#PageContainer, QStackedWidget#Content {{ background: #f5f3fa; }}
QWidget#Header {{ background: #f5f3fa; border-bottom: 1px solid #e2ddee; }}
QFrame#WelcomePanel {{ background: #ece6f9; border-right: 1px solid #d9cff0; }}
QWidget#Sidebar {{ background: #ffffff; border-right: 1px solid #e6e1f0; }}
QLabel#Brand {{ font-size: 24px; font-weight: 700; color: #221f29; }}
QLabel#BrandMark {{ background: {accent}; border-radius: 10px; font-size: 16px; font-weight: 800; color: {on_accent}; }}
QLabel#SectionLabel {{ color: #9089a0; font-size: 9px; font-weight: 700; letter-spacing: 1px; }}
QPushButton#NavButton {{
    border: 0; border-radius: 10px; padding: 11px 14px; text-align: left;
    color: #665f75; background: transparent;
}}
QPushButton#NavButton:hover {{ color: #221f29; background: #f0ecf9; }}
QPushButton#NavButton:checked {{ color: #221f29; background: {accent_tint}; border-left: 3px solid {accent}; }}
QFrame#Insight {{ background: {accent_tint}; border: 1px solid {accent_border}; border-radius: 13px; }}
QFrame#ReceivablesAlert {{ background: #eaf3fb; border: 1px solid #cfe3f6; border-radius: 14px; }}
QFrame#ReceivableRow {{ background: #ffffff; border: 1px solid #dbe7f2; border-radius: 10px; }}
QLabel#AlertCount {{ color: #1c5e94; background: #d7e9fa; border-radius: 8px; padding: 5px 9px; font-size: 10px; font-weight: 700; }}
QLabel#AlertOverdue {{ color: #d23a52; font-size: 10px; font-weight: 700; }}
QLabel#AlertToday {{ color: #c96a1c; font-size: 10px; font-weight: 700; }}
QLabel#AlertSoon {{ color: #b5860e; font-size: 10px; font-weight: 700; }}
QLabel#AlertScheduled {{ color: #5c7385; font-size: 10px; }}
QLabel#AccountHint {{ color: #6e6479; background: #ffffff; border: 1px solid #e2ddee; border-radius: 9px; padding: 10px 12px; }}
QLabel#Muted {{ color: #6b6278; }}
QLabel#Tiny {{ color: #756c84; font-size: 10px; }}
QLabel#PageTitle {{ color: #221f29; font-size: 23px; font-weight: 700; }}
QLabel#PanelTitle {{ color: #221f29; font-size: 14px; font-weight: 700; }}
QLabel#MetricValue {{ color: #221f29; font-size: 23px; font-weight: 700; }}
QLabel#HeroValue {{ color: #221f29; font-size: 34px; font-weight: 700; }}
QLabel#Positive {{ color: #128f6b; }}
QLabel#Purple {{ color: {accent_press}; }}
QLabel#Orange {{ color: #c9691f; }}
QFrame#Card, QFrame#Panel {{
    background: #ffffff; border: 1px solid #e6e1f0; border-radius: 14px;
}}
QFrame#MovementColumn {{
    background: #f7f4fc; border: 1px solid #e6e1f0; border-radius: 14px;
}}
QFrame#MovementCard {{
    background: #ffffff; border: 1px solid #e2dbef; border-radius: 11px;
}}
QFrame#MovementCard:hover, QFrame#MovementCard:focus {{
    background: {accent_tint}; border: 1px solid {accent_border_strong};
}}
QLabel#ColumnTitle {{ color: #221f29; font-size: 15px; font-weight: 700; }}
QLabel#ColumnHint {{ color: #948b9e; font-size: 10px; min-height: 25px; }}
QLabel#ColumnTotal {{ color: {accent_press}; font-size: 12px; font-weight: 700; padding: 2px 0 5px 0; }}
QLabel#MovementTitle {{ color: #221f29; font-size: 12px; font-weight: 650; }}
QLabel#FixedSection {{ color: #8b8194; font-size: 9px; font-weight: 700; letter-spacing: 1px; }}
QLabel#FixedSubtotal {{ color: #6e6479; font-size: 10px; padding-bottom: 2px; }}
QLabel#EmptyState {{
    color: #948b9e; font-size: 10px; background: #f7f4fc;
    border: 1px dashed #d9d2e6; border-radius: 9px; padding: 14px 10px;
}}
QLabel#ScopePersonal, QLabel#ScopeWork {{
    border-radius: 7px; padding: 3px 6px; font-size: 9px; font-weight: 700;
}}
QLabel#ScopePersonal {{ color: {accent_press}; background: {accent_tint}; }}
QLabel#ScopeWork {{ color: #0f7a5c; background: #dcf3ea; }}
QFrame#MetricPurple {{ background: #f2effa; border: 1px solid #e2d9f5; border-radius: 14px; }}
QFrame#MetricGreen {{ background: #eaf6f0; border: 1px solid #d3ecdf; border-radius: 14px; }}
QFrame#MetricOrange {{ background: #fbf0e8; border: 1px solid #f2ddc8; border-radius: 14px; }}
QFrame#MetricBlue {{ background: #eaf1fb; border: 1px solid #d3e3f5; border-radius: 14px; }}
QPushButton#Primary {{
    background: {accent}; color: {on_accent}; border: 0; border-radius: 10px;
    padding: 11px 18px; font-weight: 700;
}}
QPushButton#Primary:hover {{ background: {accent_hover}; }}
QPushButton#Primary:pressed {{ background: {accent_press}; }}
QPushButton#PagePrimary {{
    background: {accent}; color: {on_accent}; border: 0; border-radius: 10px;
    padding: 10px 17px; font-weight: 700;
}}
QPushButton#PagePrimary:hover {{ background: {accent_hover}; }}
QPushButton#Secondary {{
    background: #ffffff; border: 1px solid #ddd6ea;
    border-radius: 9px; padding: 9px 14px; color: #4a4456;
}}
QPushButton#Secondary:hover {{ border-color: {accent_border_strong}; color: #221f29; }}
QPushButton#Secondary:checked {{ background: {accent}; color: {on_accent}; border-color: {accent}; }}
QFrame#PeriodSwitch {{ background: #f2effa; border: 1px solid #e2d9f5; border-radius: 11px; }}
QPushButton#PeriodOption {{
    background: transparent; color: #665f75; border: 0; border-radius: 8px;
    padding: 7px 14px; font-weight: 600; font-size: 12px;
}}
QPushButton#PeriodOption:hover {{ color: #221f29; }}
QPushButton#PeriodOption:checked {{ background: {accent}; color: {on_accent}; }}
QPushButton#VisibilityToggle {{
    background: transparent; color: #6e6479; border: 0; border-radius: 7px;
    padding: 4px 6px; font-size: 13px;
}}
QPushButton#VisibilityToggle:hover {{ color: {accent_press}; background: {accent_tint}; }}
QPushButton#DateField {{
    min-height: 39px; padding: 0 12px; background: #ffffff; color: #221f29;
    border: 1px solid #ddd6ea; border-radius: 9px; text-align: left;
}}
QPushButton#DateField:hover, QPushButton#DateField:focus {{ border-color: {accent}; background: #fbfaff; }}
QComboBox#PeriodSelector {{ min-width: 130px; }}
QPushButton#TextButton {{ background: transparent; border: 0; color: {accent_press}; padding: 6px; }}
QPushButton#TextButton:hover {{ color: {accent_hover}; }}
QPushButton#ConfirmButton {{
    background: #d8f2e6; color: #0f7a5c; border: 1px solid #b6e6d1;
    border-radius: 8px; padding: 7px 10px; font-size: 10px; font-weight: 700;
}}
QPushButton#ConfirmButton:hover {{ background: #c5ebd9; border-color: #8fd6b4; color: #0a5c44; }}
QPushButton#ColumnAdd, QPushButton#InlineAdd {{
    background: {accent_tint}; color: {accent_press}; border: 1px solid {accent_border};
    border-radius: 8px; font-size: 17px; font-weight: 600; padding: 0;
}}
QPushButton#ColumnAdd {{ min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; }}
QPushButton#InlineAdd {{ min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; font-size: 14px; }}
QPushButton#ColumnAdd:hover, QPushButton#InlineAdd:hover {{ background: {accent_tint_strong}; border-color: {accent_border_strong}; color: #221f29; }}
QLineEdit, QTextEdit, QDoubleSpinBox, QSpinBox, QComboBox, QDateEdit {{
    min-height: 39px; padding: 0 12px; background: #ffffff; color: #221f29;
    border: 1px solid #ddd6ea; border-radius: 9px; selection-background-color: {accent_tint_strong};
}}
QTextEdit {{ padding: 9px 12px; }}
QLineEdit:focus, QTextEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus {{ border: 1px solid {accent}; }}
QLineEdit[placeholderText], QTextEdit[placeholderText] {{ color: #6e6479; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: 0; width: 26px; }}
QComboBox QAbstractItemView {{ background: #ffffff; border: 1px solid #ddd6ea; selection-background-color: {accent_tint_strong}; }}
QCheckBox {{ color: #4a4456; spacing: 9px; padding: 5px 0; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid #cfc6de; border-radius: 5px; background: #ffffff; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QPushButton#SmallButton, QPushButton#DangerButton {{
    border-radius: 7px; padding: 6px 9px; font-size: 10px; background: #f2effa;
    color: #56506e; border: 1px solid #ddd6ea;
}}
QPushButton#SmallButton:hover {{ color: #221f29; border-color: {accent_border_strong}; }}
QPushButton#DangerButton {{ color: #c23652; }}
QPushButton#DangerButton:hover {{ background: #fbe6ea; border-color: #eab0bd; color: #971f38; }}
QPushButton#DangerAction {{
    background: #fbe6ea; color: #971f38; border: 1px solid #eab0bd;
    border-radius: 9px; padding: 9px 14px; font-weight: 600;
}}
QPushButton#DangerAction:hover {{ background: #f6d2da; border-color: #e08fa0; color: #7a1830; }}
QLabel#FieldLabel {{ color: #6e6479; font-size: 11px; font-weight: 600; }}
QTableWidget {{
    background: transparent; alternate-background-color: #f7f4fc; border: 0; gridline-color: #e6e1f0;
    selection-background-color: {accent_tint_strong};
}}
QTableWidget::item {{ padding: 9px; border-bottom: 1px solid #ece7f4; }}
QHeaderView::section {{ background: #f7f4fc; color: #857c92; border: 0; padding: 10px; font-size: 10px; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #ddd6ea; min-height: 32px; border-radius: 4px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QProgressBar {{ background: #ece6f9; border: 0; border-radius: 4px; min-height: 7px; max-height: 7px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}
QMessageBox {{ background: #ffffff; }}
QWidget#MiniCalendar {{ background: #ffffff; border: 1px solid #ddd6ea; border-radius: 14px; }}
QWidget#WindowTitleBar {{ background: transparent; border: 0; }}
QPushButton#WindowControl {{
    background: transparent; border: 0; color: #948b9e; font-size: 13px; font-weight: 600;
}}
QPushButton#WindowControl:hover {{ background: #ece6f9; color: #221f29; }}
QPushButton#WindowControlDanger {{
    background: transparent; border: 0; color: #948b9e; font-size: 15px; font-weight: 600;
}}
QPushButton#WindowControlDanger:hover {{ background: #fbe6ea; color: #971f38; }}
"""


def build_stylesheet(mode: str, accent: str = DEFAULT_ACCENT) -> str:
    """Return the full application stylesheet for the given mode.

    ``accent`` is accepted for backwards compatibility (older saved
    settings may still carry a stored accent color) but is ignored —
    Summit always renders with the fixed brand purple.
    """
    accent = DEFAULT_ACCENT
    tokens = {
        "accent": accent,
        "accent_hover": _shade(accent, 0.15),
        "accent_press": _shade(accent, -0.15),
        "accent_soft": _shade(accent, 0.25),
        "accent_border": _shade(accent, -0.35) if mode == "dark" else _shade(accent, 0.55),
        "accent_border_strong": _shade(accent, -0.05) if mode == "dark" else _shade(accent, 0.15),
        "accent_tint": _shade(accent, 0.88),
        "accent_tint_strong": _shade(accent, 0.78),
        "on_accent": _on_accent_text(accent),
    }
    template = _LIGHT_TEMPLATE if mode == "light" else _DARK_TEMPLATE
    return template.format(**tokens)


# Backwards-compatible default export (dark theme, default accent).
APP_STYLE = build_stylesheet("dark", DEFAULT_ACCENT)
