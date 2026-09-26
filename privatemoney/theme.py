BLACK = "#000000"
CHARCOAL = "#101013"
CARD = "#151519"
CARD_HOVER = "#1B1B21"
DEEP_VIOLET = "#241B35"
VIOLET = "#BDA0FF"
IVORY = "#F5F2FA"
MUTED = "#A7A2AD"
OUTLINE = "#2D2D35"
POSITIVE = "#74D6A0"
NEGATIVE = "#FF8E9A"
WARNING = "#F4C66D"
BLUE = "#83B7FF"
CYAN = "#71D6D1"

APP_QSS = f"""
QWidget {{ background: {BLACK}; color: {IVORY}; font-family: Inter, 'Noto Sans', 'Segoe UI', sans-serif; font-size: 13px; }}
QLabel {{ background: transparent; }}
QMainWindow {{ background: {BLACK}; }}
QFrame#Sidebar {{ background: {CHARCOAL}; border-right: 1px solid {OUTLINE}; }}
QFrame#TopBar {{ background: {BLACK}; border-bottom: 1px solid {OUTLINE}; }}
QPushButton#VaultToggle {{ background: {CHARCOAL}; color: {IVORY}; border: 1px solid {OUTLINE}; border-radius: 10px; font-size: 18px; padding: 0; }}
QPushButton#VaultToggle:hover {{ background: {DEEP_VIOLET}; border-color: {VIOLET}; }}
QDialog#PasswordDialog {{ background: {CARD}; }}
QLabel#Brand {{ font-size: 20px; font-weight: 700; color: {IVORY}; }}
QLabel#Eyebrow {{ color: {MUTED}; font-size: 11px; font-weight: 600; }}
QPushButton#NavButton {{ text-align: left; padding: 11px 14px; border: 0; border-radius: 10px; background: transparent; color: {MUTED}; font-weight: 600; }}
QPushButton#NavButton:hover {{ background: {CARD_HOVER}; color: {IVORY}; }}
QPushButton#NavButton:checked {{ background: {DEEP_VIOLET}; color: {IVORY}; }}
QFrame#Card {{ background: {CARD}; border: 1px solid {OUTLINE}; border-radius: 16px; }}
QLabel#CardTitle {{ color: {MUTED}; font-size: 12px; font-weight: 600; }}
QLabel#BigNumber {{ color: {IVORY}; font-size: 26px; font-weight: 700; }}
QLabel#DeltaPositive {{ color: {POSITIVE}; font-size: 12px; font-weight: 600; }}
QLabel#DeltaNegative {{ color: {NEGATIVE}; font-size: 12px; font-weight: 600; }}
QLabel#SectionTitle {{ color: {IVORY}; font-size: 18px; font-weight: 700; }}
QLabel#PageTitle {{ color: {IVORY}; font-size: 28px; font-weight: 750; }}
QLabel#PageSubtitle {{ color: {MUTED}; font-size: 13px; }}
QPushButton#Primary {{ background: {VIOLET}; color: #17121F; border: 0; border-radius: 10px; padding: 10px 15px; font-weight: 700; }}
QPushButton#Primary:hover {{ background: #CAB3FF; }}
QPushButton#Secondary {{ background: {CHARCOAL}; color: {IVORY}; border: 1px solid {OUTLINE}; border-radius: 10px; padding: 9px 14px; font-weight: 650; }}
QPushButton#Secondary:hover {{ background: {CARD_HOVER}; }}
QLineEdit, QComboBox {{ background: {CHARCOAL}; border: 1px solid {OUTLINE}; border-radius: 10px; padding: 9px 11px; color: {IVORY}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {VIOLET}; }}
QTableWidget {{ background: {CARD}; alternate-background-color: {CHARCOAL}; border: 1px solid {OUTLINE}; border-radius: 12px; gridline-color: transparent; selection-background-color: {DEEP_VIOLET}; selection-color: {IVORY}; }}
QHeaderView::section {{ background: {CHARCOAL}; color: {MUTED}; border: 0; border-bottom: 1px solid {OUTLINE}; padding: 9px; font-weight: 650; }}
QProgressBar {{ background: {CHARCOAL}; border: 0; border-radius: 5px; min-height: 10px; max-height: 10px; }}
QProgressBar::chunk {{ background: {VIOLET}; border-radius: 5px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #35353D; min-height: 28px; border-radius: 5px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{ background: {CHARCOAL}; color: {IVORY}; border: 1px solid {OUTLINE}; padding: 6px; }}
"""
