# -*- coding: utf-8 -*-
"""
考勤填报口径确认 —— 面板部件
============================
原 AttendanceReviewDialog 的正文，改为嵌入右侧面板的 QWidget：
让人工确认白/夜班标准工时、夜班判定、加班口径，确认后 accepted 信号
带回写好的 opts；取消发 cancelled。兼容 Win7 + Python3.8 + PySide2。
"""
from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                               QLabel, QPushButton, QCheckBox, QDoubleSpinBox,
                               QFrame)


class AttendanceFormWidget(QWidget):
    accepted = Signal(object)             # 带回 opts
    cancelled = Signal()

    def __init__(self, opts, parent=None):
        super(AttendanceFormWidget, self).__init__(parent)
        self.opts = opts
        self._build()
        self._toggle_night(self.chk_night.isChecked())

    def _spin(self, val, lo, hi, step=0.5, suffix=" 小时"):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi); sp.setSingleStep(step); sp.setDecimals(1)
        sp.setValue(val); sp.setSuffix(suffix); sp.setMinimumWidth(120)
        return sp

    def _sec_title(self, text):
        lbl = QLabel(text); lbl.setObjectName("SecTitle")
        return lbl

    def _toggle_night(self, on):
        self.night_box.setEnabled(on)

    def _build(self):
        o = self.opts
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 18); lay.setSpacing(12)
        head = QLabel("开始填报前，请确认计算口径。默认值与常规设置一致，可按本次情况调整。")
        head.setObjectName("PageDesc"); head.setWordWrap(True)
        lay.addWidget(head)
        lay.addWidget(self._sec_title("白班"))
        g1 = QGridLayout(); g1.setHorizontalSpacing(12); g1.setVerticalSpacing(8)
        g1.addWidget(QLabel("标准工时（加班基准）"), 0, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.sp_day = self._spin(o.workday_hours, 1, 24)
        g1.addWidget(self.sp_day, 0, 1)
        h1 = QLabel("实际工时减去它，多出的部分算加班。")
        h1.setObjectName("Hint"); g1.addWidget(h1, 0, 2); g1.setColumnStretch(2, 1)
        lay.addLayout(g1)
        self.chk_night = QCheckBox("计算夜班（两班制，跨零点自动 +24 修正）")
        self.chk_night.setChecked(o.night_shift)
        self.chk_night.toggled.connect(self._toggle_night)
        lay.addWidget(self.chk_night)
        self.night_box = QWidget()
        g2 = QGridLayout(self.night_box)
        g2.setContentsMargins(22, 0, 0, 0); g2.setHorizontalSpacing(12); g2.setVerticalSpacing(8)
        g2.addWidget(QLabel("判为夜班：上班钟点 >="), 0, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.sp_nstart = self._spin(o.night_start_hour, 0, 23.5, 0.5, " 点")
        g2.addWidget(self.sp_nstart, 0, 1)
        g2.addWidget(QLabel("夜班标准工时"), 1, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.sp_nhours = self._spin(o.night_workday_hours, 1, 24)
        g2.addWidget(self.sp_nhours, 1, 1)
        g2.addWidget(QLabel("夜班合理上限"), 2, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.sp_nmax = self._spin(o.night_max_hours, 1, 24)
        g2.addWidget(self.sp_nmax, 2, 1)
        hn = QLabel("超过上限视为疑似漏打卡，标黄并汇总到异常报告。")
        hn.setObjectName("Hint"); hn.setWordWrap(True)
        g2.addWidget(hn, 2, 2); g2.setColumnStretch(2, 1)
        lay.addWidget(self.night_box)
        self.chk_ot = QCheckBox('计算“加班”列（不足标准工时记 0）')
        self.chk_ot.setChecked(o.overtime)
        lay.addWidget(self.chk_ot)
        lay.addStretch(1)
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setObjectName("Sep")
        lay.addWidget(line)
        row = QHBoxLayout(); row.addStretch(1)
        cancel = QPushButton("取消"); cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.cancelled.emit)
        ok = QPushButton("按此填报"); ok.setObjectName("Primary")
        ok.clicked.connect(self._on_ok)
        row.addWidget(cancel); row.addWidget(ok)
        lay.addLayout(row)

    def _on_ok(self):
        o = self.opts
        o.workday_hours = float(self.sp_day.value())
        o.overtime = bool(self.chk_ot.isChecked())
        o.night_shift = bool(self.chk_night.isChecked())
        o.night_start_hour = float(self.sp_nstart.value())
        o.night_workday_hours = float(self.sp_nhours.value())
        o.night_max_hours = float(self.sp_nmax.value())
        self.accepted.emit(o)
