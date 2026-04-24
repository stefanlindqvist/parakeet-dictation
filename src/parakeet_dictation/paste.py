"""Win32 clipboard + ``Ctrl+V`` simulation. See handover §8b.

Why pywin32 over pyautogui/keyboard:
- ``OpenClipboard`` / ``SetClipboardData`` / ``CloseClipboard`` is atomic and race-free.
- ``SendInput`` reliably delivers ``Ctrl+V`` in Electron (VS Code) and UWP apps,
  where pyautogui sometimes fails.

Clipboard restore: snapshot current contents, set new text, send ``Ctrl+V``,
then schedule a background restore after ``restore_delay_ms`` so the caller
returns immediately. Consecutive pastes cancel any still-pending restore to
avoid clobbering the clipboard with a stale value.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes

log = logging.getLogger(__name__)

_restore_lock = threading.Lock()
_restore_cancel: threading.Event | None = None

# Virtual-key codes (Windows SDK: WinUser.h)
_VK_CONTROL = 0x11
_VK_V = 0x56

# SendInput flags
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002

# Clipboard formats
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    )


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    )


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUT_UNION(ctypes.Union):
    _fields_ = (
        ("ki", _KEYBDINPUT),
        ("mi", _MOUSEINPUT),
        ("hi", _HARDWAREINPUT),
    )


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = (
        ("type", wintypes.DWORD),
        ("u", _INPUT_UNION),
    )


def _key_event(vk: int, key_up: bool) -> _INPUT:
    flags = _KEYEVENTF_KEYUP if key_up else 0
    return _INPUT(
        type=_INPUT_KEYBOARD,
        u=_INPUT_UNION(ki=_KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None)),
    )


def _send_ctrl_v() -> None:
    user32 = ctypes.windll.user32
    events = (_INPUT * 4)(
        _key_event(_VK_CONTROL, key_up=False),
        _key_event(_VK_V, key_up=False),
        _key_event(_VK_V, key_up=True),
        _key_event(_VK_CONTROL, key_up=True),
    )
    sent = user32.SendInput(len(events), ctypes.byref(events), ctypes.sizeof(_INPUT))
    if sent != len(events):
        err = ctypes.get_last_error()
        raise OSError(f"SendInput sent {sent}/{len(events)} events (last error={err})")


def _snapshot_unicode_clipboard() -> str | None:
    """Return current clipboard text or ``None`` if empty / non-text."""
    import win32clipboard  # type: ignore[import-not-found]

    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(_CF_UNICODETEXT):
            data = win32clipboard.GetClipboardData(_CF_UNICODETEXT)
            return str(data) if data is not None else None
        return None
    finally:
        win32clipboard.CloseClipboard()


def _set_unicode_clipboard(text: str) -> None:
    import win32clipboard  # type: ignore[import-not-found]

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(_CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def _schedule_restore(previous: str, delay_ms: int) -> None:
    """Restore ``previous`` to the clipboard after ``delay_ms`` on a background
    thread. Cancels any still-pending restore from an earlier paste so that
    back-to-back dictations don't resurrect a stale clipboard value."""
    global _restore_cancel

    cancel = threading.Event()
    with _restore_lock:
        if _restore_cancel is not None:
            _restore_cancel.set()
        _restore_cancel = cancel

    def _run() -> None:
        global _restore_cancel
        if cancel.wait(delay_ms / 1000.0):
            return
        try:
            _set_unicode_clipboard(previous)
        except Exception as exc:
            log.warning("Clipboard restore failed: %s", exc)
        with _restore_lock:
            if _restore_cancel is cancel:
                _restore_cancel = None

    threading.Thread(target=_run, daemon=True).start()


def paste_to_active_window(
    text: str,
    *,
    restore_clipboard: bool = True,
    restore_delay_ms: int = 150,
) -> None:
    """Copy ``text`` to the clipboard and simulate ``Ctrl+V`` in the active window.

    Returns as soon as ``Ctrl+V`` has been dispatched; the clipboard restore
    (if requested) runs asynchronously after ``restore_delay_ms``.
    """
    if not text:
        return

    previous: str | None = None
    if restore_clipboard:
        try:
            previous = _snapshot_unicode_clipboard()
        except Exception as exc:
            log.warning("Clipboard snapshot failed: %s", exc)
            previous = None

    _set_unicode_clipboard(text)
    _send_ctrl_v()

    if restore_clipboard and previous is not None:
        _schedule_restore(previous, restore_delay_ms)
