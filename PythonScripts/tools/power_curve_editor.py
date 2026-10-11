from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone power curve editor")
    parser.add_argument(
        "--curve-file",
        default="data/power_curve/active_curve.json",
        help="Curve JSON file path. Relative paths are resolved from the ZBin directory.",
    )
    parser.add_argument(
        "--readonly",
        action="store_true",
        help="Open the editor in read-only mode.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Periodically reload when the curve file changes on disk.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    python_scripts_dir = Path(__file__).resolve().parents[1]
    zbin_dir = python_scripts_dir.parent
    if str(python_scripts_dir) not in sys.path:
        sys.path.insert(0, str(python_scripts_dir))
    try:
        from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
        from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QPen, QShortcut
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QDoubleSpinBox,
            QFormLayout,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QSplitter,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
            QFileDialog,
        )
    except ImportError:
        print("PySide6 is required for the editor. Install dependencies first, then rerun this command.")
        return 1

    from PowerCurveBackend import (
        CURVE_NAMES,
        MonotoneCubicCurve,
        PROFILE_DISPLAY_NAMES,
        PROFILE_KEYS,
        PowerCurveStore,
        _validate_payload,
        atomic_write_curve_file,
        clamp_with_limits,
        default_curve_payload,
        default_curve_template_file,
        ensure_curve_file_exists,
    )

    class CurveCanvas(QWidget):
        pointMoved = Signal()
        pointAdded = Signal()
        pointDeleted = Signal()

        def __init__(self, host: "PowerCurveEditorWindow"):
            super().__init__()
            self.host = host
            self.setMinimumSize(720, 420)
            self.setMouseTracking(True)
            self._drag_curve: str | None = None
            self._drag_index: int | None = None
            self._hover_curve: str | None = None
            self._hover_index: int | None = None
            self._drag_snapshot_taken = False

        def _plot_rect(self) -> QRectF:
            return QRectF(55, 20, max(120.0, self.width() - 90.0), max(120.0, self.height() - 55.0))

        def _max_position(self) -> float:
            values = [
                point["position_mm"]
                for curve in self.host._active_curves().values()
                for point in curve["points"]
            ]
            return max(1000.0, max(values, default=1000.0) * 1.05)

        def _max_power(self) -> float:
            values = [
                point["power"]
                for curve in self.host._active_curves().values()
                for point in curve["points"]
            ]
            active_limits = self.host._active_limits()
            values.extend([active_limits["min_power"], active_limits["max_power"]])
            return max(1000.0, max(values, default=1000.0) * 1.10)

        def _to_canvas(self, position_mm: float, power: float) -> QPointF:
            rect = self._plot_rect()
            max_position = self._max_position()
            max_power = self._max_power()
            x = rect.left() + (position_mm / max_position) * rect.width()
            y = rect.bottom() - (power / max_power) * rect.height()
            return QPointF(x, y)

        def _from_canvas(self, point: QPointF) -> tuple[float, float]:
            rect = self._plot_rect()
            max_position = self._max_position()
            max_power = self._max_power()
            clamped_x = min(max(point.x(), rect.left()), rect.right())
            clamped_y = min(max(point.y(), rect.top()), rect.bottom())
            position = ((clamped_x - rect.left()) / rect.width()) * max_position
            power = ((rect.bottom() - clamped_y) / rect.height()) * max_power
            return position, power

        def _find_point(self, pos: QPointF) -> tuple[str | None, int | None]:
            best_curve = None
            best_index = None
            best_distance = 14.0
            for curve_name, visible in self.host.visible_curves.items():
                if not visible:
                    continue
                for index, point in enumerate(self.host._active_curves()[curve_name]["points"]):
                    canvas_point = self._to_canvas(point["position_mm"], point["power"])
                    distance = (canvas_point - pos).manhattanLength()
                    if distance < best_distance:
                        best_distance = distance
                        best_curve = curve_name
                        best_index = index
            return best_curve, best_index

        def paintEvent(self, _event) -> None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.fillRect(self.rect(), QColor("#111111"))

            rect = self._plot_rect()
            painter.fillRect(rect, QColor("#1c1c1c"))
            painter.setPen(QPen(QColor("#4f4f4f"), 1))
            painter.drawRect(rect)

            max_position = self._max_position()
            max_power = self._max_power()

            for i in range(6):
                tx = rect.left() + rect.width() * i / 5.0
                ty = rect.bottom() - rect.height() * i / 5.0
                painter.setPen(QPen(QColor("#303030"), 1))
                painter.drawLine(QPointF(tx, rect.top()), QPointF(tx, rect.bottom()))
                painter.drawLine(QPointF(rect.left(), ty), QPointF(rect.right(), ty))
                painter.setPen(QColor("#d0d0d0"))
                painter.drawText(tx - 16, rect.bottom() + 18, f"{max_position * i / 5.0:.0f}")
                if i < 5:
                    painter.drawText(8, ty + 5, f"{max_power * i / 5.0:.0f}")

            painter.drawText(rect.left(), 14, "Power")
            painter.drawText(rect.right() - 92, self.height() - 8, "Position(mm)")

            active_limits = self.host._active_limits()
            min_line = self._to_canvas(0.0, active_limits["min_power"]).y()
            max_line = self._to_canvas(0.0, active_limits["max_power"]).y()
            painter.setPen(QPen(QColor("#f4d35e"), 1, Qt.DashLine))
            painter.drawLine(QPointF(rect.left(), min_line), QPointF(rect.right(), min_line))
            painter.drawText(rect.right() - 170, min_line - 4, f"Min Clamp {active_limits['min_power']:.0f}")
            painter.setPen(QPen(QColor("#ee964b"), 1, Qt.DashLine))
            painter.drawLine(QPointF(rect.left(), max_line), QPointF(rect.right(), max_line))
            painter.drawText(rect.right() - 170, max_line - 4, f"Max Clamp {active_limits['max_power']:.0f}")

            for curve_name in CURVE_NAMES:
                if not self.host.visible_curves[curve_name]:
                    continue
                color = QColor(self.host._active_curves()[curve_name]["color"])
                points = self.host._active_curves()[curve_name]["points"]
                if len(points) < 2:
                    continue
                painter.setPen(QPen(color, 2.5))
                sampled_points = self.host.sample_curve_points(curve_name, samples_per_segment=24)
                for index in range(len(sampled_points) - 1):
                    p1 = self._to_canvas(sampled_points[index][0], sampled_points[index][1])
                    p2 = self._to_canvas(sampled_points[index + 1][0], sampled_points[index + 1][1])
                    painter.drawLine(p1, p2)

                if self.host.show_control_polyline_checkbox.isChecked():
                    painter.setPen(QPen(color.lighter(130), 1, Qt.DashLine))
                    for index in range(len(points) - 1):
                        p1 = self._to_canvas(points[index]["position_mm"], points[index]["power"])
                        p2 = self._to_canvas(points[index + 1]["position_mm"], points[index + 1]["power"])
                        painter.drawLine(p1, p2)

                for index, point in enumerate(points):
                    canvas_point = self._to_canvas(point["position_mm"], point["power"])
                    if curve_name == self._hover_curve and index == self._hover_index:
                        painter.setBrush(QColor("#ffffff"))
                    else:
                        painter.setBrush(color)
                    painter.setPen(QPen(QColor("#000000"), 1))
                    painter.drawEllipse(canvas_point, 5.5, 5.5)

            preview_position = self.host.preview_position.value()
            for curve_name in CURVE_NAMES:
                if not self.host.visible_curves[curve_name]:
                    continue
                power = self.host.preview_value(curve_name, preview_position)
                preview_point = self._to_canvas(preview_position, power)
                painter.setPen(QPen(QColor(self.host._active_curves()[curve_name]["color"]), 1, Qt.DashLine))
                painter.drawLine(QPointF(preview_point.x(), rect.bottom()), preview_point)
                painter.drawLine(QPointF(rect.left(), preview_point.y()), preview_point)

        def mouseMoveEvent(self, event) -> None:
            if self._drag_curve is not None and self._drag_index is not None and not self.host.readonly:
                curve_name = self._drag_curve
                index = self._drag_index
                if not self._drag_snapshot_taken:
                    self.host._record_undo_state()
                    self._drag_snapshot_taken = True
                position, power = self._from_canvas(event.position())
                points = self.host._active_curves()[curve_name]["points"]
                if index > 0:
                    position = max(position, points[index - 1]["position_mm"] + 1.0)
                if index < len(points) - 1:
                    position = min(position, points[index + 1]["position_mm"] - 1.0)
                points[index]["position_mm"] = round(position, 1)
                points[index]["power"] = round(max(0.0, power), 1)
                self.host.sync_table_selection(curve_name, index)
                self.pointMoved.emit()
                self.update()
                return

            self._hover_curve, self._hover_index = self._find_point(event.position())
            self.update()

        def mousePressEvent(self, event) -> None:
            curve_name, index = self._find_point(event.position())
            if event.button() == Qt.LeftButton and curve_name is not None:
                self._drag_curve = curve_name
                self._drag_index = index
                self.host.set_active_curve(curve_name)
                self.host.sync_table_selection(curve_name, index)
                return

            if self.host.readonly:
                return

            if event.button() == Qt.RightButton and curve_name is not None and index is not None:
                points = self.host._active_curves()[curve_name]["points"]
                if len(points) <= 2:
                    return
                self.host._record_undo_state()
                del points[index]
                self.host.set_active_curve(curve_name)
                self.host.refresh_table()
                self.pointDeleted.emit()
                self.update()
                return

            if event.button() == Qt.LeftButton:
                active_curve = self.host.active_curve
                position, power = self._from_canvas(event.position())
                points = self.host._active_curves()[active_curve]["points"]
                self.host._record_undo_state()
                points.append({"position_mm": round(position, 1), "power": round(max(0.0, power), 1)})
                points.sort(key=lambda item: item["position_mm"])
                self.host.refresh_table()
                self.pointAdded.emit()
                self.update()

        def mouseReleaseEvent(self, _event) -> None:
            self._drag_curve = None
            self._drag_index = None
            self._drag_snapshot_taken = False

    class PowerCurveEditorWindow(QMainWindow):
        def __init__(self, curve_file: Path, readonly: bool, watch: bool):
            super().__init__()
            self._initializing = True
            self.readonly = readonly
            self.curve_file = curve_file
            self.visible_curves = {name: True for name in CURVE_NAMES}
            self.active_profile = "flat"
            self.active_curve = "Normal"
            self.profile_data = self._load_payload()
            self._undo_stack: list[dict[str, object]] = []
            self._max_undo_steps = 50
            self._last_mtime_ns = self.curve_file.stat().st_mtime_ns if self.curve_file.exists() else None

            self.setWindowTitle("Power Curve Editor")
            self.resize(1220, 720)

            container = QWidget()
            self.setCentralWidget(container)
            root = QVBoxLayout(container)

            toolbar = QHBoxLayout()
            self.status_label = QLabel("")
            self.preview_position = QDoubleSpinBox()
            self.preview_position.setRange(0, 20000)
            self.preview_position.setDecimals(1)
            self.preview_position.setSingleStep(100)
            self.preview_position.setValue(2500)
            self.preview_position.valueChanged.connect(self._refresh_preview_labels)

            toolbar.addWidget(QLabel("Kick Type:"))
            self.profile_list = QListWidget()
            self.profile_list.setFlow(QListWidget.LeftToRight)
            self.profile_list.setMaximumHeight(56)
            self.profile_list.setSpacing(4)
            for profile_key in PROFILE_KEYS:
                item = QListWidgetItem(PROFILE_DISPLAY_NAMES[profile_key])
                item.setData(Qt.UserRole, profile_key)
                self.profile_list.addItem(item)
            self.profile_list.setCurrentRow(0)
            self.profile_list.currentItemChanged.connect(self._profile_changed)
            toolbar.addWidget(self.profile_list)

            for curve_name in CURVE_NAMES:
                checkbox = QCheckBox(curve_name)
                checkbox.setChecked(True)
                checkbox.stateChanged.connect(self._toggle_curve(curve_name))
                toolbar.addWidget(checkbox)

            self.show_control_polyline_checkbox = QCheckBox("Show Control Polyline")
            self.show_control_polyline_checkbox.setChecked(True)
            self.show_control_polyline_checkbox.stateChanged.connect(lambda _state: self.canvas.update())
            toolbar.addWidget(self.show_control_polyline_checkbox)

            toolbar.addStretch(1)
            toolbar.addWidget(QLabel("Preview position(mm):"))
            toolbar.addWidget(self.preview_position)
            root.addLayout(toolbar)

            splitter = QSplitter()
            root.addWidget(splitter, 1)

            left = QWidget()
            left_layout = QVBoxLayout(left)
            splitter.addWidget(left)

            self.canvas = CurveCanvas(self)
            self.canvas.pointMoved.connect(self._mark_dirty)
            self.canvas.pointAdded.connect(self._mark_dirty)
            self.canvas.pointDeleted.connect(self._mark_dirty)
            left_layout.addWidget(self.canvas, 1)

            preview_box = QGroupBox("Preview")
            preview_layout = QFormLayout(preview_box)
            self.preview_labels = {name: QLabel("-") for name in CURVE_NAMES}
            self.preview_group_title = QLabel("")
            preview_layout.addRow("Mode", self.preview_group_title)
            for name in CURVE_NAMES:
                preview_layout.addRow(name, self.preview_labels[name])
            left_layout.addWidget(preview_box)

            right = QWidget()
            right_layout = QVBoxLayout(right)
            splitter.addWidget(right)
            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 2)

            self.curve_list = QListWidget()
            for name in CURVE_NAMES:
                item = QListWidgetItem(name)
                self.curve_list.addItem(item)
            self.curve_list.setCurrentRow(CURVE_NAMES.index(self.active_curve))
            self.curve_list.currentTextChanged.connect(self.set_active_curve)
            right_layout.addWidget(self.curve_list)

            self.table = QTableWidget(0, 2)
            self.table.setHorizontalHeaderLabels(["position_mm", "power"])
            self.table.itemChanged.connect(self._table_item_changed)
            right_layout.addWidget(self.table, 1)

            limits_box = QGroupBox("Clamp")
            limits_layout = QFormLayout(limits_box)
            self.min_power_spin = QDoubleSpinBox()
            self.max_power_spin = QDoubleSpinBox()
            for spin in (self.min_power_spin, self.max_power_spin):
                spin.setRange(0, 100000)
                spin.setDecimals(1)
                spin.setSingleStep(100)
                spin.valueChanged.connect(self._limits_changed)
            self.min_power_spin.setValue(self._active_limits()["min_power"])
            self.max_power_spin.setValue(self._active_limits()["max_power"])
            limits_layout.addRow("Min Power", self.min_power_spin)
            limits_layout.addRow("Max Power", self.max_power_spin)
            right_layout.addWidget(limits_box)

            buttons = QGridLayout()
            self.add_button = QPushButton("Add Point")
            self.remove_button = QPushButton("Remove Point")
            self.save_button = QPushButton("Save")
            self.reload_button = QPushButton("Reload")
            self.reset_button = QPushButton("Reset Default Template")
            self.save_default_button = QPushButton("Save As Default Template")

            self.add_button.clicked.connect(self._add_point)
            self.remove_button.clicked.connect(self._remove_selected_point)
            self.save_button.clicked.connect(self._save)
            self.reload_button.clicked.connect(self._reload)
            self.reset_button.clicked.connect(self._reset_default)
            self.save_default_button.clicked.connect(self._save_as_default_template)

            buttons.addWidget(self.add_button, 0, 0)
            buttons.addWidget(self.remove_button, 0, 1)
            buttons.addWidget(self.save_button, 1, 0)
            buttons.addWidget(self.reload_button, 1, 1)
            buttons.addWidget(self.reset_button, 2, 0, 1, 2)
            buttons.addWidget(self.save_default_button, 3, 0, 1, 2)
            right_layout.addLayout(buttons)

            root.addWidget(self.status_label)

            file_menu = self.menuBar().addMenu("File")
            open_action = QAction("Open...", self)
            open_action.triggered.connect(self._choose_file)
            file_menu.addAction(open_action)
            file_menu.addAction(QAction("Save", self, triggered=self._save))

            self.undo_shortcut = QShortcut(QKeySequence.Undo, self)
            self.undo_shortcut.activated.connect(self._undo)

            self._dirty = False
            self.refresh_table()
            self._refresh_preview_labels()
            self._update_controls()
            self._set_status(f"Editing {self.curve_file}")
            self._initializing = False

            if watch:
                self.watch_timer = QTimer(self)
                self.watch_timer.timeout.connect(self._watch_reload)
                self.watch_timer.start(500)
            else:
                self.watch_timer = None

        def _set_status(self, text: str) -> None:
            self.status_label.setText(text)

        def _deepcopy_payload(self, payload: dict[str, object]) -> dict[str, object]:
            return json.loads(json.dumps(payload))

        def _record_undo_state(self) -> None:
            if self.readonly or getattr(self, "_initializing", False):
                return
            snapshot = self._deepcopy_payload(self._payload_from_state())
            if self._undo_stack and self._undo_stack[-1] == snapshot:
                return
            self._undo_stack.append(snapshot)
            if len(self._undo_stack) > self._max_undo_steps:
                self._undo_stack.pop(0)

        def _apply_payload(self, payload: dict[str, object]) -> None:
            normalized_profiles, limits_profiles, canonical_payload = _validate_payload(payload)
            color_map = {
                "Low": "#67b7dc",
                "Normal": "#7be495",
                "High": "#ff8c69",
            }
            profile_data: dict[str, dict[str, object]] = {}
            for profile_key in PROFILE_KEYS:
                curves = {}
                for curve_name in CURVE_NAMES:
                    curves[curve_name] = {
                        "color": color_map[curve_name],
                        "points": [
                            {"position_mm": point[0], "power": point[1]}
                            for point in normalized_profiles[profile_key][curve_name]
                        ],
                    }
                profile_data[profile_key] = {
                    "curves": curves,
                    "limits": dict(limits_profiles[profile_key]),
                }
            self.profile_data = profile_data

        def _undo(self) -> None:
            if self.readonly or not self._undo_stack:
                return
            snapshot = self._undo_stack.pop()
            self._apply_payload(snapshot)
            self._dirty = True
            self.refresh_table()
            self._refresh_preview_labels()
            self._set_status(f"Undo [{PROFILE_DISPLAY_NAMES[self.active_profile]}]")

        def _mark_dirty(self) -> None:
            self._dirty = True
            self.refresh_table()
            self._refresh_preview_labels()
            self._set_status(f"Modified {self.curve_file}")

        def _active_curves(self) -> dict[str, dict[str, object]]:
            return self.profile_data[self.active_profile]["curves"]  # type: ignore[return-value]

        def _active_limits(self) -> dict[str, float]:
            return self.profile_data[self.active_profile]["limits"]  # type: ignore[return-value]

        def _load_payload(self) -> dict[str, dict[str, object]]:
            payload_file = ensure_curve_file_exists(self.curve_file)
            store = PowerCurveStore(curve_file=payload_file, reload_interval_sec=0.0)
            payload = store.snapshot()
            color_map = {
                "Low": "#67b7dc",
                "Normal": "#7be495",
                "High": "#ff8c69",
            }
            profile_data: dict[str, dict[str, object]] = {}
            for profile_key in PROFILE_KEYS:
                curves: dict[str, dict[str, object]] = {}
                for name in CURVE_NAMES:
                    points = [
                        {
                            "position_mm": float(point["position_mm"]),
                            "power": float(point["power"]),
                        }
                        for point in payload["profiles"][profile_key]["curves"][name]["points"]
                    ]
                    curves[name] = {
                        "color": color_map[name],
                        "points": points,
                    }
                profile_data[profile_key] = {
                    "curves": curves,
                    "limits": store.limits_snapshot(profile=profile_key),
                }
            return profile_data

        def _current_points(self) -> list[dict[str, float]]:
            return self._active_curves()[self.active_curve]["points"]  # type: ignore[return-value]

        def preview_value(self, curve_name: str, distance_mm: float) -> float:
            raw_value = self.preview_raw_value(curve_name, distance_mm)
            return clamp_with_limits(raw_value, self._active_limits())

        def preview_raw_value(self, curve_name: str, distance_mm: float) -> float:
            curve = self._curve_model(curve_name)
            return curve.evaluate(distance_mm)

        def _payload_from_state(self) -> dict[str, object]:
            payload = default_curve_payload()
            for profile_key in PROFILE_KEYS:
                profile_block = payload["profiles"][profile_key]
                profile_limits = self.profile_data[profile_key]["limits"]  # type: ignore[index]
                profile_block["limits"] = {
                    "min_power": float(profile_limits["min_power"]),
                    "max_power": float(profile_limits["max_power"]),
                }
                profile_curves = self.profile_data[profile_key]["curves"]  # type: ignore[index]
                for name in CURVE_NAMES:
                    profile_block["curves"][name]["points"] = profile_curves[name]["points"]  # type: ignore[index]
            return payload

        def _refresh_preview_labels(self) -> None:
            preview_position = self.preview_position.value()
            self.preview_group_title.setText(PROFILE_DISPLAY_NAMES[self.active_profile])
            for name in CURVE_NAMES:
                raw = self.preview_raw_value(name, preview_position)
                clipped = clamp_with_limits(raw, self._active_limits())
                if abs(raw - clipped) < 1e-6:
                    self.preview_labels[name].setText(f"{clipped:.1f}")
                else:
                    self.preview_labels[name].setText(f"{raw:.1f} -> {clipped:.1f}")
            self.canvas.update()

        def _toggle_curve(self, curve_name: str):
            def _handler(state: int) -> None:
                self.visible_curves[curve_name] = bool(state)
                self.canvas.update()
            return _handler

        def set_active_curve(self, curve_name: str | None) -> None:
            if not curve_name:
                return
            self.active_curve = curve_name
            self.refresh_table()
            row = CURVE_NAMES.index(curve_name)
            if self.curve_list.currentRow() != row:
                self.curve_list.setCurrentRow(row)

        def _profile_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
            if current is None:
                return
            profile_key = current.data(Qt.UserRole)
            if not isinstance(profile_key, str):
                return
            self.active_profile = profile_key
            self.refresh_table()
            self._refresh_preview_labels()
            self._set_status(f"Editing {self.curve_file} [{PROFILE_DISPLAY_NAMES[self.active_profile]}]")

        def sync_table_selection(self, curve_name: str, index: int) -> None:
            self.set_active_curve(curve_name)
            self.table.blockSignals(True)
            self.table.selectRow(index)
            self.table.blockSignals(False)

        def refresh_table(self) -> None:
            points = self._current_points()
            self.table.blockSignals(True)
            self.table.setRowCount(len(points))
            for row, point in enumerate(points):
                self.table.setItem(row, 0, QTableWidgetItem(f"{point['position_mm']:.1f}"))
                self.table.setItem(row, 1, QTableWidgetItem(f"{point['power']:.1f}"))
            self.table.blockSignals(False)
            self.min_power_spin.blockSignals(True)
            self.max_power_spin.blockSignals(True)
            self.min_power_spin.setValue(self._active_limits()["min_power"])
            self.max_power_spin.setValue(self._active_limits()["max_power"])
            self.min_power_spin.blockSignals(False)
            self.max_power_spin.blockSignals(False)
            self._update_controls()
            self.canvas.update()

        def _update_controls(self) -> None:
            enabled = not self.readonly
            self.add_button.setEnabled(enabled)
            self.remove_button.setEnabled(enabled)
            self.save_button.setEnabled(enabled)
            self.reset_button.setEnabled(enabled)
            self.save_default_button.setEnabled(enabled)
            self.min_power_spin.setEnabled(enabled)
            self.max_power_spin.setEnabled(enabled)
            if self.readonly:
                self._set_status(f"Read-only {self.curve_file}")

        def _table_item_changed(self, item: QTableWidgetItem) -> None:
            if self.readonly:
                return
            row = item.row()
            col = item.column()
            points = self._current_points()
            try:
                value = float(item.text())
            except ValueError:
                self.refresh_table()
                return
            self._record_undo_state()
            if col == 0:
                if row > 0:
                    value = max(value, points[row - 1]["position_mm"] + 1.0)
                if row < len(points) - 1:
                    value = min(value, points[row + 1]["position_mm"] - 1.0)
                points[row]["position_mm"] = round(max(0.0, value), 1)
            else:
                points[row]["power"] = round(max(0.0, value), 1)
            self._mark_dirty()

        def _limits_changed(self) -> None:
            if getattr(self, "_initializing", False):
                return
            if self.readonly:
                return
            min_power = self.min_power_spin.value()
            max_power = self.max_power_spin.value()
            if max_power < min_power:
                sender = self.sender()
                if sender is self.min_power_spin:
                    self.max_power_spin.blockSignals(True)
                    self.max_power_spin.setValue(min_power)
                    self.max_power_spin.blockSignals(False)
                    max_power = min_power
                else:
                    self.min_power_spin.blockSignals(True)
                    self.min_power_spin.setValue(max_power)
                    self.min_power_spin.blockSignals(False)
                    min_power = max_power
            self._record_undo_state()
            active_limits = self._active_limits()
            active_limits["min_power"] = round(min_power, 1)
            active_limits["max_power"] = round(max_power, 1)
            self._mark_dirty()

        def _add_point(self) -> None:
            if self.readonly:
                return
            self._record_undo_state()
            points = self._current_points()
            tail = points[-1]["position_mm"]
            tail_power = points[-1]["power"]
            points.append({"position_mm": tail + 500.0, "power": tail_power})
            self._mark_dirty()

        def _remove_selected_point(self) -> None:
            if self.readonly:
                return
            row = self.table.currentRow()
            points = self._current_points()
            if row < 0 or len(points) <= 2:
                return
            self._record_undo_state()
            del points[row]
            self._mark_dirty()

        def _save(self) -> None:
            if self.readonly:
                return
            payload = self._payload_from_state()
            try:
                atomic_write_curve_file(payload, self.curve_file)
            except Exception as exc:
                QMessageBox.critical(self, "Save Failed", str(exc))
                return
            self._dirty = False
            self._last_mtime_ns = self.curve_file.stat().st_mtime_ns
            self._set_status(f"Saved {self.curve_file}")

        def _reload(self) -> None:
            self.profile_data = self._load_payload()
            self._undo_stack.clear()
            self._dirty = False
            self._last_mtime_ns = self.curve_file.stat().st_mtime_ns if self.curve_file.exists() else None
            self.refresh_table()
            self._refresh_preview_labels()
            self._set_status(f"Reloaded {self.curve_file} [{PROFILE_DISPLAY_NAMES[self.active_profile]}]")

        def _reset_default(self) -> None:
            if self.readonly:
                return
            self._record_undo_state()
            self.profile_data = self._load_payload_from_default()
            self._mark_dirty()

        def _save_as_default_template(self) -> None:
            if self.readonly:
                return
            payload = self._payload_from_state()
            template_file = default_curve_template_file()
            try:
                atomic_write_curve_file(payload, template_file)
            except Exception as exc:
                QMessageBox.critical(self, "Save Default Template Failed", str(exc))
                return
            self._set_status(f"Saved default template {template_file}")

        def _load_payload_from_default(self) -> dict[str, dict[str, object]]:
            template_file = ensure_curve_file_exists(default_curve_template_file())
            store = PowerCurveStore(curve_file=template_file, reload_interval_sec=0.0)
            payload = store.snapshot()
            color_map = {
                "Low": "#67b7dc",
                "Normal": "#7be495",
                "High": "#ff8c69",
            }
            profile_data: dict[str, dict[str, object]] = {}
            for profile_key in PROFILE_KEYS:
                curves = {
                    name: {
                        "color": color_map[name],
                        "points": [
                            {
                                "position_mm": float(point["position_mm"]),
                                "power": float(point["power"]),
                            }
                            for point in payload["profiles"][profile_key]["curves"][name]["points"]
                        ],
                    }
                    for name in CURVE_NAMES
                }
                profile_data[profile_key] = {
                    "curves": curves,
                    "limits": store.limits_snapshot(profile=profile_key),
                }
            return profile_data

        def _curve_model(self, curve_name: str) -> MonotoneCubicCurve:
            payload = self._payload_from_state()
            normalized_profiles, _limits_profiles, _canonical = _validate_payload(payload)
            return MonotoneCubicCurve.from_points(normalized_profiles[self.active_profile][curve_name])

        def sample_curve_points(self, curve_name: str, samples_per_segment: int = 24) -> list[tuple[float, float]]:
            points = self._active_curves()[curve_name]["points"]  # type: ignore[index]
            if len(points) < 2:
                return []
            curve = self._curve_model(curve_name)
            sampled: list[tuple[float, float]] = []
            for index in range(len(points) - 1):
                start = float(points[index]["position_mm"])
                end = float(points[index + 1]["position_mm"])
                for step in range(samples_per_segment):
                    t = step / samples_per_segment
                    distance = start + (end - start) * t
                    sampled.append((distance, curve.evaluate(distance)))
            sampled.append((float(points[-1]["position_mm"]), curve.evaluate(float(points[-1]["position_mm"]))))
            return sampled

        def _choose_file(self) -> None:
            selected, _ = QFileDialog.getOpenFileName(self, "Open Curve File", str(self.curve_file.parent), "JSON Files (*.json)")
            if not selected:
                return
            self.curve_file = Path(selected)
            ensure_curve_file_exists(self.curve_file)
            self._undo_stack.clear()
            self._reload()

        def _watch_reload(self) -> None:
            if self._dirty or not self.curve_file.exists():
                return
            mtime_ns = self.curve_file.stat().st_mtime_ns
            if self._last_mtime_ns is None or mtime_ns != self._last_mtime_ns:
                self._reload()

    curve_file = Path(args.curve_file)
    if not curve_file.is_absolute():
        curve_file = zbin_dir / curve_file
    ensure_curve_file_exists(curve_file)

    app = QApplication(sys.argv)
    window = PowerCurveEditorWindow(curve_file=curve_file, readonly=args.readonly, watch=args.watch)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
