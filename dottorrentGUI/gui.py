#!/usr/bin/env python3

import json
import os
import sys
from datetime import datetime
from fnmatch import fnmatch

import dottorrent
import humanfriendly
from PyQt5 import QtCore, QtGui, QtWidgets

from dottorrentGUI import Ui_AboutDialog, Ui_MainWindow, __version__


PROGRAM_NAME = "dottorrent-gui-dev"
PROGRAM_NAME_VERSION = "{} {}".format(PROGRAM_NAME, __version__)
CREATOR = ""

PIECE_SIZES = [None] + [2 ** i for i in range(14, 27)]

if getattr(sys, 'frozen', False):
    _basedir = sys._MEIPASS
else:
    _basedir = os.path.dirname(__file__)


class CreateTorrentQThread(QtCore.QThread):

    progress_update = QtCore.pyqtSignal(str, int, int)
    onError = QtCore.pyqtSignal(str)

    def __init__(self, torrent, save_path):
        super().__init__()
        self.torrent = torrent
        self.save_path = save_path

    def run(self):
        def progress_callback(*args):
            self.progress_update.emit(*args)
            return self.isInterruptionRequested()

        self.torrent.creation_date = datetime.now()
        try:
            self.success = self.torrent.generate(callback=progress_callback)
        except Exception as exc:
            self.onError.emit(str(exc))
            return
        if self.success:
            with open(self.save_path, 'wb') as f:
                self.torrent.save(f)


class CreateTorrentBatchQThread(QtCore.QThread):

    progress_update = QtCore.pyqtSignal(str, int, int)
    onError = QtCore.pyqtSignal(str)

    def __init__(self, path, exclude, save_dir, trackers, web_seeds,
                 private, source, comment, include_md5):
        super().__init__()
        self.path = path
        self.exclude = exclude
        self.save_dir = save_dir
        self.trackers = trackers
        self.web_seeds = web_seeds
        self.private = private
        self.source = source
        self.comment = comment
        self.include_md5 = include_md5

    def run(self):
        def callback(*args):
            return self.isInterruptionRequested()

        entries = os.listdir(self.path)
        for i, p in enumerate(entries):
            if any(fnmatch(p, ex) for ex in self.exclude):
                continue
            p = os.path.join(self.path, p)
            if not dottorrent.is_hidden_file(p):
                sfn = os.path.split(p)[1] + '.torrent'
                self.progress_update.emit(sfn, i, len(entries))
                t = dottorrent.Torrent(
                    p,
                    exclude=self.exclude,
                    trackers=self.trackers,
                    web_seeds=self.web_seeds,
                    private=self.private,
                    source=self.source,
                    comment=self.comment,
                    include_md5=self.include_md5,
                    creation_date=datetime.now()
                )
                try:
                    self.success = t.generate(callback=callback)
                # ignore empty inputs
                except dottorrent.exceptions.EmptyInputException:
                    continue
                except Exception as exc:
                    self.onError.emit(str(exc))
                    return
                if self.isInterruptionRequested():
                    return
                if self.success:
                    with open(os.path.join(self.save_dir, sfn), 'wb') as f:
                        t.save(f)


class DottorrentGUI(Ui_MainWindow):

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)

        self.torrent = None
        self.MainWindow = MainWindow
        self.current_profile = None

        self.actionImportProfile.triggered.connect(self.import_profile)
        self.actionExportProfile.triggered.connect(self.export_profile)
        self.actionAbout.triggered.connect(self.showAboutDialog)
        self.actionQuit.triggered.connect(self.MainWindow.close)

        # Profile management
        self.saveProfileButton.clicked.connect(self.save_profile)
        self.deleteProfileButton.clicked.connect(self.delete_profile)
        self.profileComboBox.currentIndexChanged.connect(self.profile_changed)

        self.fileRadioButton.toggled.connect(self.inputModeToggle)
        self.fileRadioButton.setChecked(True)
        self.directoryRadioButton.toggled.connect(self.inputModeToggle)

        self.browseButton.clicked.connect(self.browseInput)
        self.batchModeCheckBox.stateChanged.connect(self.batchModeChanged)

        self.inputEdit.dragEnterEvent = self.inputDragEnterEvent
        self.inputEdit.dropEvent = self.inputDropEvent
        self.pasteButton.clicked.connect(self.pasteInput)
        self.validateButton.clicked.connect(self.validateInput)

        self.outputBrowseButton.clicked.connect(self.browseOutput)

        self.pieceCountLabel.hide()
        self.pieceSizeComboBox.addItem('Auto')
        for x in PIECE_SIZES[1:]:
            self.pieceSizeComboBox.addItem(
                humanfriendly.format_size(x, binary=True))

        self.pieceSizeComboBox.currentIndexChanged.connect(
            self.pieceSizeChanged)

        self.privateTorrentCheckBox.stateChanged.connect(
            self.privateTorrentChanged)

        self.commentEdit.textEdited.connect(
            self.commentEdited)

        self.sourceEdit.textEdited.connect(
            self.sourceEdited)

        self.md5CheckBox.stateChanged.connect(
            self.md5Changed)

        self.progressBar.hide()
        self.createButton.setEnabled(False)
        self.createButton.clicked.connect(self.createButtonClicked)
        self.cancelButton.hide()
        self.cancelButton.clicked.connect(self.cancel_creation)
        self.resetButton.clicked.connect(self.reset)

        self.load_available_profiles()
        self._statusBarMsg('Ready')

    def getSettings(self):
        portable_fn = PROGRAM_NAME + '.ini'
        portable_fn = os.path.join(_basedir, portable_fn)
        if os.path.exists(portable_fn):
            return QtCore.QSettings(
                portable_fn,
                QtCore.QSettings.IniFormat
            )
        return QtCore.QSettings(
            QtCore.QSettings.IniFormat,
            QtCore.QSettings.UserScope,
            PROGRAM_NAME,
            PROGRAM_NAME
        )

    def loadSettings(self):
        settings = self.getSettings()
        if settings.value('input/mode') == 'directory':
            self.directoryRadioButton.setChecked(True)
        batch_mode = bool(int(settings.value('input/batch_mode') or 0))
        self.batchModeCheckBox.setChecked(batch_mode)
        exclude = settings.value('input/exclude')
        if exclude:
            self.excludeEdit.setPlainText(exclude)
        trackers = settings.value('seeding/trackers')
        if trackers:
            self.trackerEdit.setPlainText(trackers)
        web_seeds = settings.value('seeding/web_seeds')
        if web_seeds:
            self.webSeedEdit.setPlainText(web_seeds)
        private = bool(int(settings.value('options/private') or 0))
        self.privateTorrentCheckBox.setChecked(private)
        source = settings.value('options/source')
        if source:
            self.sourceEdit.setText(source)
        compute_md5 = bool(int(settings.value('options/compute_md5') or 0))
        if compute_md5:
            self.md5CheckBox.setChecked(compute_md5)
        mainwindow_size = settings.value("geometry/size")
        if mainwindow_size:
            self.MainWindow.resize(mainwindow_size)
        mainwindow_position = settings.value("geometry/position")
        if mainwindow_position:
            self.MainWindow.move(mainwindow_position)
        self.last_input_dir = settings.value('history/last_input_dir') or None
        self.last_output_dir = settings.value(
            'history/last_output_dir') or None
        output_path = settings.value('output/path')
        if output_path:
            self.outputEdit.setText(output_path)
        output_path = settings.value('output/path')
        if output_path:
            self.outputEdit.setText(output_path)
        
        # Load last used profile
        last_profile = settings.value('profile/last_profile')
        if last_profile:
            index = self.profileComboBox.findText(last_profile)
            if index >= 0:
                self.profileComboBox.setCurrentIndex(index)
                self.load_profile_data(last_profile)

    def saveSettings(self):
        settings = self.getSettings()
        settings.setValue('input/mode', self.inputMode)
        settings.setValue('input/batch_mode', int(self.batchModeCheckBox.isChecked()))
        settings.setValue('input/exclude', self.excludeEdit.toPlainText())
        settings.setValue('seeding/trackers', self.trackerEdit.toPlainText())
        settings.setValue('seeding/web_seeds', self.webSeedEdit.toPlainText())
        settings.setValue('options/private',
                          int(self.privateTorrentCheckBox.isChecked()))
        settings.setValue('options/source', self.sourceEdit.text())
        settings.setValue('options/compute_md5', int(self.md5CheckBox.isChecked()))
        settings.setValue('output/path', self.outputEdit.text())
        settings.setValue('geometry/size', self.MainWindow.size())
        settings.setValue('geometry/position', self.MainWindow.pos())
        if self.last_input_dir:
            settings.setValue('history/last_input_dir', self.last_input_dir)
        if self.last_output_dir:
            settings.setValue('history/last_output_dir', self.last_output_dir)
        
        # Save last used profile
        if self.current_profile:
            settings.setValue('profile/last_profile', self.current_profile)

    def _statusBarMsg(self, msg):
        self.MainWindow.statusBar().showMessage(msg)

    def _showError(self, msg):
        errdlg = QtWidgets.QErrorMessage()
        errdlg.setWindowTitle('Error')
        errdlg.showMessage(msg)
        errdlg.exec_()

    def showAboutDialog(self):
        qdlg = QtWidgets.QDialog()
        ad = Ui_AboutDialog()
        ad.setupUi(qdlg)
        ad.programVersionLabel.setText("version {}".format(__version__))
        ad.dtVersionLabel.setText("(dottorrent {})".format(
            dottorrent.__version__))
        qdlg.exec_()

    def inputModeToggle(self):
        if self.fileRadioButton.isChecked():
            self.inputMode = 'file'
            self.batchModeCheckBox.setEnabled(False)
            self.batchModeCheckBox.hide()
        else:
            self.inputMode = 'directory'
            self.batchModeCheckBox.setEnabled(True)
            self.batchModeCheckBox.show()
        self.inputEdit.setText('')

    def browseInput(self):
        qfd = QtWidgets.QFileDialog(self.MainWindow)
        if self.last_input_dir and os.path.exists(self.last_input_dir):
            qfd.setDirectory(self.last_input_dir)
        if self.inputMode == 'file':
            qfd.setWindowTitle('Select file')
            qfd.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        else:
            qfd.setWindowTitle('Select directory')
            qfd.setFileMode(QtWidgets.QFileDialog.Directory)
        if qfd.exec_():
            fn = qfd.selectedFiles()[0]
            self.inputEdit.setText(fn)
            self.last_input_dir = os.path.split(fn)[0]
            self.initializeTorrent()

    def browseOutput(self):
        initial_dir = self.outputEdit.text() or self.last_output_dir or ''
        output_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self.MainWindow, 'Select output directory', initial_dir)
        if output_dir:
            self.outputEdit.setText(output_dir)
            self.last_output_dir = output_dir

    def injectInputPath(self, path):
        if os.path.exists(path):
            if os.path.isfile(path):
                self.fileRadioButton.setChecked(True)
                self.inputMode = 'file'
                self.batchModeCheckBox.setCheckState(QtCore.Qt.Unchecked)
                self.batchModeCheckBox.setEnabled(False)
                self.batchModeCheckBox.hide()
            else:
                self.directoryRadioButton.setChecked(True)
                self.inputMode = 'directory'
                self.batchModeCheckBox.setEnabled(True)
                self.batchModeCheckBox.show()
            self.inputEdit.setText(path)
            self.last_input_dir = os.path.split(path)[0]
            self.initializeTorrent()

    def validateInput(self):
        path = self.inputEdit.text().strip()
        if path:
            self.injectInputPath(path)

    def inputDragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].isLocalFile():
                event.accept()
                return
        event.ignore()

    def inputDropEvent(self, event):
        path = event.mimeData().urls()[0].toLocalFile()
        self.injectInputPath(path)

    def pasteInput(self):
        mimeData = self.clipboard().mimeData()
        if mimeData.hasText():
            path = mimeData.text().strip("'\"")
            self.injectInputPath(path)

    def batchModeChanged(self, state):
        if state == QtCore.Qt.Checked:
            self.pieceSizeComboBox.setCurrentIndex(0)
            self.pieceSizeComboBox.setEnabled(False)
            self.pieceCountLabel.hide()
        else:
            self.pieceSizeComboBox.setEnabled(True)
            if self.torrent:
                self.pieceCountLabel.show()

    def initializeTorrent(self):
        self.torrent = dottorrent.Torrent(self.inputEdit.text())
        try:
            t_info = self.torrent.get_info()
        except Exception as e:
            self.torrent = None
            self._showError(str(e))
            return
        ptail = os.path.split(self.torrent.path)[1]
        if self.inputMode == 'file':
            self._statusBarMsg(
                "{}: {}".format(ptail, humanfriendly.format_size(
                    t_info[0], binary=True)))
        else:
            self._statusBarMsg(
                "{}: {} files, {}".format(
                    ptail, t_info[1], humanfriendly.format_size(
                        t_info[0], binary=True)))
        self.pieceSizeComboBox.setCurrentIndex(0)
        self.updatePieceCountLabel(t_info[2], t_info[3])
        self.pieceCountLabel.show()
        self.createButton.setEnabled(True)

    def commentEdited(self, comment):
        if getattr(self, 'torrent', None):
            self.torrent.comment = comment

    def sourceEdited(self, source):
        if getattr(self, 'torrent', None):
            self.torrent.source = source

    def pieceSizeChanged(self, index):
        if getattr(self, 'torrent', None):
            self.torrent.piece_size = PIECE_SIZES[index]
            t_info = self.torrent.get_info()
            self.updatePieceCountLabel(t_info[2], t_info[3])

    def updatePieceCountLabel(self, ps, pc):
        ps = humanfriendly.format_size(ps, binary=True)
        self.pieceCountLabel.setText("{} pieces @ {} each".format(pc, ps))

    def privateTorrentChanged(self, state):
        if getattr(self, 'torrent', None):
            self.torrent.private = (state == QtCore.Qt.Checked)

    def md5Changed(self, state):
        if getattr(self, 'torrent', None):
            self.torrent.include_md5 = (state == QtCore.Qt.Checked)

    def createButtonClicked(self):
        self.torrent.exclude = self.excludeEdit.toPlainText().strip().splitlines()
        # Validate trackers and web seed URLs
        trackers = self.trackerEdit.toPlainText().strip().split()
        web_seeds = self.webSeedEdit.toPlainText().strip().split()
        try:
            self.torrent.trackers = trackers
            self.torrent.web_seeds = web_seeds
        except Exception as e:
            self._showError(str(e))
            return
        self.torrent.private = self.privateTorrentCheckBox.isChecked()
        self.torrent.comment = self.commentEdit.text() or None
        self.torrent.source = self.sourceEdit.text() or None
        self.torrent.include_md5 = self.md5CheckBox.isChecked()
        if self.inputMode == 'directory' and self.batchModeCheckBox.isChecked():
            self.createTorrentBatch()
        else:
            self.createTorrent()

    def createTorrent(self):
        if os.path.isfile(self.inputEdit.text()):
            save_fn = os.path.splitext(
                os.path.split(self.inputEdit.text())[1])[0] + '.torrent'
        else:
            save_fn = self.inputEdit.text().split(os.sep)[-1] + '.torrent'
        
        # Use output path if set and skip dialog
        output_dir = self.outputEdit.text()
        if output_dir and os.path.exists(output_dir):
            fn = os.path.join(output_dir, save_fn)
        else:
            # Show dialog if no output path is set
            default_dir = self.last_output_dir
            if default_dir and os.path.exists(default_dir):
                save_fn = os.path.join(default_dir, save_fn)
            fn = QtWidgets.QFileDialog.getSaveFileName(
                self.MainWindow, 'Save torrent', save_fn,
                filter=('Torrent file (*.torrent)'))[0]
        
        if fn:
            self.last_output_dir = os.path.split(fn)[0]
            self.creation_thread = CreateTorrentQThread(
                self.torrent,
                fn)
            self.creation_thread.started.connect(
                self.creation_started)
            self.creation_thread.progress_update.connect(
                self._progress_update)
            self.creation_thread.finished.connect(
                self.creation_finished)
            self.creation_thread.onError.connect(
                self._showError)
            self.creation_thread.start()

    def createTorrentBatch(self):
        # Use output path if set, otherwise prompt for directory
        output_dir = self.outputEdit.text()
        if not output_dir or not os.path.exists(output_dir):
            save_dir = QtWidgets.QFileDialog.getExistingDirectory(
                self.MainWindow, 'Select output directory', self.last_output_dir)
        else:
            save_dir = output_dir
        
        if save_dir:
            self.last_output_dir = save_dir
            trackers = self.trackerEdit.toPlainText().strip().split()
            web_seeds = self.webSeedEdit.toPlainText().strip().split()
            self.creation_thread = CreateTorrentBatchQThread(
                path=self.inputEdit.text(),
                exclude=self.excludeEdit.toPlainText().strip().splitlines(),
                save_dir=save_dir,
                trackers=trackers,
                web_seeds=web_seeds,
                private=self.privateTorrentCheckBox.isChecked(),
                source=self.sourceEdit.text(),
                comment=self.commentEdit.text(),
                include_md5=self.md5CheckBox.isChecked(),
            )
            self.creation_thread.started.connect(
                self.creation_started)
            self.creation_thread.progress_update.connect(
                self._progress_update_batch)
            self.creation_thread.finished.connect(
                self.creation_finished)
            self.creation_thread.onError.connect(
                self._showError)
            self.creation_thread.start()

    def cancel_creation(self):
        self.creation_thread.requestInterruption()

    def _progress_update(self, fn, pc, pt):
        fn = os.path.split(fn)[1]
        msg = "{} ({}/{})".format(fn, pc, pt)
        self.updateProgress(msg, int(round(100 * pc / pt)))

    def _progress_update_batch(self, fn, tc, tt):
        msg = "({}/{}) {}".format(tc, tt, fn)
        self.updateProgress(msg, int(round(100 * tc / tt)))

    def updateProgress(self, statusMsg, pv):
        self._statusBarMsg(statusMsg)
        self.progressBar.setValue(pv)

    def creation_started(self):
        self.inputGroupBox.setEnabled(False)
        self.outputGroupBox.setEnabled(False)
        self.seedingGroupBox.setEnabled(False)
        self.optionGroupBox.setEnabled(False)
        self.progressBar.show()
        self.createButton.hide()
        self.cancelButton.show()
        self.resetButton.setEnabled(False)

    def creation_finished(self):
        self.inputGroupBox.setEnabled(True)
        self.outputGroupBox.setEnabled(True)
        self.seedingGroupBox.setEnabled(True)
        self.optionGroupBox.setEnabled(True)
        self.progressBar.hide()
        self.createButton.show()
        self.cancelButton.hide()
        self.resetButton.setEnabled(True)
        if self.creation_thread.success:
            self._statusBarMsg('Finished')
        else:
            self._statusBarMsg('Canceled')
        self.creation_thread = None

    def export_profile(self):

        fn = QtWidgets.QFileDialog.getSaveFileName(
            self.MainWindow, 'Save profile', self.last_output_dir,
            filter=('JSON configuration file (*.json)'))[0]
        if fn:
            exclude = self.excludeEdit.toPlainText().strip().splitlines()
            trackers = self.trackerEdit.toPlainText().strip().split()
            web_seeds = self.webSeedEdit.toPlainText().strip().split()
            private = self.privateTorrentCheckBox.isChecked()
            compute_md5 = self.md5CheckBox.isChecked()
            source = self.sourceEdit.text()
            data = {
                'exclude': exclude,
                'trackers': trackers,
                'web_seeds': web_seeds,
                'private': private,
                'compute_md5': compute_md5,
                'source': source
            }
            with open(fn, 'w') as f:
                json.dump(data, f, indent=4, sort_keys=True)
            self._statusBarMsg("Profile saved to " + fn)

    def import_profile(self):
        fn = QtWidgets.QFileDialog.getOpenFileName(
            self.MainWindow, 'Open profile', self.last_input_dir,
            filter=('JSON configuration file (*.json)'))[0]
        if fn:
            with open(fn) as f:
                data = json.load(f)
            exclude = data.get('exclude', [])
            trackers = data.get('trackers', [])
            web_seeds = data.get('web_seeds', [])
            private = data.get('private', False)
            compute_md5 = data.get('compute_md5', False)
            source = data.get('source', '')
            try:
                self.excludeEdit.setPlainText(os.linesep.join(exclude))
                self.trackerEdit.setPlainText(os.linesep.join(trackers))
                self.webSeedEdit.setPlainText(os.linesep.join(web_seeds))
                self.privateTorrentCheckBox.setChecked(private)
                self.md5CheckBox.setChecked(compute_md5)
                self.sourceEdit.setText(source)
            except Exception as e:
                self._showError(str(e))
                return
            self._statusBarMsg("Profile {} loaded".format(
                os.path.split(fn)[1]))

    def reset(self):
        self._statusBarMsg('')
        self.createButton.setEnabled(False)
        self.fileRadioButton.setChecked(True)
        self.batchModeCheckBox.setChecked(False)
        self.inputEdit.setText(None)
        self.outputEdit.setText(None)
        self.excludeEdit.setPlainText(None)
        self.trackerEdit.setPlainText(None)
        self.webSeedEdit.setPlainText(None)
        self.pieceSizeComboBox.setCurrentIndex(0)
        self.pieceCountLabel.hide()
        self.commentEdit.setText(None)
        self.privateTorrentCheckBox.setChecked(False)
        self.md5CheckBox.setChecked(False)
        self.sourceEdit.setText(None)
        self.torrent = None
        self._statusBarMsg('Ready')

    def load_available_profiles(self):
        """Load list of saved profiles into the combo box"""
        settings = self.getSettings()
        settings.beginGroup('profiles')
        profile_names = settings.childGroups()
        settings.endGroup()
        
        self.profileComboBox.clear()
        self.profileComboBox.addItem('')  # Empty profile option
        self.profileComboBox.addItems(sorted(profile_names))

    def get_current_profile_data(self):
        """Get current settings as profile data"""
        return {
            'exclude': self.excludeEdit.toPlainText().strip(),
            'trackers': self.trackerEdit.toPlainText().strip(),
            'web_seeds': self.webSeedEdit.toPlainText().strip(),
            'private': self.privateTorrentCheckBox.isChecked(),
            'compute_md5': self.md5CheckBox.isChecked(),
            'source': self.sourceEdit.text(),
            'output_path': self.outputEdit.text(),
            'piece_size': self.pieceSizeComboBox.currentIndex(),
            'comment': self.commentEdit.text()
        }

    def save_profile(self):
        """Save current settings to a profile"""
        profile_name = self.profileComboBox.currentText().strip()
        
        # If no profile is selected (empty), show dialog to enter name
        if not profile_name:
            profile_name, ok = QtWidgets.QInputDialog.getText(
                self.MainWindow,
                'New Profile',
                'Enter profile name:'
            )
            profile_name = profile_name.strip()
            
            if not ok or not profile_name:
                return
        
        # Ask for confirmation if profile already exists
        settings = self.getSettings()
        settings.beginGroup('profiles')
        profile_exists = profile_name in settings.childGroups()
        settings.endGroup()
        
        if profile_exists:
            reply = QtWidgets.QMessageBox.question(
                self.MainWindow,
                'Overwrite Profile',
                f'Profile "{profile_name}" already exists. Overwrite?',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.No:
                return
        
        # Save profile data
        profile_data = self.get_current_profile_data()
        settings.beginGroup(f'profiles/{profile_name}')
        for key, value in profile_data.items():
            settings.setValue(key, value)
        settings.endGroup()
        
        self.current_profile = profile_name
        self.load_available_profiles()
        
        # Set the combo box to the saved profile
        index = self.profileComboBox.findText(profile_name)
        if index >= 0:
            self.profileComboBox.setCurrentIndex(index)
        
        self._statusBarMsg(f'Profile "{profile_name}" saved')

    def load_profile_data(self, profile_name):
        """Load profile data by name"""
        settings = self.getSettings()
        settings.beginGroup(f'profiles/{profile_name}')
        
        exclude = settings.value('exclude', '')
        trackers = settings.value('trackers', '')
        web_seeds = settings.value('web_seeds', '')
        
        # Handle both boolean string values and integer values
        private_val = settings.value('private', 0)
        if isinstance(private_val, str):
            private = private_val.lower() == 'true'
        else:
            private = bool(int(private_val or 0))
        
        compute_md5_val = settings.value('compute_md5', 0)
        if isinstance(compute_md5_val, str):
            compute_md5 = compute_md5_val.lower() == 'true'
        else:
            compute_md5 = bool(int(compute_md5_val or 0))
        
        source = settings.value('source', '')
        output_path = settings.value('output_path', '')
        piece_size = int(settings.value('piece_size', 0) or 0)
        comment = settings.value('comment', '')
        
        settings.endGroup()
        
        # Apply settings
        self.excludeEdit.setPlainText(exclude)
        self.trackerEdit.setPlainText(trackers)
        self.webSeedEdit.setPlainText(web_seeds)
        self.privateTorrentCheckBox.setChecked(private)
        self.md5CheckBox.setChecked(compute_md5)
        self.sourceEdit.setText(source)
        self.outputEdit.setText(output_path)
        self.pieceSizeComboBox.setCurrentIndex(piece_size)
        self.commentEdit.setText(comment)
        
        self.current_profile = profile_name

    def delete_profile(self):
        """Delete the selected profile"""
        profile_name = self.profileComboBox.currentText().strip()
        
        if not profile_name:
            QtWidgets.QMessageBox.warning(
                self.MainWindow,
                'No Profile Selected',
                'Please select a profile to delete.'
            )
            return
        
        reply = QtWidgets.QMessageBox.question(
            self.MainWindow,
            'Delete Profile',
            f'Are you sure you want to delete profile "{profile_name}"?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            settings = self.getSettings()
            settings.beginGroup('profiles')
            settings.remove(profile_name)
            settings.endGroup()
            
            self.current_profile = None
            self.load_available_profiles()
            self.profileComboBox.setCurrentIndex(0)  # Set to empty
            self._statusBarMsg(f'Profile "{profile_name}" deleted')

    def profile_changed(self, index):
        """Handle profile selection change"""
        # Only auto-load if not the empty option
        if index > 0:
            profile_name = self.profileComboBox.currentText().strip()
            if profile_name:
                self.load_profile_data(profile_name)


def apply_dark_theme(app):
    """Apply dark theme to the application"""
    # Set dark palette
    dark_palette = QtGui.QPalette()
    dark_palette.setColor(QtGui.QPalette.Window, QtGui.QColor(53, 53, 53))
    dark_palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.Base, QtGui.QColor(35, 35, 35))
    dark_palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(53, 53, 53))
    dark_palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(25, 25, 25))
    dark_palette.setColor(QtGui.QPalette.ToolTipText, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.Text, QtCore.Qt.white)
    dark_palette.setColor(QtGui.QPalette.Button, QtGui.QColor(25, 25, 25))
    dark_palette.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.black)
    dark_palette.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)
    dark_palette.setColor(QtGui.QPalette.Link, QtGui.QColor(42, 130, 218))
    dark_palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(42, 130, 218))
    dark_palette.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.black)
    
    # Disabled colors
    dark_palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor(127, 127, 127))
    dark_palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor(127, 127, 127))
    dark_palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(127, 127, 127))
    dark_palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Highlight, QtGui.QColor(80, 80, 80))
    dark_palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.HighlightedText, QtCore.Qt.darkGray)
    
    app.setPalette(dark_palette)
    
    # Additional stylesheet for better dark theme support
    app.setStyleSheet("""
        QToolTip {
            color: #ffffff;
            background-color: #2a2a2a;
            border: 1px solid #767676;
        }
        QLineEdit, QTextEdit, QPlainTextEdit {
            background-color: #232323;
            color: #ffffff;
            border: 1px solid #767676;
            padding: 2px;
        }
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {
            background-color: #505050;
            color: #7f7f7f;
        }
        QComboBox {
            background-color: #232323;
            color: #ffffff;
            border: 1px solid #767676;
            padding: 3px;
        }
        QComboBox:disabled {
            background-color: #505050;
            color: #7f7f7f;
        }
        QComboBox::drop-down {
            border: none;
        }
        QComboBox QAbstractItemView {
            background-color: #353535;
            color: #ffffff;
            selection-background-color: #767676;
        }
        QProgressBar {
            border: 1px solid #767676;
            background-color: #232323;
            text-align: center;
            color: #ffffff;
        }
        QProgressBar::chunk {
            background-color: #19a819;
        }
        QGroupBox {
            border: 1px solid #767676;
            margin-top: 8px;
            padding-top: 4px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 3px 0 3px;
            color: #ffffff;
        }
        QScrollArea {
            border: none;
        }
        QMenuBar {
            background-color: #353535;
            color: #ffffff;
        }
        QMenuBar::item:selected {
            background-color: #767676;
        }
        QMenu {
            background-color: #353535;
            color: #ffffff;
            border: 1px solid #767676;
        }
        QMenu::item:selected {
            background-color: #767676;
        }
    """)


def main():
    app = QtWidgets.QApplication(sys.argv)
    
    # Apply dark theme
    apply_dark_theme(app)
    
    MainWindow = QtWidgets.QMainWindow()
    ui = DottorrentGUI()
    ui.setupUi(MainWindow)

    MainWindow.setWindowTitle(PROGRAM_NAME_VERSION)

    ui.loadSettings()
    ui.clipboard = app.clipboard
    app.aboutToQuit.connect(lambda: ui.saveSettings())
    MainWindow.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
