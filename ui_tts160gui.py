# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'tts160gui.ui'
##
## Created by: Qt User Interface Compiler version 6.9.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QLabel, QMainWindow, QMenuBar,
    QPushButton, QSizePolicy, QStatusBar, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(892, 654)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.pushStart = QPushButton(self.centralwidget)
        self.pushStart.setObjectName(u"pushStart")
        self.pushStart.setEnabled(True)
        self.pushStart.setGeometry(QRect(30, 10, 101, 41))
        self.pushStop = QPushButton(self.centralwidget)
        self.pushStop.setObjectName(u"pushStop")
        self.pushStop.setEnabled(False)
        self.pushStop.setGeometry(QRect(30, 60, 101, 41))
        self.labelStatus = QLabel(self.centralwidget)
        self.labelStatus.setObjectName(u"labelStatus")
        self.labelStatus.setGeometry(QRect(160, 40, 111, 31))
        self.labelStatus.setAutoFillBackground(False)
        self.labelStatus.setStyleSheet(u"background-color: rgb(255, 255, 255);")
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 892, 33))
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.pushStart.setText(QCoreApplication.translate("MainWindow", u"Start Driver", None))
        self.pushStop.setText(QCoreApplication.translate("MainWindow", u"Stop Driver", None))
        self.labelStatus.setText(QCoreApplication.translate("MainWindow", u"Not Started", None))
    # retranslateUi

