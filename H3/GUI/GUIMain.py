__author__ = 'Man'

import sys
import logging

from PySide import QtGui, QtCore, QtUiTools

from H3.core.AlchemyCore import H3AlchemyCore

H3Core = H3AlchemyCore()

logger = logging.getLogger(__name__)

class SetupWizard(QtGui.QWidget):
    """
    This is the end-user first connection interface.
    NOT for creating a new authorized user.
    It should adapt to Mac and Linux environments gracefully.
    """

    def __init__(self, parent):
        super(SetupWizard, self).__init__(parent)

        self.local_ok = False
        self.remote_ok = False
        self.user_ok = False
        self.pw_ok = False

        loader = QtUiTools.QUiLoader()
        loader.registerCustomWidget(ServerWizardPage)
        loader.registerCustomWidget(LoginWizardPage)
        loader.registerCustomWidget(RecapWizardPage)
        self.wizard = loader.load(QtCore.QFile("H3/GUI/QtDesigns/Wizard.ui"), self)

        logo_template = QtGui.QPixmap(":/images/H3wizardlogo.png")
        self.wizard.setPixmap(QtGui.QWizard.LogoPixmap, logo_template)
        bg_template = QtGui.QPixmap(":/images/H3wizardbg.png")
        self.wizard.setPixmap(QtGui.QWizard.BackgroundPixmap, bg_template)

        if H3Core.local_db:
            self.wizard.localAddress.setText(H3Core.local_db.location)
            self.local_ok = True

        if H3Core.remote_db:
            self.wizard.remoteAddress.setText(H3Core.remote_db.location)
            self.remote_ok = True

        if H3Core.current_user:
            self.wizard.usernameLineEdit.setText(H3Core.current_user.login)
            self.user_ok = True

        self.wizard.browseButton.clicked.connect(self.browse)

        self.wizard.localAddress.textChanged.connect(self.check_local)
        self.wizard.remoteAddress.textChanged.connect(self.invalidate_remote)
        self.wizard.connectButton.clicked.connect(self.check_remote)

        self.wizard.usernameLineEdit.textChanged.connect(self.invalidate_user)
        self.wizard.searchButton.clicked.connect(self.check_user)

        self.wizard.accepted.connect(self.update_files)

        if (self.wizard.exec_() == QtGui.QDialog.Rejected
           and not H3Core.ready()):
            sys.exit()

    def update_files(self):
        # TODO: should have some kind of progress bar / animation
        username = self.wizard.usernameLineEdit.text()
        password = self.wizard.passwordLineEdit.text()
        H3Core.remote_login(username, password)
        H3Core.download_user_tables()
        H3Core.download_base_tables()

    def check_user(self):
        username = self.wizard.usernameLineEdit.text()
        temp_user_ok = self.user_ok
        H3Core.find_user(username)
        if H3Core.user_state == "local":
            self.wizard.userStatusLabel.setText(_("User {login} already recorded locally, you can proceed !")
                                                .format(login=username))
            temp_user_ok = True
            self.pw_ok = True
            self.wizard.wizardPage3.completeChanged.emit()
        elif H3Core.user_state == "remote" or H3Core.user_state == "new_base":
            self.wizard.passwordLineEdit.show()
            self.wizard.passwordLabel.show()
            self.wizard.passwordLineEdit.textChanged.connect(self.check_pws)
            self.wizard.userStatusLabel.setText(_("User {login} found in remote, please enter password")
                                                .format(login=username))
            temp_user_ok = True
        elif H3Core.user_state == "new":
            self.wizard.passwordLineEdit.show()
            self.wizard.passwordLabel.show()
            self.wizard.confirmPasswordLineEdit.show()
            self.wizard.confirmPasswordLabel.show()
            self.wizard.passwordLineEdit.textChanged.connect(self.check_pws)
            self.wizard.confirmPasswordLineEdit.textChanged.connect(self.check_pws)
            self.wizard.userStatusLabel.setText(_("User {login} ready for creation, please enter password")
                                                .format(login=username))
            temp_user_ok = True
        elif H3Core.user_state == "no_job":
            temp_user_ok = False
            self.wizard.userStatusLabel.setText(_("User {login} has no current contract. "
                                                  "Please contact your focal point")
                                                .format(login=username))
        else:
            temp_user_ok = False
            self.wizard.userStatusLabel.setText(_("User {login} not found. Please contact your focal point.")
                                                .format(login=username))
        if temp_user_ok != self.user_ok:
            self.user_ok = temp_user_ok
            self.wizard.wizardPage3.completeChanged.emit()

    def check_pws(self):
        temp_pw_ok = self.pw_ok
        pw1 = self.wizard.passwordLineEdit.text()
        pw2 = self.wizard.confirmPasswordLineEdit.text()
        if H3Core.user_state == "new":
            if len(pw1) > 5:
                if pw1 == pw2:
                    temp_pw_ok = True
                    self.wizard.passwordStatusLabel.setText(_("Password valid, you can proceed !"))
                else:
                    temp_pw_ok = False
                    self.wizard.passwordStatusLabel.setText(_("Passwords don't match"))
            else:
                temp_pw_ok = False
                self.wizard.passwordStatusLabel.setText(_("Password too short (minimum 6 characters)"))
        elif H3Core.user_state == "remote" or H3Core.user_state == "new_base":
            if len(pw1) > 5:
                temp_pw_ok = True
                self.wizard.passwordStatusLabel.setText(_(" "))
            else:
                temp_pw_ok = False
                self.wizard.passwordStatusLabel.setText(_("Password is at least 6 characters"))
        if temp_pw_ok != self.pw_ok:
            self.pw_ok = temp_pw_ok
            self.wizard.wizardPage3.completeChanged.emit()

    def browse(self):
        """
        Simple "Open File" dialog to choose a location for the local DB.
        """
        filename = QtGui.QFileDialog.getSaveFileName(self, _("Choose local DB file location"))
        if filename != "":
            self.wizard.localAddress.setText(filename[0])

    def check_local(self):
        """
        The logic to validate the local DB location : new, existing or file exists but not a DB ?
        """
        local_db_exists = H3Core.ping_local(self.wizard.localAddress.text())
        temp_local_ok = self.local_ok
        if local_db_exists == -1:
            self.wizard.localDBstatus.setText(_("Ready to create new local DB at {location}")
                                              .format(location=self.wizard.localAddress.text()))
            temp_local_ok = True
        elif local_db_exists == 1:
            self.wizard.localDBstatus.setText(_("{location} is a valid H3 DB")
                                              .format(location=self.wizard.localAddress.text()))
            temp_local_ok = True
        else:
            assert local_db_exists == 0
            if self.wizard.localAddress.text():
                self.wizard.localDBstatus.setText(_("{location} is not a valid location for a H3 DB")
                                                  .format(location=self.wizard.localAddress.text()))
            else:
                self.wizard.localDBstatus.setText("")
            temp_local_ok = False
        if temp_local_ok != self.local_ok:
            self.local_ok = temp_local_ok
            self.wizard.wizardPage2.completeChanged.emit()

    def check_remote(self):
        """
        Tries to get a response from a H3 remote DB
        """
        location = self.wizard.remoteAddress.text()
        if location != "":
            remote_db_exists = H3Core.ping_remote(location)
            temp_remote_ok = self.remote_ok
            if remote_db_exists == 1:
                self.wizard.remoteDBstatus.setText(_("Successfully contacted H3 DB at {location}")
                                                   .format(location=self.wizard.remoteAddress.text()))
                temp_remote_ok = True
            else:
                assert remote_db_exists == 0
                self.wizard.remoteDBstatus.setText(_("Unable to reach a H3 DB at {location}")
                                                   .format(location=self.wizard.remoteAddress.text()))
                temp_remote_ok = False
            if temp_remote_ok != self.remote_ok:
                self.remote_ok = temp_remote_ok
                self.wizard.wizardPage2.completeChanged.emit()

    def invalidate_remote(self):
        if self.remote_ok:
            self.remote_ok = False
            self.wizard.wizardPage2.completeChanged.emit()

    def invalidate_user(self):
        if self.user_ok:
            self.user_ok = False
            self.pw_ok = False
            self.wizard.wizardPage3.completeChanged.emit()

class ServerWizardPage(QtGui.QWizardPage):
    def __init__(self, parent):
        super(ServerWizardPage, self).__init__(parent)

    def isComplete(self, *args, **kwargs):
        result = self.wizard().parent().local_ok and self.wizard().parent().remote_ok
        if result:
            return True
        else:
            return False

class LoginWizardPage(QtGui.QWizardPage):
    def __init__(self, parent):
        super(LoginWizardPage, self).__init__(parent)

    def isComplete(self, *args, **kwargs):
        result = self.wizard().parent().user_ok and self.wizard().parent().pw_ok
        if result:
            return True
        else:
            return False

    def initializePage(self, *args, **kwargs):
        H3Core.setup_databases(self.wizard().localAddress.text(),
                               self.wizard().remoteAddress.text())
        self.wizard().passwordLineEdit.hide()
        self.wizard().passwordLabel.hide()
        self.wizard().confirmPasswordLineEdit.hide()
        self.wizard().confirmPasswordLabel.hide()

class RecapWizardPage(QtGui.QWizardPage):
    def __init__(self, parent):
        super(RecapWizardPage, self).__init__(parent)

    def initializePage(self, *args, **kwargs):
        self.wizard().localRecap.setText(self.wizard().localAddress.text())
        self.wizard().remoteRecap.setText(self.wizard().remoteAddress.text())

        self.wizard().nameRecap.setText(_("{first} {last}") \
                                        .format(first=H3Core.current_user.first_name,
                                                last=H3Core.current_user.last_name))

        if H3Core.user_state == "no_job":
            self.wizard().jobRecap.setText(_("No current contract"))
            self.wizard().baseRecap.setText(_("No current posting"))
            self.wizard().userActionRecap.setText(_("The user profile can not be used in H3"
                                                    " because it's not currently active"))
        else:
            self.wizard().jobRecap.setText(H3Core.current_job_contract.job_code + " - "
                                           + H3Core.current_job_contract.job_title)
            self.wizard().baseRecap.setText(H3Core.current_job_contract.base + " - "
                                            + H3Core.base_full_name(H3Core.current_job_contract.base))

            if H3Core.user_state == "local":
                self.wizard().userActionRecap.setText(_("The user profile was already set up in the local database."
                                                        "This wizard will only update the user info."))
            elif H3Core.user_state == "remote":
                self.wizard().userActionRecap.setText(_("The user profile will be downloaded into the local database. "
                                                        "You can then login. Welcome back to H3 !"))
            elif H3Core.user_state == "new" or H3Core.user_state == "new_base":
                self.wizard().userActionRecap.setText(_("The user profile will be initialized and downloaded into the"
                                                        " local database. Welcome to H3 !"))

                message_box = QtGui.QMessageBox(QtGui.QMessageBox.Information, _("New base data needed"),
                                                _("H3 will now download the data for the office your new user is "
                                                  "affected to. If this is not a new H3 installation, "
                                                  "please consider deleting and rebuilding your local Database file, "
                                                  "or use the administrative options in H3 to remove old data."),
                                                QtGui.QMessageBox.Ok)
                message_box.setWindowIcon(QtGui.QIcon(":/images/H3.png"))
                message_box.exec_()

            H3Core.download_current_user_job_contract()


class LoginBox(QtGui.QWidget):
    """
    This is the first thing that greets the user.
    It has the logic for 5 login retries maximum.
    If local login is accepted, the main window adapts to the user.
    If not, the program exits.
    It can ask the main class to start the new user wizard.
    """

    def __init__(self, parent):
        super(LoginBox, self).__init__(parent)
        self.login_box = QtUiTools.QUiLoader().load(QtCore.QFile("H3/GUI/QtDesigns/LoginBox.ui"), self)
        self.login_attempts = 0

        if H3Core.current_user:
            self.login_box.loginLineEdit.setText(H3Core.current_user.login)

        self.login_box.pushButton.clicked.connect(self.login_clicked)
        self.login_box.new_user_pushButton.clicked.connect(self.parent().run_setup_wizard)

        if self.login_box.exec_() == QtGui.QDialog.Rejected:
            sys.exit()

    def login_clicked(self):
        if self.login_attempts < 4:
            username = self.login_box.loginLineEdit.text()
            password = self.login_box.passwordLineEdit.text()
            H3Core.local_login(username, password)
            if H3Core.user_state == "ok":
                self.login_box.accept()
                self.parent().set_status(_("Successfully logged in as %(name)s") % {"name": username})
            elif H3Core.user_state == "new_base":
                message_box = QtGui.QMessageBox(QtGui.QMessageBox.Information, _("New base data needed"),
                                                _(
                                                    "This user is currently affected to a base that is not present in the "
                                                    "local database. Maybe the user got promoted to a new base, or this is "
                                                    "H3 installation is old. Please run the setup wizard."),
                                                QtGui.QMessageBox.Ok)
                message_box.setWindowIcon(QtGui.QIcon(":/images/H3.png"))
                message_box.exec_()
            elif H3Core.user_state == "no_job":
                message_box = QtGui.QMessageBox(QtGui.QMessageBox.Information, _("No active job contract"),
                                                _(
                                                    "This user is currently not employed according to the local H3 database; "
                                                    "Please contact your focal point if this is wrong."),
                                                QtGui.QMessageBox.Ok)
                message_box.setWindowIcon(QtGui.QIcon(":/images/H3.png"))
                message_box.exec_()
            elif H3Core.user_state == "nok":
                self.login_attempts += 1
                self.parent().set_status("login failed, " + str((5 - self.login_attempts)) + " remaining")
        else:
            self.login_box.reject()


class H3MainGUI(QtGui.QWidget):
    """
    This is the main visual interface init for the program.
    It pops the Login Box by default, and handles creation of other dialogs,
    as well as switching the main window's central widget.
    """

    def __init__(self):
        super(H3MainGUI, self).__init__()
        self.load_resource_file()
        self.root_window = QtUiTools.QUiLoader().load(QtCore.QFile("H3/GUI/QtDesigns/Main.ui"), self)

        # TODO : Have Status bar watch the log file for messages (store in a tablemodel)+"local DB Accessible" indicator
        # TODO : Make main window (and others) resolution-adequate

        while not H3Core.ready():
            self.run_setup_wizard()

        self.root_window.show()

        LoginBox(self)

        self.root_window.setWindowTitle(_("{first} {last}, {job}, {base}")
                                        .format(first=H3Core.current_user.first_name,
                                                last=H3Core.current_user.last_name,
                                                job=H3Core.current_job_contract.job_title,
                                                base=H3Core.base_full_name(H3Core.current_job_contract.base)))

        actions_model = self.build_actions_menu()
        self.root_window.treeView.setModel(actions_model)
        self.root_window.treeView.expandAll()
        self.root_window.treeView.resizeColumnToContents(0)

        self.root_window.treeView.clicked.connect(self.do_something)

    def build_actions_menu(self):
        H3Core.get_actions()
        model = QtGui.QStandardItemModel()

        categories = set()
        action_items = list()

        for contract_action in H3Core.contract_actions:
            desc = H3Core.get_action_descriptions(contract_action.action)
            categories.add(desc.category)
            item = QtGui.QStandardItem(desc.description)
            item.setData(contract_action, 33)
            item.setData(desc, 34)
            action_items.append(item)

        for delegation in H3Core.delegations:
            desc = H3Core.get_action_descriptions(delegation.action)
            categories.add(desc.category)
            item = QtGui.QStandardItem(desc.description)
            item.setData(delegation, 33)
            item.setData(desc, 34)
            item.setBackground(QtGui.QBrush(QtCore.Qt.green))
            action_items.append(item)

        for cat in categories:
            cat_item = QtGui.QStandardItem(cat)
            for item in action_items:
                action = item.data(34)
                if action.category == cat:
                    cat_item.appendRow(item)
            model.appendRow(cat_item)

        return model

    @staticmethod
    def load_resource_file():
        if QtCore.QResource.registerResource("H3/GUI/QtDesigns/H3.rcc"):
            logger.debug(_("Resource file opened successfully"))
        else:
            logger.warning(_("Error loading resource file"))

    @QtCore.Slot(int)
    def do_something(self, num):
        if num.row() == 2:
            # ManageUsersScreen(self)
            pass

    def ui_switcher(self, screen='jobhome'):
        if screen == 'jobhome':
            self.ui_switcher(H3Core.current_user.job_desc)
        elif screen == 'PM':
            # PMMenu(self)
            pass
        elif screen == 'project':
            # ProjectMenu(self)
            pass
        elif screen == 'FP':
            # FPMenu(self)
            pass
        elif screen == 'LOG':
            pass
            # log_menu = QtUiTools.QUiLoader().load(QtCore.QFile("H3/GUI/QtDesigns/LogMenu.ui"))
            # self.H3_root_window.setCentralWidget(LogMenu)

    def run_setup_wizard(self):
        SetupWizard(self)

    def set_status(self, status_string):
        self.root_window.statusbar.showMessage(status_string, 2000)

def run():
    h3app = QtGui.QApplication(sys.argv)
    h3gui = H3MainGUI()
    h3app.exec_()

def init_remote(location, password):
    H3Core.init_remote(location, password)

def nuke_remote(location, password):
    H3Core.nuke_remote(location, password)
