"""回归测试：Windows 上从资源管理器拖入的路径必须规范化后才能交给 send2trash。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="yecatz-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import yecatz  # noqa: E402

app = QApplication.instance() or QApplication([])


def make_mime(path):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])
    return mime


def make_event(mime):
    return QDropEvent(QPointF(60, 60), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


class DropTests(unittest.TestCase):
    def setUp(self):
        with patch.object(yecatz, "get_json", side_effect=OSError("offline")):
            self.pet = yecatz.Pet()
        self.pet.entering = False
        self.pet.anim.stop()

    def tearDown(self):
        self.pet.transfer.disconnect()
        self.pet.tray.hide()
        self.pet.close()
        app.processEvents()

    def test_drop_normalizes_windows_paths(self):
        raw = r"D:\桌面 文件夹\报告 final.pdf"
        mime = make_mime(raw)          # 保持引用，否则 QMimeData 会被回收
        if os.name == "nt":
            # 这正是 bug 的来源：Qt 给出的是正斜杠路径
            self.assertIn("/", mime.urls()[0].toLocalFile())

        with patch.object(yecatz, "send2trash") as trash:
            self.pet.dropEvent(make_event(mime))

        trash.assert_called_once()
        passed = trash.call_args[0][0]
        self.assertEqual(passed, os.path.normpath(raw))
        self.assertNotIn("/", passed)
        self.assertIn("已移入回收站 1 个", self.pet.bubble)

    def test_drop_reports_failure_reason(self):
        mime = make_mime(r"D:\桌面 文件夹\报告 final.pdf")
        with patch.object(yecatz, "send2trash", side_effect=OSError("拒绝访问")):
            self.pet.dropEvent(make_event(mime))

        self.assertIn("没能移入回收站", self.pet.bubble)
        self.assertIn("报告 final.pdf", self.pet.bubble)


if __name__ == "__main__":
    unittest.main()
