import unittest
from unittest import mock

import hermes_trigger


def _visible_hermes(title="Hermes"):
    user32 = mock.Mock()
    user32.IsWindowVisible.return_value = True
    user32.GetWindowTextLengthW.return_value = len(title)

    def _text(hwnd, buf, n):
        buf.value = title
        return len(title)

    user32.GetWindowTextW.side_effect = _text

    def _enum(callback, lparam):
        callback(1234, 0)
        return 1

    user32.EnumWindows.side_effect = _enum
    return user32


class TestFindHermesWindow(unittest.TestCase):
    def test_finds_hermes_by_title(self):
        with mock.patch.object(hermes_trigger, "_exe_name", return_value="Hermes.exe"):
            self.assertEqual(
                hermes_trigger.find_hermes_window(_visible_hermes()), 1234)

    def test_rejects_other_app_with_hermes_in_title(self):
        with mock.patch.object(hermes_trigger, "_exe_name", return_value="chrome.exe"):
            self.assertIsNone(
                hermes_trigger.find_hermes_window(_visible_hermes("Hermes docs")))

    def test_none_found(self):
        user32 = mock.Mock()
        user32.EnumWindows.return_value = 1
        self.assertIsNone(hermes_trigger.find_hermes_window(user32))


class TestTrigger(unittest.TestCase):
    def test_not_open(self):
        user32 = mock.Mock()
        user32.EnumWindows.return_value = 1
        self.assertEqual(hermes_trigger.trigger(user32=user32),
                         hermes_trigger.NOT_OPEN)

    def test_ok_path(self):
        user32 = mock.Mock()
        user32.SetForegroundWindow.return_value = 1
        sent = []
        with mock.patch.object(hermes_trigger.time, "sleep"):
            result = hermes_trigger.trigger(
                user32=user32, found=777, sender=lambda: sent.append(1) or 4)
        self.assertEqual(result, hermes_trigger.OK)
        user32.ShowWindow.assert_called_once_with(777, hermes_trigger.SW_RESTORE)
        user32.SetForegroundWindow.assert_called_once_with(777)
        self.assertEqual(sent, [1])

    def test_send_failure(self):
        user32 = mock.Mock()
        user32.SetForegroundWindow.return_value = 1
        with mock.patch.object(hermes_trigger.time, "sleep"):
            result = hermes_trigger.trigger(
                user32=user32, found=777, sender=lambda: 0)
        self.assertEqual(result, hermes_trigger.SEND_FAILED)


class TestSentKey(unittest.TestCase):
    def test_sends_alt_space(self):
        user32 = mock.Mock()
        user32.SendInput.return_value = 4
        captured = {}

        def _send(n, array, size):
            captured["vks"] = [array[i].u.ki.wVk for i in range(n)]
            captured["flags"] = [array[i].u.ki.dwFlags for i in range(n)]
            return 4

        user32.SendInput.side_effect = _send
        self.assertEqual(hermes_trigger._send_hermes_key(user32), 4)
        self.assertEqual(captured["vks"], [0x12, 0x20, 0x20, 0x12])
        self.assertEqual(captured["flags"][-2:], [0x0002, 0x0002])


if __name__ == "__main__":
    unittest.main()
