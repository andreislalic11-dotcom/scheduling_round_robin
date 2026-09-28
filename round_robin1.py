import sys
from collections import deque

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
    QMessageBox, QPushButton, QSlider, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

PALETTE = ["#ff4d6d", "#4cc9f0", "#ffd166", "#06d6a0", "#b388ff",
           "#ff9f1c", "#72efdd", "#f15bb5", "#9ef01a", "#48bfe3"]
IDLE_COLOR = "#2b2b45"


# ----------------------------------------------------------------------------
# Round Robin logic (pure Python, no GUI) - simulated one time unit at a time
# ----------------------------------------------------------------------------
def simulate_round_robin(processes, quantum):
    """
    processes: list of (name, arrival, burst)
    Returns (snapshots, completion)
      snapshots: one dict per time unit: {t, running, queue, remaining}
      completion: {name: completion_time}
    """
    remaining = {n: b for n, a, b in processes}
    pending = sorted(processes, key=lambda p: p[1])  # by arrival (stable)
    queue = deque()
    completion = {}
    snapshots = []
    t = 0
    running = None
    used = 0

    def admit(now):
        while pending and pending[0][1] <= now:
            queue.append(pending.pop(0)[0])

    admit(t)
    while len(completion) < len(processes):
        if running is None:
            if queue:
                running = queue.popleft()
                used = 0
            else:  # CPU idle
                snapshots.append({"t": t, "running": None, "queue": [],
                                  "remaining": dict(remaining)})
                t += 1
                admit(t)
                continue

        snapshots.append({"t": t, "running": running, "queue": list(queue),
                          "remaining": dict(remaining)})
        remaining[running] -= 1
        used += 1
        t += 1
        admit(t)  # new arrivals enter before the preempted process

        if remaining[running] == 0:
            completion[running] = t
            running = None
        elif used == quantum:
            queue.append(running)
            running = None

    return snapshots, completion


# ----------------------------------------------------------------------------
# Arena widget: ready queue + CPU + Gantt chart, all custom painted
# ----------------------------------------------------------------------------
class Arena(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(330)
        self.reset()

    def reset(self):
        self.snaps = []
        self.colors = {}
        self.bursts = {}
        self.idx = -1
        self.finished = False
        self.update()

    def load(self, snaps, colors, bursts):
        self.snaps, self.colors, self.bursts = snaps, colors, bursts
        self.idx = -1
        self.finished = False
        self.update()

    def set_index(self, idx, finished=False):
        self.idx = idx
        self.finished = finished
        self.update()

    def _color(self, name):
        return QColor(self.colors.get(name, IDLE_COLOR))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#0f0f23"))

        # faint grid
        p.setPen(QPen(QColor("#181840"), 1))
        for x in range(0, w, 30):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 30):
            p.drawLine(0, y, w, y)

        title_font = QFont("Courier New", 11, QFont.Bold)
        small = QFont("Courier New", 9, QFont.Bold)

        if self.idx < 0:
            p.setPen(QColor("#ffd166"))
            p.setFont(QFont("Courier New", 20, QFont.Bold))
            msg = "PRESS  START" if not self.snaps else "GET READY..."
            p.drawText(self.rect(), Qt.AlignCenter, msg)
            return

        snap = self.snaps[self.idx]
        running = snap["running"]

        # ---- header
        p.setFont(title_font)
        p.setPen(QColor("#4cc9f0"))
        p.drawText(20, 26, "READY QUEUE")
        p.drawText(w - 190, 26, "CPU")
        p.setPen(QColor("#ffd166"))
        p.drawText(w // 2 - 40, 26, f"TIME = {snap['t']}")

        # ---- ready queue chips
        cw, ch, gap = 84, 62, 10
        x = 20
        max_chips = max(1, (w - 240 - 20) // (cw + gap))
        shown = snap["queue"][:max_chips]
        for name in shown:
            self._chip(p, QRectF(x, 40, cw, ch), name, snap["remaining"][name], small)
            x += cw + gap
        extra = len(snap["queue"]) - len(shown)
        if extra > 0:
            p.setPen(QColor("#ffffff"))
            p.setFont(small)
            p.drawText(int(x), 78, f"+{extra}")
        if not snap["queue"]:
            p.setPen(QColor("#555588"))
            p.setFont(small)
            p.drawText(20, 78, "(empty)")

        # ---- CPU box
        box = QRectF(w - 200, 40, 170, 90)
        if running:
            col = self._color(running)
            glow = QColor(col)
            glow.setAlpha(70 if self.idx % 2 else 130)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(box.adjusted(-6, -6, 6, 6), 12, 12)
            p.setBrush(col)
            p.setPen(QPen(QColor("#ffffff"), 3))
            p.drawRoundedRect(box, 10, 10)
            p.setPen(QColor("#0f0f23"))
            p.setFont(QFont("Courier New", 20, QFont.Bold))
            p.drawText(box.adjusted(0, 6, 0, -30), Qt.AlignCenter, running)
            p.setFont(small)
            p.drawText(box.adjusted(0, 50, 0, 0), Qt.AlignHCenter | Qt.AlignTop,
                       f"left: {snap['remaining'][running]}")
        else:
            p.setPen(QPen(QColor("#555588"), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(box, 10, 10)
            p.setFont(title_font)
            p.drawText(box, Qt.AlignCenter, "IDLE")

        # ---- Gantt chart
        n = len(self.snaps)
        x0, gy, gh = 20, h - 100, 46
        bw = min(48, (w - 40) / max(n, 1))
        p.setPen(QColor("#4cc9f0"))
        p.setFont(title_font)
        p.drawText(20, gy - 12, "GANTT CHART")
        for i in range(self.idx + 1):
            s = self.snaps[i]
            r = QRectF(x0 + i * bw, gy, bw, gh)
            p.setPen(QPen(QColor("#0f0f23"), 1))
            p.setBrush(self._color(s["running"]) if s["running"] else QColor(IDLE_COLOR))
            p.drawRect(r)
            if s["running"] and bw >= 22:
                p.setPen(QColor("#0f0f23"))
                p.setFont(small)
                p.drawText(r, Qt.AlignCenter, s["running"])
        p.setPen(QColor("#aaaacc"))
        p.setFont(QFont("Courier New", 8))
        step = 1 if bw >= 24 else 5
        for i in range(0, self.idx + 2, step):
            p.drawText(int(x0 + i * bw) - 4, gy + gh + 16, str(i))

        if self.finished:
            p.setPen(QColor("#06d6a0"))
            p.setFont(QFont("Courier New", 16, QFont.Bold))
            p.drawText(QRectF(0, 150, w, 40), Qt.AlignCenter, "*** LEVEL CLEAR ***")

    def _chip(self, p, rect, name, remaining, font):
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.setBrush(self._color(name))
        p.drawRoundedRect(rect, 8, 8)
        p.setPen(QColor("#0f0f23"))
        p.setFont(font)
        p.drawText(rect.adjusted(0, 4, 0, -28), Qt.AlignCenter, name)
        # HP bar = remaining burst
        total = max(self.bursts.get(name, 1), 1)
        bar = QRectF(rect.left() + 8, rect.bottom() - 18, rect.width() - 16, 9)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#0f0f23"))
        p.drawRect(bar)
        p.setBrush(QColor("#ffffff"))
        p.drawRect(QRectF(bar.left(), bar.top(), bar.width() * remaining / total, bar.height()))


# ----------------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------------
STYLE = """
QMainWindow, QWidget { background: #0f0f23; color: #e8e8ff;
                       font-family: 'Courier New'; font-size: 12px; }
QGroupBox { border: 2px solid #4cc9f0; border-radius: 6px; margin-top: 14px;
            padding: 8px; font-weight: bold; color: #4cc9f0; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QPushButton { background: #1b1b45; border: 2px solid #ffd166; border-radius: 6px;
              padding: 6px 10px; color: #ffd166; font-weight: bold; }
QPushButton:hover { background: #ffd166; color: #0f0f23; }
QPushButton:disabled { border-color: #444; color: #444; }
QTableWidget { background: #14142f; gridline-color: #2b2b60; border: 1px solid #2b2b60; }
QHeaderView::section { background: #1b1b45; color: #ffd166; border: 1px solid #2b2b60; padding: 3px; }
QSpinBox { background: #14142f; border: 1px solid #4cc9f0; padding: 3px; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ROUND ROBIN - CPU Scheduler Arena")
        self.resize(1150, 700)
        self.setStyleSheet(STYLE)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.snaps, self.completion, self.idx = [], {}, -1
        self.procs = []

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)

        # ---------------- left panel: inputs
        left = QVBoxLayout()
        layout.addLayout(left, 0)

        box = QGroupBox("PLAYERS (PROCESSES)")
        bl = QVBoxLayout(box)
        self.input_table = QTableWidget(0, 3)
        self.input_table.setHorizontalHeaderLabels(["Name", "Arrival", "Burst"])
        self.input_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.input_table.setFixedWidth(300)
        bl.addWidget(self.input_table)
        row = QHBoxLayout()
        add_btn, del_btn = QPushButton("+ Add"), QPushButton("- Remove")
        add_btn.clicked.connect(lambda: self.add_row())
        del_btn.clicked.connect(self.remove_row)
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        bl.addLayout(row)
        left.addWidget(box)

        qbox = QGroupBox("SETTINGS")
        ql = QVBoxLayout(qbox)
        qrow = QHBoxLayout()
        qrow.addWidget(QLabel("Time Quantum:"))
        self.quantum = QSpinBox()
        self.quantum.setRange(1, 99)
        self.quantum.setValue(3)
        qrow.addWidget(self.quantum)
        ql.addLayout(qrow)
        ql.addWidget(QLabel("Speed:"))
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(1, 10)
        self.speed.setValue(4)
        self.speed.valueChanged.connect(self.update_speed)
        ql.addWidget(self.speed)
        left.addWidget(qbox)

        self.start_btn = QPushButton("START")
        self.pause_btn = QPushButton("PAUSE")
        self.reset_btn = QPushButton("RESET")
        self.start_btn.clicked.connect(self.start)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.reset_btn.clicked.connect(self.reset)
        self.pause_btn.setEnabled(False)
        for b in (self.start_btn, self.pause_btn, self.reset_btn):
            left.addWidget(b)
        left.addStretch()

        # ---------------- right panel: arena + results
        right = QVBoxLayout()
        layout.addLayout(right, 1)
        self.arena = Arena()
        right.addWidget(self.arena, 3)

        self.result_table = QTableWidget(0, 6)
        self.result_table.setHorizontalHeaderLabels(
            ["Process", "Arrival", "Burst", "Completion", "Turnaround", "Waiting"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        right.addWidget(self.result_table, 2)
        self.avg_label = QLabel("")
        self.avg_label.setStyleSheet("color:#06d6a0; font-weight:bold; font-size:13px;")
        right.addWidget(self.avg_label)

        # sample data
        for name, a, b in [("P1", 0, 5), ("P2", 1, 3), ("P3", 2, 8), ("P4", 3, 6)]:
            self.add_row(name, a, b)

    # ---------- input table helpers
    def add_row(self, name=None, arrival=0, burst=1):
        r = self.input_table.rowCount()
        self.input_table.insertRow(r)
        name = name or f"P{r + 1}"
        for c, v in enumerate((name, arrival, burst)):
            item = QTableWidgetItem(str(v))
            item.setTextAlignment(Qt.AlignCenter)
            self.input_table.setItem(r, c, item)

    def remove_row(self):
        r = self.input_table.currentRow()
        if r < 0:
            r = self.input_table.rowCount() - 1
        if r >= 0:
            self.input_table.removeRow(r)

    def read_inputs(self):
        procs, seen = [], set()
        for r in range(self.input_table.rowCount()):
            try:
                name = self.input_table.item(r, 0).text().strip()
                arrival = int(self.input_table.item(r, 1).text())
                burst = int(self.input_table.item(r, 2).text())
            except (ValueError, AttributeError):
                raise ValueError(f"Row {r + 1}: arrival and burst must be whole numbers.")
            if not name or name in seen:
                raise ValueError(f"Row {r + 1}: names must be unique and not empty.")
            if arrival < 0 or burst < 1:
                raise ValueError(f"Row {r + 1}: arrival >= 0 and burst >= 1 required.")
            seen.add(name)
            procs.append((name, arrival, burst))
        if not procs:
            raise ValueError("Add at least one process.")
        return procs

    # ---------- controls
    def update_speed(self):
        self.timer.setInterval(1100 - self.speed.value() * 100)

    def start(self):
        try:
            self.procs = self.read_inputs()
        except ValueError as e:
            QMessageBox.warning(self, "Invalid input", str(e))
            return
        self.snaps, self.completion = simulate_round_robin(self.procs, self.quantum.value())
        colors = {n: PALETTE[i % len(PALETTE)] for i, (n, _, _) in enumerate(self.procs)}
        bursts = {n: b for n, _, b in self.procs}
        self.arena.load(self.snaps, colors, bursts)
        self.result_table.setRowCount(0)
        self.avg_label.setText("")
        self.idx = -1
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("PAUSE")
        self.update_speed()
        self.timer.start()

    def toggle_pause(self):
        if self.timer.isActive():
            self.timer.stop()
            self.pause_btn.setText("RESUME")
        elif self.idx < len(self.snaps) - 1:
            self.timer.start()
            self.pause_btn.setText("PAUSE")

    def reset(self):
        self.timer.stop()
        self.arena.reset()
        self.result_table.setRowCount(0)
        self.avg_label.setText("")
        self.idx = -1
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("PAUSE")

    def tick(self):
        self.idx += 1
        done = self.idx >= len(self.snaps) - 1
        self.arena.set_index(self.idx, finished=done)
        if done:
            self.timer.stop()
            self.show_results()
            self.start_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)

    def show_results(self):
        total_tat = total_wt = 0
        self.result_table.setRowCount(len(self.procs))
        for r, (name, arrival, burst) in enumerate(self.procs):
            comp = self.completion[name]
            tat = comp - arrival
            wt = tat - burst
            total_tat += tat
            total_wt += wt
            for c, v in enumerate((name, arrival, burst, comp, tat, wt)):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignCenter)
                self.result_table.setItem(r, c, item)
        n = len(self.procs)
        self.avg_label.setText(
            f"Avg Turnaround: {total_tat / n:.2f}    Avg Waiting: {total_wt / n:.2f}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())