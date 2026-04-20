"""Win32 clipboard + ``Ctrl+V`` simulation. See handover §8b.

Why pywin32 over pyautogui/keyboard:
- ``OpenClipboard`` / ``SetClipboardData`` / ``CloseClipboard`` is atomic and race-free.
- ``SendInput`` reliably delivers ``Ctrl+V`` in Electron (VS Code) and UWP apps,
  where pyautogui sometimes fails.

Clipboard restore: snapshot current contents, set new text, send ``Ctrl+V``,
sleep ``restore_delay_ms``, restore original clipboard.
"""

from __future__ import annotations


def paste_to_active_window(
    text: str,
    *,
    restore_clipboard: bool = True,
    restore_delay_ms: int = 500,
) -> None:
    """Copy ``text`` to the clipboard and simulate ``Ctrl+V`` in the active window.

    Implement per handover §11 step 6.
    """
    raise NotImplementedError("Implement per handover §11 step 6.")
