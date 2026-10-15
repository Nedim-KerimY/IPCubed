"""KiCad polling (SyncThread). pygfx/Qt iceri aktarmaz: ayri senkron surecinde hafif calisir."""
from __future__ import annotations

import queue
import threading
import time

from .kicad_source import KiCadSource
from .log import _log


class SyncThread(threading.Thread):
    """KiCad'i polling ile izler, degisenleri kuyruga atar. Render thread'i asla beklemez.

    Mesajlar: ("full", snap) tam yukleme; ("moved", [FootprintData]) tasinan footprint (anlik, yalniz model matrisleri);
    ("geom", snap) bakir/silk/kontur yeniden cekildi (iz, via, zone, pad, sekil, yazi degisti); ("status", metin).
    """

    GEOM_EVERY = 1.5          # sn: 3D acikken geometri degisim kontrolu araligi

    def __init__(self, out: queue.Queue, interval: float = 0.12):
        super().__init__(daemon=True, name="kicad-sync")
        self.out = out
        self.interval = interval
        self.paused_interval = 2.5            # gorunmezken yavas poll (3D acilirken check_now ile aninda uyanir)
        self.visible = True
        self._halt = threading.Event()
        self.request_full = threading.Event()
        self.request_full.set()                # ilk calismada tam snapshot
        self.check_now = threading.Event()     # geometri degisimini hemen kontrol et (3D acilirken)

    def run(self):
        from kipy.errors import ApiError

        src = None
        last: dict[str, int] | None = None   # kiyas durumu: baglanti kopsa da KORUNUR
        last_raw = None                      # pad ham hash'i: degismediyse python'da pad cozumleme yapilmaz (bosta CPU ~0)
        prev_snap = None
        geom_ref = None
        last_chk = 0.0
        last_hot = 0.0
        fresh_fp = False                      # sonraki geometri kontrolu footprint'leri de hemen cekmeli mi
        backoff = 0.0                         # son yenilemenin suresine gore kontrol araligi uzar (yavas/buyuk kartlarda firtina olmasin)
        full_inflight = False
        while not self._halt.is_set():
            try:
                if src is None:
                    src = KiCadSource()
                raw = src.pads_raw_hash()
                if self._was_busy:                   # KiCad'de etkilesimli arac (rota cizme, surukleme, diyalog) az once bitti:
                    self._was_busy = False           # degisiklik buyuk olasilikla simdi isledi -> 1.5 sn beklemeden kontrol et
                    _log("duzenleme bitti -> hemen kontrol (footprint dahil)")
                    fresh_fp = True                  # footprint ici yazi/alan da degismis olabilir: seyrek footprint kontrolunu bekleme
                    self.check_now.set()
                if last is None or raw != last_raw or self.request_full.is_set():
                    sig = src.pad_signature()
                    if last is None:
                        last = sig
                    if set(sig) != set(last) or self.request_full.is_set():
                        self.request_full.clear()
                        full_inflight = True             # hata olursa (dosya kilidi, baglanti...) tam yukleme yeniden denenir
                        gs = src.geom_signature()
                        self.out.put(("fetching", True))
                        prev_snap = src.snapshot()
                        geom_ref = gs
                        self.out.put(("full", self._ship(prev_snap)))
                        full_inflight = False
                    elif sig != last:
                        changed = [k for k in sig if sig[k] != last.get(k)]
                        _log(f"moved: {len(changed)} footprint")
                        self.out.put(("moved", src.footprints_by_id(changed)))
                        # duzenleme = tasima: tasinan footprint'lerin silk'i zaten tek tek alindi (ve 5 sn tek tek yeniden kontrol
                        # edilir); tum footprint'leri cekmek (~0.8 sn, KiCad kilitlenir) gereksiz
                        fresh_fp = False
                        self.check_now.set()             # tasima sonrasi bakir/maske/silk yenilemesi hemen baslasin (bekleme/backoff yok)
                    last = sig
                    last_raw = raw
                now = time.monotonic()
                if prev_snap is not None and self.visible and now - last_hot > 0.5:
                    last_hot = now
                    if src.recheck_hot():                # tasinan footprint KiCad'den gec/bayat geldiyse silk duzeltilir
                        self.check_now.set()
                if prev_snap is not None and self.visible and (self.check_now.is_set() or now - last_chk > max(self.GEOM_EVERY, backoff)):
                    self.check_now.clear()
                    last_chk = now
                    gs = src.geom_signature(fresh_fp)
                    fresh_fp = False
                    if geom_ref is not None and (gs != geom_ref or src.silk_pending()):
                        t0 = time.perf_counter()
                        diff = [i for i in range(len(gs)) if gs[i] != geom_ref[i]]
                        self.out.put(("fetching", True))         # viewer: "Reading changes from KiCad"
                        # yalniz degisen kategori cekilir, yalniz etkilenen katmanlar yeniden uretilir
                        prev_snap, plan = src.refresh_partial(prev_snap, diff)
                        if plan.get("refull"):                 # stackup kalinligi degisti: modeller dahil tam yukleme
                            self.request_full.set()
                            geom_ref = gs
                            continue
                        # degisen katmanlarin iz/zone verisi plana eklenir: o isler buyuk veri dosyasini okumadan baslar
                        cdn = prev_snap.copper
                        plan["track_data"] = {L: cdn.tracks.get(L) for L in plan["tracks"]}
                        plan["zone_data"] = {L: cdn.zones.get(L, []) for L in plan.get("zones", ())}
                        backoff = 2 * (time.perf_counter() - t0)
                        _log(f"degisti {diff} -> plan cu={sorted(plan['cu'])} iz={sorted(plan['tracks'])} zone={sorted(plan.get('zones', ()))} govde={plan['body']}/{sorted(plan.get('body_tiles', ()))} via={plan.get('vias')} "
                             f"silk={plan['silk']} pad={plan['pads']} tam={plan['full']}; cekildi {time.perf_counter() - t0:.2f}s")
                        self.out.put(("partial", (self._ship(prev_snap), plan)))
                        geom_ref = gs
                    elif geom_ref is None:
                        geom_ref = gs
            except ApiError as e:
                # KiCad bir arac (surukleme vb.) calisirken "busy" der: baglanti saglam, kisa sure sonra tekrar dene
                if "busy" in str(e).lower():
                    self._was_busy = True
                    time.sleep(0.04)
                    continue
                _log(f"api hatasi: {e}")
                if full_inflight:
                    self.request_full.set()
                    full_inflight = False
                time.sleep(0.5)
                continue
            except Exception as e:  # noqa: BLE001  KiCad kapandi / yeniden aciliyor
                _log(f"baglanti hatasi: {type(e).__name__}: {e}")
                if full_inflight:                    # yarim kalan tam yukleme kaybolmasin: viewer hic "yuklendi" olmazdi
                    self.request_full.set()
                    full_inflight = False
                self.out.put(("status", f"KiCad connection lost: {type(e).__name__}"))
                src = None
                time.sleep(1.0)
                continue
            if prev_snap is None or not self.visible:
                self.check_now.clear()          # henuz is yok: bos donguye girmesin
            self.check_now.wait(self.interval if self.visible else self.paused_interval)

    _was_busy = False
    ship_files = False            # ayri surecte True: buyuk veri dosyaya, kuyruga hafif kopya
    _n = 0

    def _ship(self, snap):
        """Bakir (iz/zone dahil) + silk verisini dosyaya yaz; render surecine yalniz hafif kopya (pad/via, footprint, stackup) gonder."""
        if not self.ship_files or snap.copper is None:
            return snap
        import dataclasses
        import os
        import pickle
        from .paths import cache_dir
        d = cache_dir().parent / "snap"
        d.mkdir(parents=True, exist_ok=True)
        self._n += 1
        path = d / f"{os.getpid()}_{self._n}.pkl"
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            pickle.dump({"copper": snap.copper, "silk": snap.silk}, f, protocol=5)
        for i in range(6):                            # Windows: antivirus/indeksleyici yeni dosyayi kisa sure kilitleyebilir
            try:
                tmp.replace(path)
                break
            except PermissionError:
                if i == 5:
                    raise
                time.sleep(0.1 * (i + 1))
        olds = sorted(d.glob(f"{os.getpid()}_*.pkl"), key=lambda p: int(p.stem.split("_")[1]))
        for p in olds[:-4]:                           # son birkac goruntu (isler hala okuyor olabilir) kalir
            try:
                p.unlink()
            except OSError:
                pass
        lite = dataclasses.replace(snap.copper, tracks={}, zones={})
        return dataclasses.replace(snap, copper=lite, silk=None, data_path=str(path))

    def stop(self):
        self._halt.set()
