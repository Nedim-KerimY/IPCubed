"""SpaceMouse HID motion, independent of Qt/GPU so parsing can be tested offline.

Windows uses Raw Input (generic desktop / multi-axis controller), not exclusive
HID access or injected keyboard events. No extra driver DLL is loaded. The
viewer applies input only while its viewport is visible and has focus.
"""
from __future__ import annotations

import math
import struct
import sys
import time


def hid_reports(payload: bytes):
    """Split a RAWHID payload (size, count, reports), rejecting truncated input."""
    if len(payload) < 8:
        return ()
    size, count = struct.unpack_from("<II", payload)
    if not size or not count or size * count > len(payload) - 8:
        return ()
    return tuple(payload[8 + i * size:8 + (i + 1) * size] for i in range(count))


class MotionState:
    TIMEOUT = .15

    def __init__(self):
        self.reset()

    def reset(self):
        self.axes = [0] * 6
        self.updated = [float("-inf"), float("-inf")]
        self.last_motion = float("-inf")

    def feed(self, report: bytes, now: float):
        # Enterprise and recent wired/wireless devices: either two 3-axis
        # reports (1/2), or one 6-axis report (1). Ignore button/keyboard data.
        if len(report) < 7 or report[0] not in (1, 2):
            return False
        if report[0] == 1:
            self.axes[:3] = struct.unpack_from("<3h", report, 1)
            self.updated[0] = now
            if len(report) >= 13:
                self.axes[3:] = struct.unpack_from("<3h", report, 7)
                self.updated[1] = now
        else:
            self.axes[3:] = struct.unpack_from("<3h", report, 1)
            self.updated[1] = now
        values = struct.unpack_from("<6h" if report[0] == 1 and len(report) >= 13 else "<3h", report, 1)
        if any(abs(value) > 14 for value in values):  # Match the default motion deadzone.
            self.last_motion = now
        return True

    def motion_recent(self, now):
        # Include the release tail: 3DxWare's emulated wheel can arrive just
        # after a zero HID report. Do not swallow wheel input after disconnect.
        return 0 <= now - self.last_motion <= self.TIMEOUT

    def sample(self, now: float, deadzone: float = .04):
        deadzone = max(0.0, min(.5, deadzone))
        result = []
        for i, raw in enumerate(self.axes):
            age = now - self.updated[i // 3]
            v = max(-1.0, min(1.0, raw / 350.0)) if 0 <= age <= self.TIMEOUT else 0.0
            value = max(0.0, (abs(v) - deadzone) / (1.0 - deadzone))
            result.append(math.copysign(value, v))
        return tuple(result)


class WindowsSpaceMouse:
    """One native event filter owned by the viewer shell; GUI-thread only."""
    def __init__(self, window, active, motion, config):
        import ctypes as ct
        from PySide6 import QtCore

        self.ct, self.window, self.active, self.motion, self.config = ct, window, active, motion, config
        self.state = MotionState()
        self.device = None
        self.known = {}
        self.hwnd = None
        self.closed = False
        self.last_tick = time.monotonic()
        # Fixed-width Win32 integers; pointers follow the interpreter's bitness.
        class Device(ct.Structure):
            _fields_ = [("page", ct.c_uint16), ("usage", ct.c_uint16), ("flags", ct.c_uint32), ("hwnd", ct.c_void_p)]
        class Header(ct.Structure):
            _fields_ = [("kind", ct.c_uint32), ("size", ct.c_uint32), ("device", ct.c_void_p), ("wparam", ct.c_size_t)]
        class Point(ct.Structure):
            _fields_ = [("x", ct.c_int32), ("y", ct.c_int32)]
        class Message(ct.Structure):
            _fields_ = [("hwnd", ct.c_void_p), ("message", ct.c_uint32), ("wparam", ct.c_size_t),
                        ("lparam", ct.c_ssize_t), ("time", ct.c_uint32), ("pt", Point), ("private", ct.c_uint32)]
        self.Device, self.Header, self.Message = Device, Header, Message
        self.user = ct.WinDLL("user32", use_last_error=True)
        self.user.RegisterRawInputDevices.argtypes = [ct.POINTER(Device), ct.c_uint32, ct.c_uint32]
        self.user.RegisterRawInputDevices.restype = ct.c_int
        self.user.GetRawInputData.argtypes = [ct.c_void_p, ct.c_uint32, ct.c_void_p, ct.POINTER(ct.c_uint32), ct.c_uint32]
        self.user.GetRawInputData.restype = ct.c_uint32
        self.user.GetRawInputDeviceInfoW.argtypes = [ct.c_void_p, ct.c_uint32, ct.c_void_p, ct.POINTER(ct.c_uint32)]
        self.user.GetRawInputDeviceInfoW.restype = ct.c_uint32

        owner = self
        class Filter(QtCore.QAbstractNativeEventFilter):
            def nativeEventFilter(self, event_type, message):
                if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                    try:
                        owner.on_message(int(message))
                    except Exception as error:
                        owner.state.reset()
                        if not getattr(owner, "reported_error", False):
                            print(f"SpaceMouse input error: {error}", flush=True)
                            owner.reported_error = True
                # Let Qt/DefWindowProc perform WM_INPUT cleanup.
                return False, 0
        self.filter = Filter()
        self.app = QtCore.QCoreApplication.instance()
        self.retarget()
        self.app.installNativeEventFilter(self.filter)

    def retarget(self):
        hwnd = int(self.window.winId())
        if hwnd != self.hwnd:
            # INPUTSINK handles the embedded viewport whose top-level owner is
            # KiCad. active() gates delivery; DEVNOTIFY clears unplugged devices.
            d = self.Device(1, 8, 0x100 | 0x2000, hwnd)
            if not self.user.RegisterRawInputDevices(self.ct.byref(d), 1, self.ct.sizeof(d)):
                raise self.ct.WinError(self.ct.get_last_error())
            self.hwnd = hwnd
            self.state.reset()

    def supported(self, handle):
        if handle not in self.known:
            ct = self.ct
            size = ct.c_uint32()
            command = 0x20000007  # RIDI_DEVICENAME, not a device open.
            self.user.GetRawInputDeviceInfoW(handle, command, None, ct.byref(size))
            if not 0 < size.value < 4096:
                return False
            name = ct.create_unicode_buffer(size.value + 1)
            rc = self.user.GetRawInputDeviceInfoW(handle, command, name, ct.byref(size))
            value = name.value.upper() if rc != 0xFFFFFFFF else ""
            if len(self.known) >= 64:
                self.known.clear()
            self.known[handle] = "VID_256F&" in value or "VID_046D&" in value
        return self.known[handle]

    def on_message(self, address):
        if self.closed:
            return
        ct = self.ct
        msg = self.Message.from_address(address)
        if msg.hwnd != self.hwnd:
            return
        if msg.message == 0xFE:  # WM_INPUT_DEVICE_CHANGE
            self.known.pop(msg.lparam, None)
            if msg.lparam == self.device:
                self.state.reset()
            return
        if msg.message != 0xFF:  # WM_INPUT
            return
        if not self.config.spacemouse_enabled or not self.active():
            self.state.reset()
            return
        size, header_size = ct.c_uint32(), ct.sizeof(self.Header)
        if self.user.GetRawInputData(msg.lparam, 0x10000003, None, ct.byref(size), header_size) == 0xFFFFFFFF:
            return
        if not header_size + 8 <= size.value <= 65536:
            return
        buffer = ct.create_string_buffer(size.value)
        read = self.user.GetRawInputData(msg.lparam, 0x10000003, buffer, ct.byref(size), header_size)
        if read == 0xFFFFFFFF or read < header_size + 8 or read > len(buffer):
            return
        header = self.Header.from_buffer_copy(buffer)
        if header.kind != 2 or not self.supported(header.device):
            return
        if self.device != header.device:
            self.device = header.device
            self.state.reset()
        for report in hid_reports(buffer.raw[header_size:read]):
            self.state.feed(report, time.monotonic())

    def tick(self):
        if self.closed:
            return
        now = time.monotonic()
        dt, self.last_tick = min(.05, max(0.0, now - self.last_tick)), now
        if not self.config.spacemouse_enabled or not self.active():
            self.state.reset()
            return
        try:
            self.retarget()  # Qt can replace the HWND when detaching the view.
        except OSError as error:
            print(f"SpaceMouse disabled: {error}", flush=True)
            self.close()
            return
        axes = self.state.sample(now)
        if self.config.spacemouse_reverse:
            axes = tuple(-x for x in axes)
        if not self.config.spacemouse_roll:
            axes = (*axes[:4], 0.0, axes[5])
        if any(axes):
            self.motion(axes, dt, self.config.spacemouse_move_speed / 100.0,
                        self.config.spacemouse_turn_speed / 100.0)

    def blocks_wheel(self):
        """Avoid double zoom from 3DxWare's concurrent wheel-emulation fallback.

        Wheel events have no reliable HID device identity at the renderer. Give
        six-axis motion precedence during its gesture and short release tail.
        Ordinary wheel zoom remains available when the cap is at rest.
        """
        return (not self.closed and self.config.spacemouse_enabled and self.active()
                and self.state.motion_recent(time.monotonic()))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.state.reset()
        self.app.removeNativeEventFilter(self.filter)
        d = self.Device(1, 8, 1, None)  # RIDEV_REMOVE requires a NULL target.
        self.user.RegisterRawInputDevices(self.ct.byref(d), 1, self.ct.sizeof(d))


def start(window, active, motion, config):
    if sys.platform != "win32":
        return None
    try:
        return WindowsSpaceMouse(window, active, motion, config)
    except Exception as error:
        print(f"SpaceMouse unavailable: {error}", flush=True)
        return None
