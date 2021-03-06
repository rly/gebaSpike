from PyQt5 import QtWidgets, QtGui, QtCore
import pyqtgraph as pg
import os
from .default_parameters import project_name, channel_range, alt_action_button
from .plot_utils import CustomViewBox, MultiLine, get_channel_color
import numpy as np
from .gui_utils import Communicate
from functools import partial
from .plot_functions import cut_cell
from .waveform_cut_functions import get_channel_y_edges, setPlotTitle, maxSpikesChange, moveToChannel
from .undo import undo_function


class PopUpCutWindow(QtWidgets.QWidget):
    def __init__(self, mainWindow):
        super(PopUpCutWindow, self).__init__()

        self.mainWindow = mainWindow

        pg.setConfigOptions(antialias=True)

        QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create('GTK+'))

        # declaring the icon image
        self.setWindowIcon(QtGui.QIcon(os.path.join(self.mainWindow.IMG_DIR, 'GEBA_Logo.png')))

        self.setWindowTitle("%s - Popup Cutting Window" % project_name)  # sets the main window title

        self.channel_win = None
        self.unit_win = None
        self.hide_btn = None
        self.channel_number = None

        self.drag_active = False

        self.choice = None
        self.LogError = Communicate()
        self.LogError.signal.connect(self.raiseError)

        self.active_ROI = []

        self.avg_plot_lines = {}
        self.plot_lines = {}

        self.channel_avg_plot_lines = {}
        self.channel_plot_lines = {}

        self.index = None
        self.cell = None

        self.PopUpActive = False

        self.samples_per_spike = None
        self.n_channels = None

        self.initialize()  # initializes the main window

    def raiseError(self, error):

        if 'InvalidMoveChannel' in error:
            self.choice = QtWidgets.QMessageBox.question(self, "Invalid Move to Cell Value!",
                                                         "The value you have chosen for the 'Move to Cell' value is "
                                                         "invalid, please choose a valid value before continuing!",
                                                         QtWidgets.QMessageBox.Ok)

        elif 'SameChannelInvalid' in error:
            self.choice = QtWidgets.QMessageBox.question(self, "Same Channel Error!",
                                                         "The value you have chosen for the 'Move to Cell' value is "
                                                         "the same as the cell you are cutting from! If you would like "
                                                         "to move these selected spikes to a different channel, please "
                                                         "choose another channel!",
                                                         QtWidgets.QMessageBox.Ok)

        elif 'ActionsMade' in error:
            self.choice = QtWidgets.QMessageBox.question(self, "Are you sure...?",
                                                         "You have performed some actions that will be lost when you"
                                                         " reload this cut file. Are you sure you want to continue?",
                                                         QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)

        elif 'invalidMaxSpikes' in error:
            self.choice = QtWidgets.QMessageBox.question(self, "Invalid Max Spikes",
                                                         "The number chosen for Max Spikes is invalid!",
                                                         QtWidgets.QMessageBox.Ok)

    def initialize(self):

        # parameter layout

        channel_layout = QtWidgets.QHBoxLayout()
        channel_label = QtWidgets.QLabel("Channel:")
        self.channel_number = QtWidgets.QComboBox()
        self.channel_number.currentIndexChanged.connect(self.plot_channel)

        channel_layout.addWidget(channel_label)
        channel_layout.addWidget(self.channel_number)

        max_spike_label = QtWidgets.QLabel("Max Plot Spikes:")
        self.max_spike_plots_text = QtWidgets.QLineEdit()
        self.max_spike_plots_text.setToolTip("This is the maximum number of spikes to plot.")
        self.max_spike_plots_text.setText(self.mainWindow.max_spike_plots_text.text())
        self.max_spike_plots_text.textChanged.connect(lambda: maxSpikesChange(self, 'popup'))

        max_spikes_layout = QtWidgets.QHBoxLayout()
        max_spikes_layout.addWidget(max_spike_label)
        max_spikes_layout.addWidget(self.max_spike_plots_text)

        move_to_layout = QtWidgets.QHBoxLayout()

        move_to_label = QtWidgets.QLabel("Move to Cell:")
        self.move_to_channel = QtWidgets.QLineEdit()
        self.move_to_channel.setText(self.mainWindow.move_to_channel.text())
        self.move_to_channel.textChanged.connect(lambda: moveToChannel(self, 'popup'))

        move_to_layout.addWidget(move_to_label)
        move_to_layout.addWidget(self.move_to_channel)

        parameter_layout = QtWidgets.QHBoxLayout()
        parameter_layout.addStretch(1)
        for object_ in [channel_layout, move_to_layout, max_spikes_layout]:
            if 'Layout' in object_.__str__():
                parameter_layout.addLayout(object_)
                parameter_layout.addStretch(1)
            else:
                parameter_layout.addWidget(object_, 0, QtCore.Qt.AlignCenter)
                parameter_layout.addStretch(1)

        # plot layout
        self.channel_win = pg.GraphicsWindow()
        self.channel_plot = self.channel_win.addPlot(row=0, col=0, viewBox=CustomViewBox(self, self.channel_win))
        self.channel_plot.hideAxis('left')  # remove the y-axis
        self.channel_plot.hideAxis('bottom')  # remove the x axis
        self.channel_plot.hideButtons()  # hide the auto-resize button
        self.channel_plot.setMouseEnabled(x=False, y=False)  # disables the mouse interactions
        self.channel_plot.enableAutoRange(False, False)
        self.vb_channel_plot = self.channel_plot.vb
        self.vb_channel_plot.mouseDragEvent = partial(dragPopup, self, 'channel',
                                                   self.vb_channel_plot)  # overriding the drag event
        self.vb_channel_plot.mouseClickEvent = partial(mouse_click_eventPopup, self, self.vb_channel_plot)

        self.channel_drag_lines = None

        self.unit_win = pg.GraphicsWindow()
        self.unit_plot = self.unit_win.addPlot(row=0, col=0, viewBox=CustomViewBox(self, self.unit_win))
        self.unit_plot.hideAxis('left')  # remove the y-axis
        self.unit_plot.hideAxis('bottom')  # remove the x axis
        self.unit_plot.hideButtons()  # hide the auto-resize button
        self.unit_plot.setMouseEnabled(x=False, y=False)  # disables the mouse interactions
        self.unit_plot.enableAutoRange(False, False)

        self.vb_unit_plot = self.unit_plot.vb

        self.vb_unit_plot.mouseDragEvent = partial(dragPopup, self, 'unit', self.vb_unit_plot)  # overriding the drag event
        self.vb_unit_plot.mouseClickEvent = partial(mouse_click_eventPopup, self, self.vb_unit_plot)

        self.unit_drag_lines = None

        plot_layout = QtWidgets.QHBoxLayout()
        for _object in [self.channel_win, self.unit_win]:
            plot_layout.addWidget(_object)

        # button layout

        button_layout = QtWidgets.QHBoxLayout()

        self.undo_btn = QtWidgets.QPushButton("Undo")
        self.undo_btn.clicked.connect(lambda: undo_function(self.mainWindow))

        self.hide_btn = QtWidgets.QPushButton("Hide")
        self.hide_btn.clicked.connect(self.hideF)

        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel)

        for widget in [self.undo_btn, self.hide_btn, self.cancel_btn]:
            button_layout.addWidget(widget)

        # adding all widgets/layouts to the main layout

        layout_order = [parameter_layout, plot_layout, button_layout]
        add_Stretch = [False, False, False]
        # ---------------- add all the layouts and widgets to the Main Window's layout ------------ #
        popupLayout = QtWidgets.QVBoxLayout()

        for widget, addStretch in zip(layout_order, add_Stretch):
            if 'Layout' in widget.__str__():
                popupLayout.addLayout(widget)
                if addStretch:
                    popupLayout.addStretch(1)
            else:
                popupLayout.addWidget(widget, 0, QtCore.Qt.AlignCenter)
                if addStretch:
                    popupLayout.addStretch(1)

        self.setLayout(popupLayout)  # defining the layout of the Main Window

    def cancel(self):
        self.hideF()
        self.mainWindow.PopUpCutWindow.pop(self.cell)

    def hideF(self):
        self.hide()
        self.PopUpActive = False

    def keyPressEvent(self, event):
        """
        This method will occur when the Popup Window is on top and the user presses a button

        :param event:
        :return:
        """
        if type(event) == QtGui.QKeyEvent:
            # here accept the event and do something
            if event.key() == alt_action_button:
                # check if there is a popup that is shown
                cut_cell(self, self.index)

            event.accept()
        else:
            event.ignore()

    def plot(self, index, cell):

        self.PopUpActive = True

        self.index = index
        self.cell = cell

        if self.n_channels is None:
            self.n_channels = self.mainWindow.n_channels
            for channel in np.arange(self.n_channels):
                self.channel_number.addItem(str(int(channel+1)))
            self.channel_number.setCurrentIndex(0)
            self.unit_plot.setYRange(0, -self.n_channels * channel_range, padding=0)

        if self.samples_per_spike is None:
            self.samples_per_spike = self.mainWindow.samples_per_spike
            self.unit_plot.setXRange(0, self.samples_per_spike, padding=0)  # set the x-range
            self.channel_plot.setXRange(0, self.samples_per_spike, padding=0)  # set the x-range

        setTitle = False
        for channel in np.arange(self.n_channels):

            if index in self.mainWindow.unit_data.keys():
                plot_data = self.mainWindow.unit_data[index][channel]
            else:
                # self.reset_plots()
                self.cancel()
                return

            plot_data_avg = np.mean(plot_data, axis=0).reshape((1, -1))

            current_n = plot_data.shape[0]

            plot_data = plot_data[self.mainWindow.cell_subsample_i[cell][channel], :]

            if not setTitle:
                if cell in self.mainWindow.original_cell_count.keys():
                    setPlotTitle(self.unit_plot, cell, original_cell_count=self.mainWindow.original_cell_count[cell],
                                 current_cell_count=current_n)
                else:
                    setPlotTitle(self.unit_plot, cell, current_cell_count=current_n)
                setTitle = True

            if index not in self.plot_lines.keys():
                self.plot_lines[index] = {
                    channel: MultiLine(np.tile(np.arange(self.samples_per_spike), (plot_data.shape[0], 1)),
                                       plot_data, pen_color=get_channel_color(cell))}
            else:
                if channel in self.plot_lines[index].keys():
                    self.unit_plot.removeItem(self.plot_lines[index][channel])
                self.plot_lines[index][channel] = MultiLine(np.tile(np.arange(self.samples_per_spike),
                                                                     (plot_data.shape[0], 1)),  plot_data,
                                                            pen_color=get_channel_color(cell))

            if index not in self.avg_plot_lines.keys():
                self.avg_plot_lines[index] = {channel: MultiLine(np.arange(self.samples_per_spike).reshape((1, -1)),
                                                                 plot_data_avg, pen_color='w', pen_width=2)}
            else:
                if channel in self.avg_plot_lines[index].keys():
                    self.unit_plot.removeItem(self.avg_plot_lines[index][channel])

                self.avg_plot_lines[index][channel] = MultiLine(np.arange(self.samples_per_spike).reshape((1, -1)),
                                                                plot_data_avg, pen_color='w', pen_width=2)

            self.unit_plot.addItem(self.plot_lines[index][channel])
            self.unit_plot.addItem(self.avg_plot_lines[index][channel])

        self.plot_channel()

        self.show()

    def plot_channel(self):

        self.channel_plot.clear()

        if self.samples_per_spike is None:
            return

        channel = int(self.channel_number.currentText()) - 1

        plot_data = self.mainWindow.unit_data[self.index][channel]
        plot_data_avg = np.mean(plot_data, axis=0).reshape((1, -1))
        plot_data = plot_data[self.mainWindow.cell_subsample_i[self.cell][channel], :]

        if self.index not in self.channel_plot_lines.keys():
            self.channel_plot_lines[self.index] = {
                channel: MultiLine(np.tile(np.arange(self.samples_per_spike), (plot_data.shape[0], 1)),
                                   plot_data, pen_color=get_channel_color(self.cell))}
        else:
            if channel in self.channel_plot_lines[self.index].keys():
                self.channel_plot.removeItem(self.channel_plot_lines[self.index][channel])

            self.channel_plot_lines[self.index][channel] = MultiLine(np.tile(np.arange(self.samples_per_spike),
                                                                (plot_data.shape[0], 1)), plot_data,
                                                        pen_color=get_channel_color(self.cell))

        if self.index not in self.channel_avg_plot_lines.keys():
            self.channel_avg_plot_lines[self.index] = {channel: MultiLine(np.arange(self.samples_per_spike).reshape((1, -1)),
                                                             plot_data_avg, pen_color='w', pen_width=2)}
        else:
            if channel in self.channel_avg_plot_lines[self.index].keys():
                self.channel_plot.removeItem(self.channel_avg_plot_lines[self.index][channel])

            self.channel_avg_plot_lines[self.index][channel] = MultiLine(np.arange(self.samples_per_spike).reshape((1, -1)),
                                                            plot_data_avg, pen_color='w', pen_width=2)

        ymin, ymax = get_ylimits(channel, channel_range=channel_range, n_channels=self.n_channels)

        self.channel_plot.addItem(self.channel_plot_lines[self.index][channel])
        self.channel_plot.addItem(self.channel_avg_plot_lines[self.index][channel])

        self.channel_plot.setYRange(ymin, ymax, padding=0)

    def reset_plots(self):
        self.unit_plot.clear()
        self.unit_plot.setTitle('')
        self.channel_plot.clear()

    def reset_data(self):

        self.reset_plots()

        self.cell = None
        self.index = None

        self.unit_drag_lines = None
        self.channel_drag_lines = None

        self.drag_active = False

        self.active_ROI = []
        self.plot_lines = {}
        self.avg_plot_lines = {}

        self.channel_avg_plot_lines = {}
        self.channel_plot_lines = {}

    def isPopup(self):
        return True


def get_ylimits(channel, channel_range=256, n_channels=4):
    edges = get_channel_y_edges(channel_range=channel_range, n_channels=n_channels)
    return edges[channel+1], edges[channel]


def dragPopup(self, mode, vb, ev=None):
    # global vb, lr
    if ev.button() == QtCore.Qt.LeftButton:

        # defining the start of the selected region
        points = [[vb.mapToView(ev.buttonDownPos()).x(),
                   vb.mapToView(ev.buttonDownPos()).y()],
                  [vb.mapToView(ev.pos()).x(),
                   vb.mapToView(ev.pos()).y()]]

        if mode == 'unit':
            self.unit_plot.removeItem(self.unit_drag_lines)
            self.unit_drag_lines = pg.PolyLineROI(points)
            self.unit_plot.addItem(self.unit_drag_lines)
            self.active_ROI = [self.unit_drag_lines]
            self.drag_active = True
        elif mode == 'channel':
            self.channel_plot.removeItem(self.channel_drag_lines)
            self.channel_drag_lines = pg.PolyLineROI(points)
            self.channel_plot.addItem(self.channel_drag_lines)
            self.active_ROI = [self.channel_drag_lines]
            self.drag_active = True

        ev.accept()
    else:
        pg.ViewBox.mouseDragEvent(vb, ev)


def mouse_click_eventPopup(self, vb, ev=None):

    if ev.button() == QtCore.Qt.RightButton:
        # open menu
        pg.ViewBox.mouseClickEvent(vb, ev)

    elif ev.button() == QtCore.Qt.LeftButton:

        # hopefully drag event
        pg.ViewBox.mouseClickEvent(vb, ev)

    elif ev.button() == QtCore.Qt.MiddleButton:
        # then we will accept the changes

        # perform the cut on the cell
        cut_cell(self, self.index)
