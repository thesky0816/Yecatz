"""Exercise real Qt drag events without starting the desktop pet."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QWidget

import yecatz


class DragTestPet(yecatz.Pet):
    def __init__(self):
        QWidget.__init__(self)
        self.transfer = SimpleNamespace(state="idle", send_file=Mock())
        self.reading_mode = False
        self.tick = 0
        self.phase = ""
        self.phase_until = 0
        self.bubble = ""

    def say(self, text):
        self.bubble = text


class DropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.pet = DragTestPet()
        self.source = self.file_url("报告 final.pdf")
        self.mime = QMimeData()
        self.mime.setUrls([self.source])
        patcher = patch.object(yecatz, "QFile")
        self.qfile = patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def file_url(name):
        return QUrl.fromLocalFile(str(Path(tempfile.gettempdir()) / name))

    def event(self, event_type=QDropEvent, *, actions=Qt.DropAction.CopyAction, position=(60, 60)):
        point = QPointF(*position) if event_type is QDropEvent else QPoint(*position)
        return event_type(point, actions, self.mime, Qt.MouseButton.LeftButton,
                          Qt.KeyboardModifier.ShiftModifier)

    @staticmethod
    def recycled_file():
        file = Mock()
        file.moveToTrash.return_value = True
        file.fileName.return_value = str(Path(tempfile.gettempdir()) / "trash" / "recycled-file")
        return file

    @staticmethod
    def denied_file():
        file = Mock()
        file.moveToTrash.return_value = False
        file.errorString.return_value = "拒绝访问"
        return file

    def test_drop_passes_qt_path_and_accepts_copy(self):
        file = self.recycled_file()
        self.qfile.return_value = file
        event = self.event(actions=Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        self.assertEqual(event.proposedAction(), Qt.DropAction.MoveAction)

        self.pet.dropEvent(event)

        self.qfile.assert_called_once_with(self.source.toLocalFile())
        file.moveToTrash.assert_called_once_with()
        self.assertTrue(event.isAccepted())
        self.assertEqual(event.dropAction(), Qt.DropAction.CopyAction)
        self.assertEqual(self.pet.phase, "trash")
        self.assertIn("已移入回收站 1 个", self.pet.bubble)

    def test_move_only_drag_is_rejected_at_every_stage(self):
        for event_type, handler in ((QDragEnterEvent, self.pet.dragEnterEvent),
                                    (QDragMoveEvent, self.pet.dragMoveEvent),
                                    (QDropEvent, self.pet.dropEvent)):
            with self.subTest(event=event_type.__name__):
                event = self.event(event_type, actions=Qt.DropAction.MoveAction)
                handler(event)
                self.assertFalse(event.isAccepted())
        self.qfile.assert_not_called()

    def test_partial_failure_reports_successes_and_failure_details(self):
        self.mime.setUrls([self.source, self.file_url("locked.txt"), self.file_url("third.txt")])
        self.qfile.side_effect = [self.recycled_file(), self.denied_file(), self.recycled_file()]
        event = self.event()

        self.pet.dropEvent(event)

        self.assertEqual(self.qfile.call_count, 3)
        self.assertTrue(event.isAccepted())
        self.assertEqual(event.dropAction(), Qt.DropAction.CopyAction)
        self.assertEqual(self.pet.phase, "trash")
        self.assertIn("已移入回收站 2 个", self.pet.bubble)
        self.assertIn("失败 1 个", self.pet.bubble)
        self.assertIn("locked.txt", self.pet.bubble)
        self.assertIn("拒绝访问", self.pet.bubble)

    def test_all_failures_leave_drop_ignored_and_report_reason(self):
        self.qfile.return_value = self.denied_file()
        event = self.event()

        self.pet.dropEvent(event)

        self.assertFalse(event.isAccepted())
        self.assertEqual(self.pet.phase, "")
        self.assertIn("报告 final.pdf", self.pet.bubble)
        self.assertIn("拒绝访问", self.pet.bubble)

    def test_missing_trash_destination_is_not_success(self):
        file = self.recycled_file()
        file.fileName.return_value = ""
        self.qfile.return_value = file
        event = self.event()

        self.pet.dropEvent(event)

        self.assertFalse(event.isAccepted())
        self.assertEqual(self.pet.phase, "")
        self.assertIn("报告 final.pdf", self.pet.bubble)

    def test_malformed_and_mixed_file_urls_are_rejected(self):
        nul_url = QUrl.fromEncoded(bytes(self.source.toEncoded()) + b"%00")
        for urls in ([QUrl("file:")], [QUrl("file:relative.txt")], [nul_url],
                     [self.source, QUrl("https://example.invalid/report.txt")]):
            with self.subTest(urls=urls):
                self.mime.setUrls(urls)
                event = self.event()
                self.pet.dropEvent(event)
                self.assertFalse(event.isAccepted())
        self.qfile.assert_not_called()

    def test_reading_drop_routes_to_summary(self):
        self.pet.reading_mode = True
        event = self.event()
        with patch.object(self.pet, "summarize_file") as summarize:
            self.pet.dropEvent(event)

        self.assertTrue(event.isAccepted())
        summarize.assert_called_once_with(self.source.toLocalFile())
        self.qfile.assert_not_called()

    def test_connected_transfer_only_accepts_drop_in_box(self):
        self.pet.transfer.state = "connected"
        enter = self.event(QDragEnterEvent)
        outside_box = self.event()
        inside_box = self.event(position=(105, 185))

        self.pet.dragEnterEvent(enter)
        self.pet.dropEvent(outside_box)
        self.pet.dropEvent(inside_box)

        self.assertTrue(enter.isAccepted())
        self.assertFalse(outside_box.isAccepted())
        self.assertTrue(inside_box.isAccepted())
        self.pet.transfer.send_file.assert_called_once_with(self.source.toLocalFile())
        self.qfile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
