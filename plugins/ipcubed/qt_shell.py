"""Qt kabugu: pencere(ler), zamanlayici, kontrol sunucusu, gosterme/gizleme + animasyon."""
from __future__ import annotations

import sys

from . import compat  # noqa: F401
from PySide6 import QtCore, QtGui, QtNetwork, QtWidgets

from .paths import config_dir

TITLE = "IPCubed"


def _log(msg: str):
    from .log import _log as log
    log(msg)


def port_file():
    from .ctl import port_path
    return port_path()                    # KiCad ornegi basina ayri (ayni anda iki KiCad: iki viewer)


def kicad_running() -> bool:
    """Bagli KiCad (bilinmiyorsa herhangi bir KiCad: proje yoneticisi ya da tek basina pcbnew) calisiyor mu? kicad-cli sayilmaz."""
    import psutil
    from .ctl import kicad_pid
    pid = kicad_pid()
    if pid is not None:
        try:
            return psutil.Process(pid).is_running() and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            return False
    for p in psutil.process_iter(["name"]):
        n = (p.info["name"] or "").lower()
        if (n.startswith("kicad") or n.startswith("pcbnew")) and "cli" not in n:
            return True
    return False


def _debug_log_hint() -> str:
    import os
    import tempfile
    return os.path.join(tempfile.gettempdir(), "ipcubed.log")


class ViewerFrame(QtWidgets.QWidget):
    """Gorunum penceresi: solda (istege bagli) 3D Ayarlari paneli + sagda 3D viewport. KiCad uzerine bindirilen / harici pencere olan bu."""
    closed = QtCore.Signal()

    def closeEvent(self, e):
        e.ignore()                  # kapatma istegini kabuk yonetir (harici pencerede: KiCad'e don + gizle)
        self.closed.emit()


def _rec_icon() -> QtGui.QIcon:
    """Kirmizi kayit (canli) noktasi."""
    pm = QtGui.QPixmap(16, 16)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor("#e5322d"))
    p.drawEllipse(2, 2, 12, 12)
    p.end()
    return QtGui.QIcon(pm)


class ViewerShell(QtCore.QObject):
    def __init__(self, embed: bool = True, show_now: bool = False, persist: bool = False):
        super().__init__()
        from rendercanvas.qt import QRenderWidget  # Qt secildikten sonra

        from .core import ViewerCore
        from .panel import SettingsWindow
        from .settings import Settings

        self.cfg = Settings.load()
        # vsync kapali: kare suresi 16.7 ms'yi biraz asinca 60'tan 30 FPS'e dusmesin (ekran 60 Hz)
        self.canvas = QRenderWidget(vsync=False)
        self.core = ViewerCore(self.canvas, self.cfg)
        self.settings_win = SettingsWindow(self.cfg, self._on_setting, self._rebuild_mask, self._on_models_hidden)
        self.core.on_status = self.settings_win.set_status
        self.core.on_snapshot = self._on_snapshot
        self.core.on_cube_toggled = self._cube_toggled
        self.core.on_layers_changed = self._layers_changed
        self.settings_win.on_close = self.close_settings
        self.settings_win.hide()
        self.frame = ViewerFrame()                 # [3D Ayarlari paneli | viewport]
        fl = QtWidgets.QHBoxLayout(self.frame)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(0)
        fl.addWidget(self.settings_win)
        fl.addWidget(self.canvas, 1)
        self.frame.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.frame.setStyleSheet("ViewerFrame { background: #2b2b2b; }")
        self.frame.closed.connect(self._on_frame_closed)
        self._external = False

        self.embedder = None
        if embed:
            try:
                from .embed import make_embedder
                self.embedder = make_embedder()
            except Exception as e:  # noqa: BLE001
                print("gomme kullanilamiyor:", e)
        self.embedded = self.embedder is not None

        self.container = None
        if not self.embedded:
            self.container = self.frame           # bagimsiz mod: kendi penceresi
            self.frame.setWindowTitle(TITLE)
            self._window_min_size(True)
            self.frame.resize(1400, 900)
        else:
            self.embedder.prepare(self.frame)     # bindirme: boyut KiCad'in canvas'indan gelir; Qt minimumu onu ezmesin

        self.canvas.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._context_menu)
        QtGui.QShortcut(QtGui.QKeySequence("3"), self.frame, activated=self.toggle)
        QtGui.QShortcut(QtGui.QKeySequence("Esc"), self.frame, activated=self._esc)
        QtGui.QShortcut(QtGui.QKeySequence("2"), self.frame, activated=self.hide3d)

        self._persist = persist                   # False: KiCad tamamen kapaninca daemon da cikar
        self._closing = False
        self._pending_show = False
        self._shown = False
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(8)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self.core.on_loaded = self._on_loaded

        self.server = QtNetwork.QTcpServer(self)
        self.server.newConnection.connect(self._on_conn)
        self.server.listen(QtNetwork.QHostAddress.LocalHost, 0)
        port_file().write_text(str(self.server.serverPort()))

        if not self.embedded:
            self._editor_up = True
            self.core.start_sync()
        if show_now:
            self.show3d()

    # ------------------------------------------------------------ ayarlar / menu
    def _on_setting(self, key: str):
        self.core.vs.apply_settings()
        if key == "projection":
            self.core.rig.set_projection(self.cfg.projection == "orthographic", self.cfg.fov_3d)
        elif key in ("fov_3d", "pitch_3d"):
            self.rig_refresh()
        self._schedule_save()
        self.core.request_draw()

    def _schedule_save(self):
        """Kaydirici surukleme gibi sik degisikliklerde diske her seferinde yazma: 600 ms sessizlikten sonra tek yazim."""
        if not hasattr(self, "_save_timer"):
            self._save_timer = QtCore.QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(600)
            self._save_timer.timeout.connect(self.cfg.save)
        self._save_timer.start()

    def _on_models_hidden(self, hidden: set):
        self.core.vs.set_hidden(hidden)
        self.core.request_draw()

    def _on_snapshot(self, snap):
        self.settings_win.set_models(self.core.vs.model_index(), self.core.vs.hidden)
        if snap.stack is not None:
            self.settings_win.set_stack(snap.stack)
        if snap.mask_expansion is not None and self.cfg.mask_expansion is None:
            self.settings_win.exp.setValue(snap.mask_expansion)

    def _rebuild_mask(self):
        self.core.vs.rebuild_mask()
        self.cfg.save()

    def _context_menu(self, pos):
        """Sag tik (surukleme degil) -> menu."""
        if self.core.travel > 6:
            return
        from .ctxmenu import build_menu
        c = self.core
        menu, A = build_menu(self.canvas, self.settings_win.isVisible(), self.embedded, self._external, self.cfg.show_view_cube, self.cfg.show_stats,
                             hl_active=c.highlight_active(), has_sel=bool(c.hl.selected), can_2d=c.sync is not None,
                             exploded=c.exploded, show_diel=not c.vs.ex_hide_diel,
                             poly_opacity=self.cfg.polygon_opacity, on_poly=self._set_poly_opacity,
                             pth_opacity=self.cfg.pth_opacity, on_pth=self._set_pth_opacity,
                             hl_polygons=self.cfg.highlight_polygons)
        a_set, a_ref, a_ext, a_ret, a_2d = A["settings"], A["refresh"], A["external"], A["return"], A["to2d"]
        act = menu.exec(self.canvas.mapToGlobal(pos))
        if act is None:
            return
        if act is a_set:
            self.toggle_settings()
        elif act is A["stats"]:
            self.core.toggle_stats()
        elif act is A["cube"]:
            self.core.toggle_cube()
        elif act is a_ref:
            self.core.refresh_all()
        elif act is a_ext:
            self.go_external()
        elif act is a_ret:
            self.return_to_kicad()
        elif act is a_2d:
            self.hide3d()
        elif act is A["explode"]:
            self.core.toggle_explode()
        elif act is A["hlpoly"]:
            self.cfg.highlight_polygons = not self.cfg.highlight_polygons
            self.core.vs.apply_settings()
            self.core.request_draw()
            self._schedule_save()
        elif act is A["diel"]:
            self.core.vs.ex_hide_diel = not self.core.vs.ex_hide_diel
            self.core.vs.apply_settings()
            self.core.request_draw()
        elif act is A["nethl"]:
            self.core.start_picker()
        elif act is A["stophl"]:
            self.core.stop_highlight()
        elif act is A["hl2d"]:
            self.core.highlight_2d()

    def _esc(self):
        """ESC: once net vurgusunu kapat, vurgu yoksa 2D'ye don."""
        if self.core.highlight_active():
            self.core.stop_highlight()
        else:
            self.hide3d()

    def _set_poly_opacity(self, v: float):
        """Exploded view: zone/pour opakligi (menudeki kaydirici, canli)."""
        self.cfg.polygon_opacity = float(v)
        self.core.vs.apply_settings()
        self.core.request_draw()
        self._schedule_save()

    def _set_pth_opacity(self, v: float):
        """Exploded view: PTH / via tup opakligi (menudeki kaydirici, canli)."""
        self.cfg.pth_opacity = float(v)
        self.core.vs.apply_settings()
        self.core.request_draw()
        self._schedule_save()

    def _layers_changed(self, key: str):
        """Gizmo'nun kucuk kupuyle katman ac/kapat: paneldeki onay kutusu da guncellensin."""
        cb = self.settings_win._layer_checks.get(key)
        if cb is not None:
            cb.blockSignals(True); cb.setChecked(self.cfg.visible(key)); cb.blockSignals(False)
        self._schedule_save()

    def _cube_toggled(self, on: bool):
        cb = self.settings_win.cube_check
        cb.blockSignals(True); cb.setChecked(on); cb.blockSignals(False)

    def toggle_settings(self):
        """3D Ayarlari panelini viewport'un solunda ac / kapat."""
        self.settings_win.setVisible(not self.settings_win.isVisible())
        self.core.request_draw()

    def close_settings(self):
        self.settings_win.hide()
        self.core.request_draw()

    def _window_min_size(self, on: bool):
        """Kendi penceresi olunca makul minimum; bindirmede yok (kucuk KiCad penceresinde canvas'tan buyuk tasmasin)."""
        self.canvas.setMinimumSize(*((320, 240) if on else (0, 0)))
        self.frame.setMinimumSize(*((560, 300) if on else (0, 0)))

    # ------------------------------------------------------------ harici pencere
    def go_external(self):
        """Viewport'u KiCad'den ayir: normal, boyutlandirilabilir pencere (canli senkron surer)."""
        if not (self.embedded and self.is_open and not self._external):
            return
        board = getattr(self.core, "board_name", "") or ""
        self._window_min_size(True)
        self.embedder.make_external(self.frame, f"IPCubed — {board}" if board else TITLE)
        self._external = True
        self.frame.activateWindow()
        self.core.request_draw()
        _log("harici pencere")

    def return_to_kicad(self):
        if not self._external:
            return
        self._external = False
        self._window_min_size(False)
        self.embedder.make_embedded(self.frame)
        if not self.embedder.place(self.frame):
            self._finish_hide()
        _log("KiCad'e donuldu")

    def _on_frame_closed(self):
        if self._external:                      # harici pencerenin kapatma dugmesi: KiCad'e don ve 3D'yi kapat
            self.return_to_kicad()
            self._finish_hide()
        elif not self.embedded:                 # bagimsiz pencere (Wayland/macOS): kapat = gizle; arac cubugu dugmesi yeniden acar
            self._finish_hide()
        else:
            self.hide3d()

    def rig_refresh(self):
        if self.core.vs.board_bounds:
            self.core.rig.frame(self.core.vs.board_bounds, self.core.vs.thickness, self.cfg)

    # ------------------------------------------------------------ gosterme
    @property
    def is_open(self) -> bool:
        return self._shown and not self._closing

    def toggle(self):
        if self._external:                       # KiCad'de 3: harici pencereyi one getir
            self.frame.raise_(); self.frame.activateWindow()
            return
        if self.is_open:
            self.hide3d()
        else:
            self.show3d()

    def show3d(self):
        if self.embedded and not self._editor_up:
            if not self._pending_show:
                import time
                self._pending_since = time.monotonic()
            self._pending_show = True       # editor belirince ac
            return
        self.core.start_sync()
        if not self.core.loaded:
            self._pending_show = True       # veri gelince ac
            return
        self._closing = False
        if not self._shown:
            if self.embedded:
                from pathlib import Path
                self.embedder.hint = Path(getattr(self.core, "board_name", "") or "").stem
                if not self.embedder.place(self.frame):
                    _log("place basarisiz")
                    return
                c = self.embedder.last.get("canvas")        # gercek canvas boyutuyla yeniden cercevele
                if c and c[3] > 0:
                    self.core.rig.set_aspect(c[2] / c[3])
                    self.rig_refresh()
            else:
                self.frame.show()
            self._shown = True
            _log("3D acildi")
        self.core.set_polling_fast(True)
        self.core.enter_3d(animate=True)

    def hide3d(self):
        if not self._shown or self._closing or self._external:
            return
        self._closing = True
        self.core.leave_3d()

    def _on_loaded(self):
        if self._pending_show or not self.embedded:
            self._pending_show = False
            self.show3d()

    # ------------------------------------------------------------ dongu
    _editor_up = False
    _seen_editor = False
    _gone_since = None
    _nokicad_since = None

    def _watch_editor(self):
        """Gomulu mod: PCB duzenleyici var mi? Belirince KiCad'e baglan (hazirda bekle), kaybolunca birak. 3 tusunu dinle."""
        import time
        now = time.monotonic()
        if self.embedder.hotkey_pressed():
            _log(f"hotkey 3 -> toggle (acik={self.is_open}, loaded={self.core.loaded}, editor={self._editor_up})")
            self.toggle()
        if now - getattr(self, "_watch_t", 0) < 0.5:
            return
        self._watch_t = now
        try:
            up = self.embedder.editor_present()
        except Exception:  # noqa: BLE001
            up = self._editor_up
        if not up and self._pending_show and not getattr(self, "_warned_no_editor", False) \
                and now - getattr(self, "_pending_since", now) > 10:
            self._warned_no_editor = True           # sessizce beklemek yerine nedenini soyle (bir kez)
            _log("3D istendi ama PCB duzenleyici penceresi bulunamadi")
            self._notice("IPCubed cannot find the PCB editor window to show the 3D view on.\n\n"
                         "If the Appearance panel (Layers / Objects / Nets) is hidden, show it again: "
                         "View > Panels > Appearance. Then press 3D Live again.\n\n"
                         "If the problem stays, please report it with the log file "
                         f"(set IPCUBED_DEBUG=1 before starting KiCad): {_debug_log_hint()}")
        if up:
            self._gone_since = None
            self._seen_editor = True
            if not self._editor_up:
                _log("PCB duzenleyici bulundu")
                self._editor_up = True
                self.core.start_sync()               # veriyi onceden yukle: ilk '3' aninda acilsin
                self.core.set_polling_fast(False)
                if self._pending_show:
                    self._pending_show = False
                    self.show3d()
        elif self._editor_up:
            self._gone_since = self._gone_since or now
            if now - self._gone_since > 5:
                self._editor_up = False
                if self._shown and not self._external:
                    self._finish_hide()
                self.core.stop_sync()                # KiCad yokken sifir polling
        if not up and not self._persist and not self._seen_editor and now - getattr(self, "_kicad_chk", 0) > 2:
            # editor hic gorulmedi (KiCad, viewer acilirken kapanmis olabilir): 30 sn hic KiCad sureci yoksa cik
            self._kicad_chk = now
            try:
                alive = kicad_running()
            except Exception:  # noqa: BLE001
                alive = True
            if alive:
                self._nokicad_since = None
            elif now - (self._nokicad_since or now) > 30:
                _log("KiCad yok (hic gorulmedi) -> cikis")
                self.quit()
            else:
                self._nokicad_since = self._nokicad_since or now
        if not up and not self._persist and self._seen_editor and now - (self._gone_since or now) > 5:
            # PCB duzenleyici kapandi: proje yoneticisi de yoksa (KiCad tamamen kapandi) daemon'u kapat.
            # Yalniz pcbnew kapanip KiCad acik kaldiysa beklemeye devam: yeniden acilinca '3' hemen calissin.
            if now - getattr(self, "_kicad_chk", 0) > 2:
                self._kicad_chk = now
                try:
                    alive = kicad_running()
                except Exception:  # noqa: BLE001
                    alive = True
                if not alive:
                    _log("KiCad kapandi -> cikis")
                    self.quit()

    def _watch_kicad(self):
        """Bagimsiz mod: editor penceresi izlenemez; KiCad sureci gorulduyse ve artik yoksa cik."""
        import time
        now = time.monotonic()
        if now - getattr(self, "_kicad_chk", 0) < 2:
            return
        self._kicad_chk = now
        try:
            alive = kicad_running()
        except Exception:  # noqa: BLE001
            return
        if alive:
            self._seen_editor = True
        elif self._seen_editor:
            _log("KiCad kapandi -> cikis")
            self.quit()

    def _tick(self):
        self.core.tick()
        busy = self._shown or self._closing or self.core.vs.pending() or self.core.rig.animating
        want = 8 if busy else 25                 # 3D kapaliyken seyrek uyan: bosta CPU ~1/3
        if want != self.timer.interval():
            self.timer.setInterval(want)
        if self.embedded:
            self._watch_editor()
        elif not self._persist:
            self._watch_kicad()
        if self.embedded and self._shown and not self._external:
            if not self.embedder.follow(self.frame):
                _log("follow: editor penceresi yok -> gizle")
                self._finish_hide()           # pcbnew kapandi/kayboldu
        if self._closing and not self.core.rig.animating:
            if self.embedded:
                self._finish_hide()
            else:
                self._closing = False         # bagimsiz modda pencere kalir (2D gorunumde)
                self._shown = True

    def _notice(self, text: str):
        """Engellemeyen bilgi kutusu (viewer dongusu durmasin), KiCad'in ustunde."""
        box = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Warning, TITLE, text, QtWidgets.QMessageBox.Ok)
        box.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        box.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        box.show()
        box.raise_()
        self._notice_box = box

    def quit(self):
        if self._external:
            self.return_to_kicad()
        if self._shown:
            self._finish_hide()
        self.timer.stop()
        QtWidgets.QApplication.quit()

    def _finish_hide(self):
        self._closing = False
        self._shown = False
        self.core.visible = False
        self.core.set_polling_fast(False)
        self.frame.hide()
        if self.embedder:
            self.embedder.release(self.frame)

    # ------------------------------------------------------------ kontrol sunucusu
    def _on_conn(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._on_cmd(s))
            sock.disconnected.connect(sock.deleteLater)

    def _on_cmd(self, sock):
        for line in bytes(sock.readAll()).decode("utf-8", "ignore").splitlines():
            cmd = line.strip().lower()
            _log(f"komut: {cmd}")
            try:
                self._run_cmd(cmd)
            except Exception:  # noqa: BLE001
                import traceback
                _log(traceback.format_exc())
            sock.write(b"ok\n")
        sock.flush()
        sock.disconnectFromHost()

    def _run_cmd(self, cmd: str):
        if True:
            if cmd == "toggle":
                self.toggle()
            elif cmd == "show":
                self.show3d()
            elif cmd == "hide":
                self.hide3d()
            elif cmd == "settings":
                self.toggle_settings()
            elif cmd == "external":
                self.go_external()
            elif cmd == "return":
                self.return_to_kicad()
            elif cmd == "quit":
                self.quit()


def run(args):
    import os
    os.environ.setdefault("QT_API", "pyside6")
    from .ctl import send
    if send("ping", timeout=0.5):          # zaten calisan bir viewer var: tek kopya
        if getattr(args, "show", False):
            send("show")
        return 0
    sys.setswitchinterval(0.002)          # arka plan thread'leri (model/ornekleyici) render thread'ini uzun sure bekletmesin
    app = QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName("ipcubed")
    from . import theme
    theme.apply_app_font(app)
    shell = ViewerShell(embed=not getattr(args, "standalone", False), show_now=getattr(args, "show", False),
                        persist=getattr(args, "persist", False))
    code = app.exec()
    try:
        if port_file().read_text().strip() == str(shell.server.serverPort()):
            port_file().unlink()
    except OSError:
        pass
    try:
        shell.core.close()
    finally:
        _kill_children()
    # Calisan model/mesh isleri ve ProcessPool yonetici thread'leri yorumlayici cikisini bekletmesin: dogrudan cik
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def _kill_children():
    """Senkron sureci ve isci havuzlari (spawn) geride kalmasin."""
    try:
        import psutil
        kids = psutil.Process().children(recursive=True)
        for k in kids:
            k.terminate()
        _, alive = psutil.wait_procs(kids, timeout=1.5)
        for k in alive:
            k.kill()
    except Exception:  # noqa: BLE001
        pass
