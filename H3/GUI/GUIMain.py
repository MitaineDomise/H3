__author__ = 'Man'

import sys
import logging
import datetime

from PySide import QtGui, QtCore, QtUiTools

from H3.core.AlchemyCore import H3AlchemyCore
from H3.core import AlchemyClassDefs as Acd

H3Core = H3AlchemyCore()

logger = logging.getLogger(__name__)


class SetupWizard:
    """
    This is the end-user first connection interface.
    """

    def __init__(self, parent_h3_gui):

        self.gui = parent_h3_gui

        loader = QtUiTools.QUiLoader()
        loader.registerCustomWidget(ServerWizardPage)
        loader.registerCustomWidget(LoginWizardPage)
        loader.registerCustomWidget(RecapWizardPage)
        self.wizard = loader.load(QtCore.QFile("H3/GUI/QtDesigns/Wizard.ui"), self.gui.root_window)

        desktop_rect = self.gui.rect
        rect2 = QtCore.QRect(desktop_rect.width() * 2 / 7,
                             desktop_rect.height() * 1 / 6,
                             desktop_rect.width() * 3 / 7,
                             desktop_rect.height() * 4 / 6)
        self.wizard.setGeometry(rect2)

        logo_template = QtGui.QPixmap(":/images/H3wizardlogo.png")
        self.wizard.setPixmap(QtGui.QWizard.LogoPixmap, logo_template)
        bg_template = QtGui.QPixmap(":/images/H3wizardbg.png")
        self.wizard.setPixmap(QtGui.QWizard.BackgroundPixmap, bg_template)

        self.wizard.local_ok = False
        self.wizard.remote_ok = False
        self.wizard.user_ok = False
        self.wizard.pw_ok = False

        if H3Core.local_db:
            self.wizard.localAddress.setText(H3Core.local_db.location)
            self.wizard.check_local()

        if H3Core.remote_db:
            self.wizard.remoteAddress.setText(H3Core.remote_db.location)
            self.wizard.check_remote()

        if H3Core.current_job_contract:
            self.wizard.usernameLineEdit.setText(H3Core.current_job_contract.user)
            self.wizard.check_user()

        self.wizard.browseButton.clicked.connect(self.browse)

        self.wizard.localAddress.textChanged.connect(self.check_local)
        self.wizard.remoteAddress.textChanged.connect(self.invalidate_remote)
        self.wizard.connectButton.clicked.connect(self.check_remote)

        self.wizard.usernameLineEdit.textChanged.connect(self.invalidate_user)
        self.wizard.searchButton.clicked.connect(self.check_user)

        self.wizard.accepted.connect(H3Core.sync_down)
        # TODO: should have some kind of progress bar / animation
        if (self.wizard.exec_() == QtGui.QDialog.Rejected
           and not H3Core.ready()):
            sys.exit()

    def check_user(self):
        username = self.wizard.usernameLineEdit.text()
        temp_user_ok = self.wizard.user_ok
        H3Core.find_user(username)
        if H3Core.user_state == "local":
            self.wizard.userStatusLabel.setText(_("User {login} already recorded locally, you can proceed !")
                                                .format(login=username))
            temp_user_ok = True
            self.wizard.pw_ok = True
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
        if temp_user_ok != self.wizard.user_ok:
            self.wizard.user_ok = temp_user_ok
            self.wizard.wizardPage3.completeChanged.emit()

    def check_pws(self):
        temp_pw_ok = self.wizard.pw_ok
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
        if temp_pw_ok != self.wizard.pw_ok:
            self.wizard.pw_ok = temp_pw_ok
            self.wizard.wizardPage3.completeChanged.emit()

    def browse(self):
        """
        Simple "Open File" dialog to choose a location for the local DB.
        """
        filename = QtGui.QFileDialog.getSaveFileName(self.wizard, _("Choose local DB file location"))
        if filename != "":
            self.wizard.localAddress.setText(filename[0])

    def check_local(self):
        """
        The logic to validate the local DB location : new, existing or file exists but not a DB ?
        """
        local_db_exists = H3Core.ping_local(self.wizard.localAddress.text())
        temp_local_ok = self.wizard.local_ok
        str(temp_local_ok)  # again useless
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
        if temp_local_ok != self.wizard.local_ok:
            self.wizard.local_ok = temp_local_ok
            self.wizard.wizardPage2.completeChanged.emit()

    def check_remote(self):
        """
        Tries to get a response from a H3 remote DB
        """
        location = self.wizard.remoteAddress.text()
        if location != "":
            remote_db_exists = H3Core.ping_remote(location)
            temp_remote_ok = self.wizard.remote_ok
            str(temp_remote_ok)  # useless
            if remote_db_exists == 1:
                self.wizard.remoteDBstatus.setText(_("Successfully contacted H3 DB at {location}")
                                                   .format(location=self.wizard.remoteAddress.text()))
                temp_remote_ok = True
            else:
                assert remote_db_exists == 0
                self.wizard.remoteDBstatus.setText(_("Unable to reach a H3 DB at {location}")
                                                   .format(location=self.wizard.remoteAddress.text()))
                temp_remote_ok = False
            if temp_remote_ok != self.wizard.remote_ok:
                self.wizard.remote_ok = temp_remote_ok
                self.wizard.wizardPage2.completeChanged.emit()

    def invalidate_remote(self):
        if self.wizard.remote_ok:
            self.wizard.remote_ok = False
            self.wizard.wizardPage2.completeChanged.emit()

    def invalidate_user(self):
        if self.wizard.user_ok:
            self.wizard.user_ok = False
            self.wizard.pw_ok = False
            self.wizard.wizardPage3.completeChanged.emit()


class ServerWizardPage(QtGui.QWizardPage):
    def __init__(self, parent):
        super(ServerWizardPage, self).__init__(parent)

    def isComplete(self, *args, **kwargs):
        result = self.wizard().local_ok and self.wizard().remote_ok
        if result:
            return True
        else:
            return False


class LoginWizardPage(QtGui.QWizardPage):
    def __init__(self, parent):
        super(LoginWizardPage, self).__init__(parent)

    def isComplete(self, *args, **kwargs):
        result = self.wizard().user_ok and self.wizard().pw_ok
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
        H3Core.get_current_user_job_contract(self.wizard().usernameLineEdit.text())

        self.wizard().localRecap.setText(self.wizard().localAddress.text())
        self.wizard().remoteRecap.setText(self.wizard().remoteAddress.text())

        self.wizard().nameRecap.setText(H3Core.current_job_contract.user)

        if H3Core.user_state == "no_job":
            self.wizard().jobRecap.setText(_("No current contract"))
            self.wizard().baseRecap.setText(_("No current posting"))
            self.wizard().userActionRecap.setText(_("The user profile can not be used in H3"
                                                    " because it's not currently active"))
        else:
            self.wizard().jobRecap.setText(H3Core.current_job_contract.job_code + " - "
                                           + H3Core.current_job_contract.job_title)
            self.wizard().baseRecap.setText(H3Core.current_job_contract.base + " - "
                                            + H3Core.get_base(H3Core.current_job_contract.base).full_name)

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


class LoginBox:
    """
    This is the first thing that greets the user.
    It has the logic for 5 login retries maximum.
    If local login is accepted, the main window adapts to the user.
    If not, the program exits.
    It can ask the main class to start the new user wizard.
    """

    def __init__(self, parent_h3_gui):
        self.gui = parent_h3_gui
        self.login_box = QtUiTools.QUiLoader().load(QtCore.QFile("H3/GUI/QtDesigns/LoginBox.ui"),
                                                    self.gui.root_window)

        desktop_rect = self.gui.rect
        rect2 = QtCore.QRect(desktop_rect.width() * 2 / 5,
                             desktop_rect.height() * 2 / 7,
                             desktop_rect.width() * 1 / 5,
                             desktop_rect.height() * 1 / 5)
        self.login_box.setGeometry(rect2)

        self.login_attempts = 0

        if H3Core.current_job_contract:
            self.login_box.loginLineEdit.setText(H3Core.current_job_contract.user)

        self.login_box.pushButton.clicked.connect(self.login_clicked)
        self.login_box.new_user_pushButton.clicked.connect(self.gui.run_setup_wizard)

        if self.login_box.exec_() == QtGui.QDialog.Rejected:
            sys.exit()

    def login_clicked(self):
        if self.login_attempts < 4:
            username = self.login_box.loginLineEdit.text()
            password = self.login_box.passwordLineEdit.text()
            H3Core.local_login(username, password)
            if H3Core.user_state == "ok":
                self.login_box.accept()
                self.gui.set_status(_("Successfully logged in as %(name)s") % {"name": username})
            elif H3Core.user_state == "new_base":
                message_box = QtGui.QMessageBox(QtGui.QMessageBox.Information, _("New base data needed"),
                                                _("This user is currently affected to a base that is not present in"
                                                  " the local database. Maybe the user got promoted to a new base, "
                                                  "or this is H3 installation is old. Please run the setup wizard."),
                                                QtGui.QMessageBox.Ok)
                message_box.setWindowIcon(QtGui.QIcon(":/images/H3.png"))
                message_box.exec_()
            elif H3Core.user_state == "no_job":
                message_box = QtGui.QMessageBox(QtGui.QMessageBox.Information, _("No active job contract"),
                                                _("This user is currently not employed according to the local "
                                                  "H3 database; Please contact your focal point if this is wrong."),
                                                QtGui.QMessageBox.Ok)
                message_box.setWindowIcon(QtGui.QIcon(":/images/H3.png"))
                message_box.exec_()
            elif H3Core.user_state == "nok":
                self.login_attempts += 1
                self.gui.set_status("login failed, " + str((5 - self.login_attempts)) + " remaining")
        else:
            self.login_box.reject()


class H3MainGUI:
    """
    This is the main visual interface init for the program.
    It pops the Login Box by default, and handles creation of other dialogs,
    as well as switching the main window's central widget.
    """

    def __init__(self, desktop):
        self.load_resource_file()
        self.root_window = QtGui.QMainWindow()
        self.root_window = QtUiTools.QUiLoader().load(QtCore.QFile("H3/GUI/QtDesigns/Main.ui"), desktop)
        self.rect = desktop.availableGeometry()

        rect2 = QtCore.QRect(self.rect.width() / 6,
                             self.rect.height() / 6,
                             self.rect.width() * 2 / 3,
                             self.rect.height() * 2 / 3)
        self.root_window.setGeometry(rect2)

        self.root_window.show()

        # TODO : Have Status bar watch the log file for messages (store in a tablemodel)+"local DB Accessible" indicator

        while not H3Core.ready():
            self.run_setup_wizard()

        LoginBox(self)

        self.current_screen = None

        self.root_window.setWindowTitle(_("{first} {last}, {job}, {base}")
                                        .format(first=H3Core.get_user(H3Core.current_job_contract.user).first_name,
                                                last=H3Core.get_user(H3Core.current_job_contract.user).last_name,
                                                job=H3Core.current_job_contract.job_title,
                                                base=H3Core.get_base(H3Core.current_job_contract.base).full_name))

        actions_model = self.build_actions_menu()
        self.root_window.treeView.setModel(actions_model)
        self.root_window.treeView.expandAll()
        self.root_window.treeView.resizeColumnToContents(0)
        self.root_window.treeView.setFixedWidth(self.root_window.treeView.columnWidth(0) + 10)
        self.root_window.Actions.setFixedWidth(self.root_window.treeView.size().width() + 50)

        self.selection_model = self.root_window.treeView.selectionModel()

        self.selection_model.currentChanged.connect(self.ui_switcher)

    @staticmethod
    def build_actions_menu():
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
            item.setStatusTip(desc.description)
            action_items.append(item)

        for delegation in H3Core.delegations:
            desc = H3Core.get_action_descriptions(delegation.action)
            categories.add(desc.category)
            item = QtGui.QStandardItem(desc.description)
            item.setData(delegation, 33)
            item.setData(desc, 34)
            item.setStatusTip(desc.description)
            tooltip = _("Delegated until : {end}.").format(end=delegation.end_date)
            if delegation.scope != 'all':
                tooltip.append(_("\nScope :  {sc}").format(sc=delegation.scope))
            if delegation.maximum != -1:
                tooltip.append(_("\nLimit :  {lim}").format(lim=delegation.maximum))
            item.setToolTip(tooltip)
            item.setBackground(QtGui.QBrush(QtCore.Qt.green))
            action_items.append(item)

        cat2 = sorted(categories)

        for cat in cat2:
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
    def ui_switcher(self, action_menu_item):
        action = ""
        if action_menu_item.data(34):
            action = action_menu_item.data(34).code
        if action == 'manage_bases':
            self.current_screen = ManageBases(self)

    def run_setup_wizard(self):
        SetupWizard(self)

    def set_status(self, status_string):
        self.root_window.statusbar.showMessage(status_string, 2000)


class ManageBases:
    """
    Handles the "manage bases" action : UI elements and core interaction.
    """

    def __init__(self, parent_h3_gui):
        self.gui = parent_h3_gui
        self.menu = QtUiTools.QUiLoader().load(QtCore.QFile("H3/GUI/QtDesigns/Bases.ui"), self.gui.root_window)
        self.gui.root_window.setCentralWidget(self.menu)
        self.model = QtGui.QStandardItemModel()
        base_data = H3Core.read_table(Acd.WorkBase, "local")

        tree_row = list()
        next_row = list()

        for record in base_data:
            if record.parent == record.code:
                root_item = QtGui.QStandardItem(record.code)
                desc = QtGui.QStandardItem(record.full_name)
                root_item.setData(record, 33)
                tree_row.append(root_item)
                self.model.invisibleRootItem().appendRow(root_item)
                self.model.invisibleRootItem().appendColumn([desc])

        assert len(tree_row) == 1

        while tree_row:
            for parent in tree_row:
                for base in base_data:
                    if base.parent == parent.data(33).code and not base.code == base.parent:
                        item = QtGui.QStandardItem(record.code)
                        item.setData(record, 33)
                        desc = QtGui.QStandardItem(record.full_name)
                        parent.appendRow(item)
                        parent.appendColumn(desc)
                        next_row.append(item)
            tree_row = next_row
            next_row = []

        self.model.setColumnCount(2)
        headers = (_('Base code'), _('Full name'))
        self.model.setHorizontalHeaderLabels(headers)
        self.menu.treeView.setModel(self.model)
        self.menu.treeView.resizeColumnToContents(0)
        self.menu.treeView.resizeColumnToContents(1)

        self.base_selection_model = self.menu.treeView.selectionModel()
        self.base_selection_model.currentChanged.connect(self.update_stats)

        self.menu.createButton.clicked.connect(self.create_base_box)
        # self.menu.editButton.clicked.connect(self.edit_box)
        # self.menu.deleteButton.clicked.connect(self.delete_box)

    @QtCore.Slot(int)
    # TODO: figure out why this doesn't work !!
    def update_stats(self, base_index):
        if not base_index:
            self.menu.opendate.setText("-")
            self.menu.userno.setText("-")
        elif base_index.data(33):
            self.menu.opendate.setText(base_index.data(33).opened_date)
            count = H3Core.get_user_count(base_index.data(33).code)
            if count:
                self.menu.userno.setText(count)
            else:
                self.menu.userno.setText(_("Data unavailable without a connection to the remote DB"))

    def create_base_box(self):
        selected_base = self.base_selection_model.currentIndex().data(33)
        create_base_box = QtUiTools.QUiLoader().load(QtCore.QFile("H3/GUI/QtDesigns/CreateBaseBox.ui"),
                                                     self.gui.root_window)
        base_data = H3Core.read_table(Acd.WorkBase, "local")
        bases_list = list()

        for record in base_data:
            bases_list.append(record.code)

        create_base_box.parentBaseComboBox.setModel(QtGui.QStringListModel(bases_list))
        create_base_box.timeZoneComboBox.setModel(QtGui.QStringListModel(["UTC", "GMT"]))

        create_base_box.openingDateDateEdit.setDate(datetime.date.today())

        if create_base_box.exec_() == QtGui.QDialog.Accepted:
            new_base = Acd.WorkBase(code="TEMP_" + create_base_box.baseCodeLineEdit.text(),
                                    parent=create_base_box.parentBaseComboBox.text(),
                                    full_name=create_base_box.fullNameLineEdit.text(),
                                    opened_date=create_base_box.openingDateDateEdit.date(),
                                    country=create_base_box.counTryCodeLineEdit.text(),
                                    time_zone=create_base_box.timeZoneComboBox.text())
            H3Core.create_base(new_base)


def run():
    h3app = QtGui.QApplication(sys.argv)
    desk = h3app.desktop()
    h3gui = H3MainGUI(desk)
    h3app.exec_()

def init_remote(location, password):
    H3Core.init_remote(location, password)

def nuke_remote(location, password):
    H3Core.nuke_remote(location, password)
