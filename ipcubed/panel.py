"""3D Ayarlari penceresi (Qt): katmanlar, gorunum (renk/saydamlik), maske, kamera, isik."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .settings import Settings

from . import theme as _th


def make_style() -> str:
    """KiCad Gorsellestirme panelinin birebir gorunumu: duz bolumler, siyah/gri sekmeler, #363636 listeler, mavi yuvarlak onay kutulari."""
    ic = _th.ensure_icons()
    return f"""
QWidget {{ background: {_th.PANEL_BG}; color: {_th.TEXT}; font-family: {_th.FONT_CSS}; font-size: {_th.FONT_PT}pt; }}
QLabel {{ background: transparent; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {_th.TAB_LINE}; background: {_th.PANEL_BG}; top: -1px; }}
QTabBar {{ background: {_th.PANEL_BG}; }}
QTabBar::tab {{ background: {_th.TAB_BLACK}; color: {_th.TEXT}; padding: 4px 8px; border: 1px solid {_th.TAB_LINE}; margin-right: -1px; }}
QTabBar::tab:selected {{ background: {_th.BG_ALT}; border-bottom-color: {_th.BG_ALT}; }}
QGroupBox {{ border: none; margin-top: 16px; padding-top: 4px; background: transparent; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 0px; padding: 2px 4px; color: {_th.TEXT}; background: {_th.BAND}; }}
QCheckBox {{ spacing: 6px; padding: 1px 0; background: transparent; }}
QCheckBox::indicator {{ width: 15px; height: 15px; }}
QCheckBox::indicator:unchecked {{ image: url({ic["check_off"]}); }}
QCheckBox::indicator:checked {{ image: url({ic["check_on"]}); }}
QCheckBox::indicator:indeterminate {{ image: url({ic["check_on"]}); }}
QPushButton {{ background: {_th.BG_ALT}; border: 1px solid {_th.INPUT_BORDER}; padding: 3px 10px; border-radius: 0px; }}
QPushButton:hover {{ background: {_th.LIST_SEL}; }}
QSlider::groove:horizontal {{ height: 3px; background: #5a5a5a; }}
QSlider::handle:horizontal {{ background: {_th.ACCENT}; width: 10px; margin: -4px 0; border-radius: 5px; }}
QScrollArea {{ border: none; background: {_th.PANEL_BG}; }}
#listBody {{ background: {_th.BG_LIST}; }}
#listBody QCheckBox, #listBody QLabel {{ background: transparent; }}
QScrollBar:vertical {{ background: #171717; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #8a8a8a; min-height: 24px; border-radius: 3px; margin: 0 1px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QDoubleSpinBox, QLineEdit {{ background: {_th.BG_ALT}; border: 1px solid {_th.INPUT_BORDER}; padding: 2px 4px; border-radius: 0px; }}
QComboBox {{ background: {_th.BG_ALT}; border: 1px solid {_th.INPUT_BORDER}; padding: 2px 6px; border-radius: 0px; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{ image: url({ic["chevron"]}); width: 15px; height: 15px; }}
QComboBox QAbstractItemView {{ background: {_th.BG_ALT}; border: 1px solid {_th.INPUT_BORDER}; selection-background-color: {_th.LIST_SEL}; }}
QTreeWidget, QListWidget {{ background: {_th.BG_LIST}; border: none; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {_th.LIST_SEL}; }}
QToolTip {{ background: {_th.BG_ALT}; color: {_th.TEXT}; border: 1px solid {_th.INPUT_BORDER}; }}
"""


STYLE = None          # SettingsWindow olusturulurken make_style() ile (Qt uygulamasi hazirken) uretilir

from .settings import MASK_PRESETS as _MP

MASK_PRESETS = [(n, p["mask_color"], p["mask_density"], p["mask_haze"], p["silk_color"]) for n, p in _MP.items()]

COLORS = [
    ("mask_color", "Solder mask"),
    ("copper_color", "Copper"),
    ("substrate_color", "Board body (dielectric)"),
    ("silk_color", "Silkscreen"),
    ("bg_top", "Background (top)"),
    ("bg_bottom", "Background (bottom)"),
]

KIND_TR = {"silk": "Silkscreen", "mask": "Solder mask", "cu": "Copper", "diel": "Dielectric", "paste": "Paste"}


class ColorButton(QtWidgets.QPushButton):
    changed = QtCore.Signal(str)

    def __init__(self, color: str):
        super().__init__()
        self.setFixedWidth(46)
        self.set_color(color)
        self.clicked.connect(self._pick)

    def set_color(self, c: str):
        self._c = c
        self.setStyleSheet(f"QPushButton {{ background: {c}; border: 1px solid #6b6b6b; }}")

    def _pick(self):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(self._c), self, "Renk")
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit(c.name())


class SettingsWindow(QtWidgets.QWidget):
    """Sag tik -> '3D Ayarlari' ile viewport'un SOLUNDA acilan gomulu panel (ayri pencere degil)."""

    def __init__(self, cfg: Settings, on_change, on_rebuild_mask=None, on_models_hidden=None):
        super().__init__()
        self.cfg, self.on_change, self.on_rebuild_mask = cfg, on_change, on_rebuild_mask
        self.on_models_hidden = on_models_hidden
        self._sliders = {}
        self._tune = {}
        self.on_close = lambda: None
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)      # ust-duzey degil: stil arka plani acikca ciz
        self.setStyleSheet(make_style())
        self.setFixedWidth(372)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        head = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("3D Settings"); title.setStyleSheet(f"background:{_th.BAND}; padding: 5px 6px;")
        close = QtWidgets.QPushButton("×"); close.setFixedSize(26, 22); close.setToolTip("Close panel"); close.setStyleSheet("font-size: 14pt; padding: 0 0 2px 0; border: none; background: transparent;")
        close.clicked.connect(lambda: self.on_close())
        head.addWidget(title, 1); head.addWidget(close)
        lay.addLayout(head)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setUsesScrollButtons(False)
        self.tabs.tabBar().setExpanding(False)
        lay.addWidget(self.tabs, 1)

        # ---- Katmanlar
        self.layers_page = QtWidgets.QWidget()
        lp = QtWidgets.QVBoxLayout(self.layers_page)
        row = QtWidgets.QHBoxLayout()
        for text, fn in (("Outer layers", self._preset_outer), ("All layers", self._preset_all)):
            b = QtWidgets.QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        lp.addLayout(row)
        sc = QtWidgets.QScrollArea(); sc.setWidgetResizable(True)
        self.layers_body = QtWidgets.QWidget(); self.layers_body.setObjectName("listBody"); self.layers_lay = QtWidgets.QVBoxLayout(self.layers_body)
        self.layers_lay.setContentsMargins(2, 2, 2, 2)
        sc.setWidget(self.layers_body); lp.addWidget(sc, 1)
        self._layer_checks: dict[str, QtWidgets.QCheckBox] = {}
        self._build_misc_checks()
        self.tabs.addTab(self.layers_page, "Layers")

        # ---- Görünüm
        vp = QtWidgets.QWidget(); vl = QtWidgets.QVBoxLayout(vp)
        from .settings import STYLES
        g = QtWidgets.QGroupBox("Appearance style"); sl = QtWidgets.QVBoxLayout(g)
        self.style_combo = QtWidgets.QComboBox()
        for name in STYLES:
            self.style_combo.addItem(name)
        self.style_combo.setPlaceholderText("Choose style…")
        self.style_combo.setCurrentIndex(-1)
        self.style_combo.activated.connect(lambda i: self._apply_style(self.style_combo.itemText(i)))
        sl.addWidget(self.style_combo)
        vl.addWidget(g)
        g = QtWidgets.QGroupBox("Solder mask color"); ml_ = QtWidgets.QHBoxLayout(g)
        self.mask_combo = QtWidgets.QComboBox()
        self.mask_combo.setPlaceholderText("Choose preset…")
        self._fill_mask_combo()
        self.mask_combo.setCurrentIndex(-1)
        self.mask_combo.activated.connect(self._mask_combo_picked)
        imp = QtWidgets.QPushButton("Import…"); imp.setToolTip("Load a color preset file (.json); it is added to the list")
        imp.clicked.connect(self._import_preset)
        ml_.addWidget(self.mask_combo, 1); ml_.addWidget(imp)
        vl.addWidget(g)
        g = QtWidgets.QGroupBox("Colors"); fl = QtWidgets.QFormLayout(g)
        self._colors = {}
        for key, label in COLORS:
            b = ColorButton(getattr(cfg, key)); b.changed.connect(lambda c, k=key: self._set(k, c))
            fl.addRow(label, b); self._colors[key] = b
        exp_b = QtWidgets.QPushButton("Export…"); exp_b.setToolTip("Save the current color and mask settings to a file (.json)")
        exp_b.clicked.connect(self._export_preset)
        fl.addRow(exp_b)
        vl.addWidget(g)
        # yuzey kaplama: acikta kalan bakir (pad, cutout), bakir renginden bagimsiz
        g = QtWidgets.QGroupBox("Surface finish (exposed copper)"); fl = QtWidgets.QFormLayout(g)
        from .stackup import FINISH_COLORS, finish_color
        self._finish_combo = QtWidgets.QComboBox()
        self._finish_combo.addItem("Automatic (board setting)", None)
        for _, col, label in FINISH_COLORS:
            self._finish_combo.addItem(label, col)
        self._finish_btn = ColorButton(cfg.pad_color or finish_color(""))
        self._finish_btn.changed.connect(self._finish_custom)
        self._finish_combo.currentIndexChanged.connect(self._finish_picked)
        fl.addRow("Type", self._finish_combo)
        fl.addRow("Custom color", self._finish_btn)
        vl.addWidget(g)
        self._sync_finish()
        g = QtWidgets.QGroupBox("Transparency"); fl = QtWidgets.QFormLayout(g)
        fl.addRow("Board body", self._pct_slider("substrate_opacity"))
        vl.addWidget(g)
        hint = QtWidgets.QLabel("Use the “Adjust” tab for lighting, reflection, solder mask and camera settings.")
        hint.setWordWrap(True); hint.setStyleSheet("color:#9d9d9d")
        vl.addWidget(hint); vl.addStretch(1)
        self.tabs.addTab(vp, "Appearance")

        # ---- Ayar: dogru degeri bulmak icin canli kaydiricilar
        self._tune = {}
        tp = QtWidgets.QWidget(); tl = QtWidgets.QVBoxLayout(tp)
        sc = QtWidgets.QScrollArea(); sc.setWidgetResizable(True)
        body = QtWidgets.QWidget(); bl = QtWidgets.QVBoxLayout(body); bl.setContentsMargins(0, 0, 4, 0)
        sc.setWidget(body); tl.addWidget(sc, 1)
        for title, rows in (
            ("Lighting", [("light_intensity", "Overall brightness", 0.3, 2.0), ("ambient_level", "Ambient light", 0.0, 1.5),
                      ("key_level", "Key light", 0.0, 3.5), ("fill_level", "Fill light", 0.0, 2.0)]),
            ("Reflections (haze / washed-out look comes from here)", [("env_intensity", "Environment reflection", 0.0, 3.0), ("mask_gloss", "Lacquer gloss", 0.0, 3.0)]),
            ("Solder mask", [("mask_density", "Color filter (density)", 0.0, 1.0), ("mask_haze", "Matte tint (haze)", 0.0, 1.0),
                               ("mask_value", "Color brightness", 0.4, 1.8), ("mask_saturation", "Color saturation", 0.3, 1.8)]),
            ("Components", [("model_saturation", "Saturation", 0.5, 2.2), ("model_contrast", "Contrast", 0.7, 5.0)]),
        ):
            g = QtWidgets.QGroupBox(title); fl = QtWidgets.QFormLayout(g)
            for key, label, lo, hi in rows:
                fl.addRow(label, self._tune_slider(key, lo, hi))
            bl.addWidget(g)
        # Lehim maskesi acikligi (eski "Maske" sekmesi)
        g = QtWidgets.QGroupBox("Solder mask opening"); fl = QtWidgets.QFormLayout(g)
        self.exp = QtWidgets.QDoubleSpinBox(); self.exp.setRange(-0.5, 0.5); self.exp.setDecimals(3); self.exp.setSingleStep(0.01)
        self.exp.setSuffix(" mm")
        self.exp.setValue(cfg.mask_expansion if cfg.mask_expansion is not None else 0.0)
        fl.addRow("Expansion (−: shrink)", self.exp)
        self.tent = QtWidgets.QComboBox()
        self.tent.addItem("Per-via KiCad setting", None)
        self.tent.addItem("All covered (tented)", True)
        self.tent.addItem("All open (mask opening)", False)
        self.tent.setCurrentIndex({None: 0, True: 1, False: 2}.get(cfg.tent_vias, 0))
        fl.addRow("Via covering", self.tent)
        ap = QtWidgets.QPushButton("Apply (rebuild mask)"); ap.clicked.connect(self._apply_mask)
        fl.addRow(ap)
        bl.addWidget(g)
        # Kamera (eski "Kamera" sekmesi) + ViewCube
        g = QtWidgets.QGroupBox("Camera"); fl = QtWidgets.QFormLayout(g)
        self.proj_combo = QtWidgets.QComboBox()
        self.proj_combo.addItem("Perspective", "perspective")
        self.proj_combo.addItem("Orthographic", "orthographic")
        self.proj_combo.setCurrentIndex(1 if getattr(cfg, "projection", "perspective") == "orthographic" else 0)
        self.proj_combo.currentIndexChanged.connect(self._projection_changed)
        fl.addRow("Projection", self.proj_combo)
        self.fov_slider = self._slider("fov_3d", 15, 70)
        self.fov_slider.setEnabled(self.proj_combo.currentData() != "orthographic")
        fl.addRow("Field of view", self.fov_slider)
        fl.addRow("Pitch", self._slider("pitch_3d", 15, 85))
        fl.addRow("Transition time (ms)", self._slider("anim_ms", 0, 2000))
        self.cube_check = QtWidgets.QCheckBox("Show ViewCube")
        self.cube_check.setChecked(cfg.show_view_cube)
        self.cube_check.toggled.connect(lambda v: self._set("show_view_cube", bool(v)))
        fl.addRow(self.cube_check)
        bl.addWidget(g)
        bl.addStretch(1)
        row = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton("Reset"); b.clicked.connect(self._reset_tuning); row.addWidget(b)
        b = QtWidgets.QPushButton("Copy values"); b.setToolTip("Copies the current tuning values to the clipboard")
        b.clicked.connect(self._copy_tuning); row.addWidget(b)
        tl.addLayout(row)
        self.tabs.addTab(tp, "Adjust")

        # ---- Modeller: arama + modele gore gruplu agac (>): grup isareti hepsine uygulanir
        mp2 = QtWidgets.QWidget(); ml2 = QtWidgets.QVBoxLayout(mp2)
        self.model_search = QtWidgets.QLineEdit()
        self.model_search.setPlaceholderText("Search: model name or reference (e.g. 0402, C12, U3)…")
        self.model_search.setClearButtonEnabled(True)
        self.model_search.textChanged.connect(self._filter_models)
        ml2.addWidget(self.model_search)
        self.model_tree = QtWidgets.QTreeWidget()
        self.model_tree.setHeaderHidden(True)
        self.model_tree.setUniformRowHeights(True)
        self.model_tree.itemChanged.connect(self._model_item_changed)
        ml2.addWidget(self.model_tree, 1)
        row = QtWidgets.QHBoxLayout()
        for text, st in (("Show", True), ("Hide", False)):
            b = QtWidgets.QPushButton(text + " (filtered)")
            b.clicked.connect(lambda _=False, v=st: self._set_visible_models(v)); row.addWidget(b)
        b = QtWidgets.QPushButton("Expand/Collapse"); b.clicked.connect(self._toggle_expand); row.addWidget(b)
        ml2.addLayout(row)
        self.model_info = QtWidgets.QLabel("")
        self.model_info.setStyleSheet("color:#9d9d9d")
        ml2.addWidget(self.model_info)
        self._models_busy = False
        self.tabs.addTab(mp2, "Models")

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color: #9d9d9d; padding: 2px 4px;")
        lay.addWidget(self.status)

    # ------------------------------------------------------------------ katman listesi
    def _build_misc_checks(self):
        g = QtWidgets.QGroupBox("Components"); gl = QtWidgets.QVBoxLayout(g)
        for key, label in (("show_comp_top", "Top components"), ("show_comp_bottom", "Bottom components"), ("show_pads", "Pads / vias / holes")):
            cb = QtWidgets.QCheckBox(label); cb.setChecked(getattr(self.cfg, key))
            cb.toggled.connect(lambda v, k=key: self._set(k, v)); gl.addWidget(cb)
        self.layers_lay.addWidget(g)
        self.stack_group = QtWidgets.QGroupBox("Stackup (top to bottom)")
        self.stack_lay = QtWidgets.QVBoxLayout(self.stack_group)
        self.layers_lay.addWidget(self.stack_group)
        self.layers_lay.addStretch(1)

    def set_stack(self, stack):
        """Stackup'tan katman onay kutularini kur."""
        self._sync_finish(getattr(stack, "finish", ""))
        while self.stack_lay.count():
            w = self.stack_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._layer_checks.clear()
        for l in stack.layers:
            if l.kind == "paste":
                continue
            key = l.key
            label = f"{l.name}" if l.kind in ("copper", "silk", "mask") else l.name
            suffix = {"copper": f"  ({l.thickness * 1000:.0f} µm)", "dielectric": f"  ({l.thickness * 1000:.0f} µm)",
                      "mask": f"  ({l.thickness * 1000:.0f} µm)"}.get(l.kind, "")
            cb = QtWidgets.QCheckBox(label + suffix)
            cb.setChecked(self.cfg.visible(key))
            cb.toggled.connect(lambda v, k=key: self._set_layer(k, v))
            self.stack_lay.addWidget(cb); self._layer_checks[key] = cb

    def _set_layer(self, key, v):
        self.cfg.layer_visible[key] = bool(v)
        self.on_change("layer_visible")

    def _sync_checks(self):
        for k, cb in self._layer_checks.items():
            cb.blockSignals(True); cb.setChecked(self.cfg.visible(k)); cb.blockSignals(False)

    def _preset_outer(self):
        self.cfg.layer_visible.clear()
        self.cfg.show_inner_copper = False
        self.cfg.substrate_opacity = 1.0
        self._sliders["substrate_opacity"].blockSignals(True)
        self._sliders["substrate_opacity"].setValue(100)
        self._sliders["substrate_opacity"].blockSignals(False)
        self._sync_checks(); self.on_change("preset")

    def _preset_all(self):
        self.cfg.layer_visible.clear()
        self.cfg.show_inner_copper = True
        self._sliders["substrate_opacity"].blockSignals(True)
        self._sliders["substrate_opacity"].setValue(10)
        self._sliders["substrate_opacity"].blockSignals(False)
        # yalniz kart govdesi saydam olur; lehim maskesi rengi/parlakligi AYNI kalir (maskeleme bozulmaz)
        self.cfg.substrate_opacity = 0.10
        self._sync_checks(); self.on_change("preset")

    # ------------------------------------------------------------------ stiller / maske / kaplama
    # --- Modeller sekmesi -------------------------------------------------------------
    def set_models(self, index: list[dict], hidden: set):
        """Sahnedeki model dizininden agaci kur (grup = model dosyasi, cocuk = tek tek ornek)."""
        self._models_busy = True
        tree = self.model_tree
        tree.clear()
        for grp in index:
            top = QtWidgets.QTreeWidgetItem(tree, [f"{grp['name']}  ({len(grp['items'])})"])
            top.setFlags(top.flags() | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsAutoTristate)
            top.setData(0, QtCore.Qt.UserRole, ("group", grp["name"]))
            top.setToolTip(0, grp["path"])
            for kiid, mi, ref, bottom in grp["items"]:
                ch = QtWidgets.QTreeWidgetItem(top, [f"{ref}   ({'bottom' if bottom else 'top'})"])
                ch.setFlags((ch.flags() | QtCore.Qt.ItemIsUserCheckable) & ~QtCore.Qt.ItemIsAutoTristate)
                ch.setData(0, QtCore.Qt.UserRole, ("item", kiid, mi, ref.lower()))
                ch.setCheckState(0, QtCore.Qt.Unchecked if (kiid, mi) in hidden else QtCore.Qt.Checked)
        for i in range(tree.topLevelItemCount()):          # cocuklardan ust durumu hesapla
            self._refresh_group_state(tree.topLevelItem(i))
        self._models_busy = False
        self._filter_models(self.model_search.text())
        self._update_model_info()

    @staticmethod
    def _refresh_group_state(top):
        n = top.childCount()
        on = sum(1 for i in range(n) if top.child(i).checkState(0) == QtCore.Qt.Checked)
        top.setCheckState(0, QtCore.Qt.Checked if on == n else QtCore.Qt.Unchecked if on == 0 else QtCore.Qt.PartiallyChecked)

    def _collect_hidden(self) -> set:
        hidden = set()
        tree = self.model_tree
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            for j in range(top.childCount()):
                ch = top.child(j)
                if ch.checkState(0) != QtCore.Qt.Checked:
                    d = ch.data(0, QtCore.Qt.UserRole)
                    hidden.add((d[1], d[2]))
        return hidden

    def _model_item_changed(self, item, col):
        if self._models_busy:
            return
        self._models_busy = True
        parent = item.parent()
        if parent is not None:
            self._refresh_group_state(parent)
        self._models_busy = False
        self._update_model_info()
        if self.on_models_hidden:
            self.on_models_hidden(self._collect_hidden())

    def _update_model_info(self):
        total = sum(self.model_tree.topLevelItem(i).childCount() for i in range(self.model_tree.topLevelItemCount()))
        self.model_info.setText(f"{total} instances · {len(self._collect_hidden())} hidden · "
                                f"{self.model_tree.topLevelItemCount()} distinct models")

    def _filter_models(self, text: str):
        q = (text or "").strip().lower()
        tree = self.model_tree
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            gname = top.data(0, QtCore.Qt.UserRole)[1].lower()
            group_hit = (not q) or q in gname
            any_child = False
            for j in range(top.childCount()):
                ch = top.child(j)
                hit = group_hit or q in ch.data(0, QtCore.Qt.UserRole)[3]
                ch.setHidden(not hit)
                any_child |= hit
            top.setHidden(not any_child)
            if q and any_child and not group_hit:
                top.setExpanded(True)                    # referansla eslesince grup kendiliginden acilir

    def _set_visible_models(self, show: bool):
        """Aramada gorunen (suzulmus) tum ornekleri goster/gizle."""
        self._models_busy = True
        tree = self.model_tree
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            if top.isHidden():
                continue
            for j in range(top.childCount()):
                ch = top.child(j)
                if not ch.isHidden():
                    ch.setCheckState(0, QtCore.Qt.Checked if show else QtCore.Qt.Unchecked)
            self._refresh_group_state(top)
        self._models_busy = False
        self._update_model_info()
        if self.on_models_hidden:
            self.on_models_hidden(self._collect_hidden())

    def _toggle_expand(self):
        tree = self.model_tree
        anyopen = any(tree.topLevelItem(i).isExpanded() for i in range(tree.topLevelItemCount()))
        (tree.collapseAll if anyopen else tree.expandAll)()

    # --- Ayar sekmesi: canli kaydiricilar (deger etiketi yaninda) --------------------
    def _tune_slider(self, key, lo, hi):
        w = QtWidgets.QWidget(); h = QtWidgets.QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0)
        s = QtWidgets.QSlider(QtCore.Qt.Horizontal); s.setRange(0, 1000)
        lab = QtWidgets.QLabel(); lab.setMinimumWidth(40); lab.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self._tune[key] = (s, lab, lo, hi)

        def on(v, k=key, lo=lo, hi=hi, lab=lab):
            val = lo + (hi - lo) * v / 1000.0
            lab.setText(f"{val:.2f}")
            self._set(k, round(val, 3))

        s.valueChanged.connect(on)
        h.addWidget(s, 1); h.addWidget(lab)
        self._sync_one(key)
        return w

    def _sync_one(self, key):
        s, lab, lo, hi = self._tune[key]
        val = float(getattr(self.cfg, key))
        s.blockSignals(True)
        s.setValue(int(round((val - lo) / (hi - lo) * 1000)))
        s.blockSignals(False)
        lab.setText(f"{val:.2f}")

    def _sync_tuning(self):
        for k in self._tune:
            self._sync_one(k)
        for k, s in self._sliders.items():
            val = getattr(self.cfg, k, None)
            if val is not None:
                s.blockSignals(True); s.setValue(int(round(val * 100))); s.blockSignals(False)

    def _reset_tuning(self):
        self.cfg.reset_tuning()
        self._sync_tuning()
        self.on_change("tuning")

    def _copy_tuning(self):
        import json
        vals = {k: round(float(getattr(self.cfg, k)), 3) for k in self.cfg.TUNING_KEYS}
        vals["mask_color"] = self.cfg.mask_color
        QtWidgets.QApplication.clipboard().setText(json.dumps(vals, ensure_ascii=False, indent=1))
        self.status.setText("Values copied to clipboard")

    def _apply_style(self, name):
        from .settings import STYLES
        for k, v in STYLES[name].items():
            setattr(self.cfg, k, v)
        for k, b in self._colors.items():
            b.set_color(getattr(self.cfg, k))
        self._sync_tuning()
        self.on_change("style")

    # --- hazir maske renkleri: acilir kutu (+ ice aktarilan ozel ayarlar) -------------------------
    @staticmethod
    def _swatch(color: str) -> QtGui.QIcon:
        pm = QtGui.QPixmap(18, 12)
        pm.fill(QtGui.QColor(color))
        return QtGui.QIcon(pm)

    def _fill_mask_combo(self):
        self.mask_combo.clear()
        for name, col, dens, haze, silk in MASK_PRESETS:
            self.mask_combo.addItem(self._swatch(col), name, dict(mask_color=col, mask_density=dens, mask_haze=haze, silk_color=silk))
        for name, vals in self.cfg.custom_presets.items():
            self.mask_combo.addItem(self._swatch(vals.get("mask_color", "#808080")), name, vals)

    def _mask_combo_picked(self, idx):
        v = self.mask_combo.itemData(idx)
        if not v:
            return
        if set(v) <= {"mask_color", "mask_density", "mask_haze", "silk_color"}:
            self._mask_preset(v["mask_color"], v["mask_density"], v["mask_haze"], v["silk_color"])
        else:
            self._apply_values(v)

    PRESET_KEYS = ("mask_color", "copper_color", "substrate_color", "edge_color", "silk_color", "bg_top", "bg_bottom", "pad_color",
                   "mask_density", "mask_haze", "mask_gloss", "mask_value", "mask_saturation", "substrate_opacity")

    def _apply_values(self, vals: dict):
        for k in self.PRESET_KEYS:
            if k in vals:
                setattr(self.cfg, k, vals[k])
        for k, b in self._colors.items():
            b.set_color(getattr(self.cfg, k))
        self._sync_finish()
        self._sync_tuning()
        self.on_change("preset_values")

    def _export_preset(self):
        import json
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export color settings", "kicad3d_colors.json", "JSON (*.json)")
        if not path:
            return
        data = {k: getattr(self.cfg, k) for k in self.PRESET_KEYS}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
            self.status.setText(f"Exported: {path}")
        except OSError as e:
            self.status.setText(f"Could not save: {e}")

    def _import_preset(self):
        import json
        import os
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import color preset", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                vals = json.load(f)
            vals = {k: vals[k] for k in self.PRESET_KEYS if k in vals}
            if not vals:
                raise ValueError("no valid keys")
        except Exception as e:  # noqa: BLE001
            self.status.setText(f"Could not import: {e}")
            return
        name = os.path.splitext(os.path.basename(path))[0]
        self.cfg.custom_presets[name] = vals
        self.cfg.save()
        self._fill_mask_combo()
        self.mask_combo.setCurrentIndex(self.mask_combo.count() - 1)
        self._apply_values(vals)
        self.status.setText(f"Imported: {name}")

    def _mask_preset(self, color, dens, haze, silk):
        self.cfg.mask_color, self.cfg.mask_density, self.cfg.mask_haze, self.cfg.silk_color = color, dens, haze, silk
        self.cfg.mask_value = self.cfg.mask_saturation = 1.0
        for k, v in (("mask_color", color), ("silk_color", silk)):
            if k in self._colors:
                self._colors[k].set_color(v)
        self._sync_tuning()
        self.on_change("mask_preset")

    def _finish_picked(self, idx):
        col = self._finish_combo.itemData(idx)
        self.cfg.pad_color = col                      # None -> kartin ayari
        self._sync_finish()
        self.on_change("pad_color")

    def _finish_custom(self, c):
        self.cfg.pad_color = c
        self._finish_combo.blockSignals(True)
        self._finish_combo.setCurrentIndex(-1)
        self._finish_combo.blockSignals(False)
        self.on_change("pad_color")

    def _sync_finish(self, stack_finish: str | None = None):
        from .stackup import finish_color
        if stack_finish is not None:
            self._stack_finish = stack_finish
        eff = self.cfg.pad_color or finish_color(getattr(self, "_stack_finish", ""))
        self._finish_btn.set_color(eff)

    # ------------------------------------------------------------------ yardimcilar
    def _projection_changed(self, idx):
        mode = self.proj_combo.itemData(idx)
        self.fov_slider.setEnabled(mode != "orthographic")
        self._set("projection", mode)

    def _apply_mask(self):
        self.cfg.mask_expansion = float(self.exp.value())
        self.cfg.tent_vias = self.tent.currentData()
        if self.on_rebuild_mask:
            self.on_rebuild_mask()

    def _slider(self, key, lo, hi):
        s = QtWidgets.QSlider(QtCore.Qt.Horizontal); s.setRange(lo, hi)
        s.setValue(int(getattr(self.cfg, key)))
        s.valueChanged.connect(lambda v, k=key: self._set(k, type(getattr(self.cfg, k))(v)))
        return s

    _sliders: dict = {}

    def _pct_slider(self, key):
        s = QtWidgets.QSlider(QtCore.Qt.Horizontal); s.setRange(0, 100)
        s.setValue(int(round(getattr(self.cfg, key) * 100)))
        s.valueChanged.connect(lambda v, k=key: self._set(k, v / 100))
        self._sliders[key] = s
        return s

    def _set(self, key, value):
        setattr(self.cfg, key, value)
        self.on_change(key)

    def set_status(self, text: str):
        self.status.setText(text)
