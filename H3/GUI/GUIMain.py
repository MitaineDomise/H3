__author__ = 'Man'

import sys
import logging
import datetime
import locale

from PySide import QtGui, QtCore, QtUiTools

from iso3166 import countries
import pytz
import babel
import babel.dates

from H3.core import AlchemyCore
from H3.core import AlchemyClassDefs as Acd

H3Core = AlchemyCore.H3AlchemyCore()

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
            self.check_local()

        if H3Core.remote_db:
            self.wizard.remoteAddress.setText(H3Core.remote_db.location)
            self.check_remote()

        if H3Core.current_job_contract:
            user = H3Core.get_from_primary_key(Acd.User, H3Core.current_job_contract.user)
            self.wizard.usernameLineEdit.setText(user.login)

        self.wizard.browseButton.clicked.connect(self.browse)

        self.wizard.localAddress.textChanged.connect(self.check_local)
        self.wizard.remoteAddress.textChanged.connect(self.invalidate_remote)
        self.wizard.connectButton.clicked.connect(self.check_remote)

        self.wizard.usernameLineEdit.textChanged.connect(self.invalidate_user)
        self.wizard.searchButton.clicked.connect(self.check_user)

        self.wizard.accepted.connect(self.connect_and_sync)
        if self.wizard.exec_() == QtGui.QDialog.Rejected:
            if H3Core.wizard_system_ready():
                H3Core.log_off()
            else:
                sys.exit()

    def connect_and_sync(self):
        """
        At the end of the wizard, depending on state, take the following action:
         - no such user or user with no job : exit
         - user waiting for creation : update password
         - new user and / or base data gets downloaded
         - A downward sync happens (including for local users)
        :return:
        """
        username = self.wizard.usernameLineEdit.text()
        password = self.wizard.passwordLineEdit.text()
        if H3Core.internal_state["user"] == ("no_job" or "invalid"):
            sys.exit()
        elif H3Core.internal_state["user"] == "new":
            H3Core.remote_pw_change(username, username + "YOUPIE", password)
            H3Core.internal_state["user"] = "remote"
        elif H3Core.internal_state["user"] == "remote":
            H3Core.remote_login(username, password)
        H3Core.initial_setup()

    def check_user(self):
        """
        Checks that the login the user entered exists in either DB
        The core will also check for cases like having no job or a job on a different base
        :return:
        """
        username = self.wizard.usernameLineEdit.text()
        # TODO : Have global and base "profiles" for sets of actions
        # TODO : Make the mail routing table for actions
        # TODO : Filter closed bases, banned users, finished JCs at download - Think harder about base closing: final ?
        # TODO : Switch to JSON for scope and limit
        # TODO : Start Excel import / export work
        # TODO : start work on image DB
        # TODO : start work on versioning exploration

        # noinspection PyUnusedLocal
        temp_user_ok = self.wizard.user_ok
        if username == "":
            self.wizard.userStatusLabel.setText("")
        else:
            H3Core.wizard_find_user(username)

        if H3Core.internal_state["user"] == "local":
            self.wizard.userStatusLabel.setText(_("User {login} already recorded locally, you can proceed !")
                                                .format(login=username))
            temp_user_ok = True
            self.wizard.pw_ok = True
        elif H3Core.internal_state["user"] == "remote":
            self.wizard.passwordLineEdit.show()
            self.wizard.passwordLabel.show()
            self.wizard.passwordLineEdit.textChanged.connect(self.check_pws)
            self.wizard.userStatusLabel.setText(_("User {login} found in remote, please enter password")
                                                .format(login=username))
            temp_user_ok = True
        elif H3Core.internal_state["user"] == "new":
            self.wizard.passwordLineEdit.show()
            self.wizard.passwordLabel.show()
            self.wizard.confirmPasswordLineEdit.show()
            self.wizard.confirmPasswordLabel.show()
            self.wizard.passwordLineEdit.textChanged.connect(self.check_pws)
            self.wizard.confirmPasswordLineEdit.textChanged.connect(self.check_pws)
            self.wizard.userStatusLabel.setText(_("User {login} ready for creation, please enter password")
                                                .format(login=username))
            temp_user_ok = True
        elif H3Core.internal_state["user"] == "no_job":
            temp_user_ok = False
            self.wizard.userStatusLabel.setText(_("User {login} has no current contract. "
                                                  "Please contact your focal point")
                                                .format(login=username))
        elif H3Core.internal_state["user"] == "invalid":
            temp_user_ok = False
            self.wizard.userStatusLabel.setText(_("User {login} not found. Please contact your focal point.")
                                                .format(login=username))
        if temp_user_ok != self.wizard.user_ok:
            self.wizard.user_ok = temp_user_ok
            self.wizard.wizardPage3.completeChanged.emit()

    def check_pws(self):
        """
        Will check that the password is > 5 characters.
        In the case of a new user, checks that both fields match.
        :return:
        """
        temp_pw_ok = self.wizard.pw_ok
        pw1 = self.wizard.passwordLineEdit.text()
        pw2 = self.wizard.confirmPasswordLineEdit.text()
        if H3Core.internal_state["user"] == "new":
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
        elif H3Core.internal_state["user"] == "remote":
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
        local_db_exists = AlchemyCore.ping_local(self.wizard.localAddress.text())
        # noinspection PyUnusedLocal
        temp_local_ok = self.wizard.local_ok
        if local_db_exists == "OK":
            self.wizard.localDBstatus.setText(_("Ready to create new local DB at {location}")
                                              .format(location=self.wizard.localAddress.text()))
            temp_local_ok = True
        elif local_db_exists == "H3DB":
            self.wizard.localDBstatus.setText(_("{location} is a valid H3 DB")
                                              .format(location=self.wizard.localAddress.text()))
            temp_local_ok = True
        elif local_db_exists == "OTHERFILE":
            self.wizard.localDBstatus.setText(_("{location} is not a valid location for a H3 DB")
                                              .format(location=self.wizard.localAddress.text()))
            temp_local_ok = False
        elif local_db_exists == "NO_RW":
            self.wizard.localDBstatus.setText(_("Impossible to read or write {location}")
                                              .format(location=self.wizard.localAddress.text()))
            temp_local_ok = False
        elif local_db_exists == "NO_R":
            self.wizard.localDBstatus.setText(_("Impossible to read {location}")
                                              .format(location=self.wizard.localAddress.text()))
            temp_local_ok = False
        elif local_db_exists == "NO_W":
            self.wizard.localDBstatus.setText(_("Impossible to write {location}")
                                              .format(location=self.wizard.localAddress.text()))
            temp_local_ok = False
        elif local_db_exists == "EMPTY":
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
            remote_db_exists = AlchemyCore.ping_remote(location)
            # noinspection PyUnusedLocal
            temp_remote_ok = self.wizard.remote_ok
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
        """
        Called on changing the remote DB address field after having checked it
        """
        if self.wizard.remote_ok:
            self.wizard.remote_ok = False
            self.wizard.wizardPage2.completeChanged.emit()

    def invalidate_user(self):
        """
        Called on changing the login field after having checked it
        """
        if self.wizard.user_ok:
            self.wizard.user_ok = False
            self.wizard.pw_ok = False
            self.wizard.wizardPage3.completeChanged.emit()


class ServerWizardPage(QtGui.QWizardPage):
    """
    Custom class with a specialized routine checking both DBs are reachable
    before the user can proceed
    """
    def __init__(self, parent):
        super(ServerWizardPage, self).__init__(parent)

    def isComplete(self, *args, **kwargs):
        result = self.wizard().local_ok and self.wizard().remote_ok
        if result:
            return True
        else:
            return False


class LoginWizardPage(QtGui.QWizardPage):
    """
    Custom class with a specialized routine checking the user exists
    and password is correct before the user can proceed.
    On init, will commit the database info from the previous page.
    """
    def __init__(self, parent):
        super(LoginWizardPage, self).__init__(parent)

    def isComplete(self, *args, **kwargs):
        result = self.wizard().user_ok and self.wizard().pw_ok
        if result:
            return True
        else:
            return False

    def initializePage(self, *args, **kwargs):
        H3Core.wizard_setup_databases(self.wizard().localAddress.text(),
                                      self.wizard().remoteAddress.text())
        self.wizard().passwordLineEdit.hide()
        self.wizard().passwordLabel.hide()
        self.wizard().confirmPasswordLineEdit.hide()
        self.wizard().confirmPasswordLabel.hide()


class RecapWizardPage(QtGui.QWizardPage):
    """
    Custom class with a specialized routine recapitulating the user info
    and the relevant action the program will take.
    On init, will commit the user info from the previous page.
    """
    def __init__(self, parent):
        super(RecapWizardPage, self).__init__(parent)

    def initializePage(self, *args, **kwargs):

        self.wizard().localRecap.setText(self.wizard().localAddress.text())
        self.wizard().remoteRecap.setText(self.wizard().remoteAddress.text())

        user = H3Core.get_from_primary_key(Acd.User, H3Core.current_job_contract.user, "remote")
        self.wizard().nameRecap.setText(_("{first} {last}")
                                        .format(first=user.first_name, last=user.last_name))

        if H3Core.internal_state["user"] == "no_job":
            self.wizard().jobRecap.setText(_("No current contract"))
            self.wizard().baseRecap.setText(_("No current posting"))
            self.wizard().userActionRecap.setText(_("The user profile can not be used in H3"
                                                    " because it's not currently active"))
        else:
            self.wizard().jobRecap.setText(H3Core.current_job_contract.job_title)
            base = H3Core.get_from_primary_key(Acd.WorkBase, H3Core.current_job_contract.work_base, "remote")
            self.wizard().baseRecap.setText(_("{id} - {fullname}")
                                            .format(id=base.identifier, fullname=base.full_name))

            if H3Core.internal_state["user"] == "local":
                self.wizard().userActionRecap.setText(_("The user profile was already set up in the local database."
                                                        "This wizard will only update the user info."))
            elif H3Core.internal_state["user"] == "remote":
                self.wizard().userActionRecap.setText(_("The user profile will be downloaded into the local database. "
                                                        "You can then login. Welcome back to H3 !"))
            elif H3Core.internal_state["user"] == "new":
                self.wizard().userActionRecap.setText(_("The user profile will be initialized and downloaded into the"
                                                        " local database. Welcome to H3 !"))
            if H3Core.internal_state["base"] == "new":
                message_box = QtGui.QMessageBox(QtGui.QMessageBox.Information, _("New base data needed"),
                                                _("H3 will now download the data for the office this user is "
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
            user = H3Core.get_from_primary_key(Acd.User, H3Core.current_job_contract.user)
            self.login_box.loginLineEdit.setText(user.login)

        self.login_box.pushButton.clicked.connect(self.login_clicked)
        self.login_box.new_user_pushButton.clicked.connect(self.gui.run_setup_wizard)

        if self.login_box.exec_() == QtGui.QDialog.Rejected:
            sys.exit()

    def login_clicked(self):
        """
        Logs the user locally and checks for changes to his or her status.
        Will exit after 5 tries.
        """
        if self.login_attempts < 4:
            username = self.login_box.loginLineEdit.text()
            password = self.login_box.passwordLineEdit.text()
            H3Core.login(username, password)
            if H3Core.internal_state["user"] == "ok":
                self.login_box.accept()
                self.gui.set_status(_("Successfully logged in as {name}").format(name=username))
            elif H3Core.internal_state["user"] == "no_job":
                message_box = QtGui.QMessageBox(QtGui.QMessageBox.Information, _("No active job contract"),
                                                _("This user is currently not employed according to the local "
                                                  "H3 database; Please contact your focal point if this is wrong."),
                                                QtGui.QMessageBox.Ok)
                message_box.setWindowIcon(QtGui.QIcon(":/images/H3.png"))
                message_box.exec_()
            elif H3Core.internal_state["user"] == "nok":
                self.login_attempts += 1
                self.gui.set_status(_("login failed, {remaining_attempts} attempts remaining")
                                    .format(remaining_attempts=str((5 - self.login_attempts))))
            if H3Core.internal_state["base"] == "relocated":
                message_box = QtGui.QMessageBox(QtGui.QMessageBox.Information, _("New base data needed"),
                                                _("This user is currently affected to a base that is not present in"
                                                  " the local database. The user may have been promoted to a new base, "
                                                  "or this H3 installation is old. Please run the setup wizard."),
                                                QtGui.QMessageBox.Ok)
                message_box.setWindowIcon(QtGui.QIcon(":/images/H3.png"))
                message_box.exec_()
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

        self.locale = babel.Locale.parse(locale.getdefaultlocale()[0], "_")

        syncbutton = QtGui.QPushButton(QtGui.QIcon(":/images/H3.png"), _("Sync"), self.root_window)
        # noinspection PyUnresolvedReferences
        syncbutton.clicked.connect(self.sync)

        self.root_window.statusbar.addPermanentWidget(syncbutton)

        self.root_window.show()

        while not H3Core.wizard_system_ready():
            self.run_setup_wizard()

        LoginBox(self)

        self.current_screen = None

        base = H3Core.get_from_primary_key(Acd.WorkBase, H3Core.current_job_contract.work_base)
        user = H3Core.get_from_primary_key(Acd.User, H3Core.current_job_contract.user)

        self.root_window.setWindowTitle(_("{first} {last}, {job}, {base}")
                                        .format(first=user.first_name,
                                                last=user.last_name,
                                                job=H3Core.current_job_contract.job_title,
                                                base=base.full_name))

        actions_model = self.build_actions_menu()
        self.root_window.treeView.setModel(actions_model)
        self.root_window.treeView.expandAll()
        self.root_window.treeView.resizeColumnToContents(0)
        self.root_window.treeView.setFixedWidth(self.root_window.treeView.columnWidth(0) + 10)
        self.root_window.Actions.setFixedWidth(self.root_window.treeView.size().width() + 50)

        action_selector = self.root_window.treeView.selectionModel()

        # This allows keyboard navigation in the action bar
        action_selector.currentChanged.connect(self.ui_switcher)
        self.root_window.treeView.clicked.connect(self.ui_switcher)

    def sync(self):
        # This syncs local and remote DB then refreshes the current action menu by "clicking" it
        H3Core.sync_up()
        self.root_window.treeView.clicked.emit(self.root_window.treeView.currentIndex())

    @staticmethod
    def build_actions_menu():
        """
        Collects the actions the current user can execute and builds
        a custom menu out of them.
        """
        H3Core.update_assigned_actions()
        model = QtGui.QStandardItemModel()

        categories = set()
        action_items = list()

        for assigned_action in H3Core.assigned_actions:
            action = H3Core.get_from_primary_key(Acd.Action, assigned_action.action)
            categories.add(AlchemyCore.json_read(action.language, H3Core.language, 'cat'))
            item = QtGui.QStandardItem(AlchemyCore.json_read(action.language, H3Core.language, 'desc'))
            item.setData(assigned_action, 33)
            item.setData(action, 34)
            if assigned_action.delegated_from:
                tooltip = _("Delegated until : {end}.").format(end=assigned_action.end_date)
                # if assigned_action.scope != 'all':
                #     tooltip.append(_("\nScope :  {sc}").format(sc=assigned_action.scope))
                # if assigned_action.maximum != -1:
                #     tooltip.append(_("\nLimit :  {lim}").format(lim=assigned_action.maximum))
                item.setToolTip(tooltip)
                item.setBackground(QtGui.QBrush(QtCore.Qt.green))
            action_items.append(item)

        cat2 = sorted(categories)

        for cat in cat2:
            cat_item = QtGui.QStandardItem(cat)
            for item in action_items:
                action = item.data(34)
                if AlchemyCore.json_read(action.language, H3Core.language, 'cat') == cat:
                    cat_item.appendRow(item)
            model.appendRow(cat_item)

        return model

    @staticmethod
    def load_resource_file():
        """
        Loads the resource file for icons, logos and other organization-specific files
        """
        # noinspection PyTypeChecker,PyCallByClass
        if QtCore.QResource.registerResource("H3/GUI/QtDesigns/H3.rcc"):
            logger.debug(_("Resource file opened successfully"))
        else:
            logger.warning(_("Error loading resource file"))

    @QtCore.Slot(int)
    def ui_switcher(self, action_menu_item):
        """
        From the entry selected in the actions menu, display the relevant widget
        in the central area.
        """
        action = ""
        if action_menu_item.data(34):
            action = action_menu_item.data(34).identifier
        if action == 'manage_bases':
            self.current_screen = ManageBases(self)

    def run_setup_wizard(self):
        H3Core.clear_variables()
        SetupWizard(self)

    def set_status(self, status_string):
        """
        Displays a status message for 2 seconds in the status bar.
        """
        self.root_window.statusbar.showMessage(status_string, 2000)


class ManageBases:
    """
    Handles the "manage bases" action : UI elements and core interaction.
    This is an admin-level action that will be allowed to create and edit global data without further approval
    """

    def __init__(self, parent_h3_gui, action=None, base=None):
        """
        If called with action != None, jumps to the relevant action on the relevant base
        :param parent_h3_gui:
        :param action: create, delete, edit
        :param base: Acd.WorkBase object
        :return:
        """
        self.gui = parent_h3_gui
        self.menu = QtUiTools.QUiLoader().load(QtCore.QFile("H3/GUI/QtDesigns/Bases.ui"), self.gui.root_window)
        self.gui.root_window.setCentralWidget(self.menu)
        self.selected_base = None

        self.countries_model = QtGui.QStandardItemModel()
        for c in countries:
            localized_name = self.gui.locale.territories[c.alpha2]
            item = QtGui.QStandardItem(_("{code} - {fullname}").format(code=c.alpha2, fullname=localized_name))
            item.setData(c, 33)
            self.countries_model.appendRow(item)

        self.timezones_model = QtGui.QStandardItemModel()
        self.timezones_model.appendRow(QtGui.QStandardItem(_("Choose a country")))

        # Updated when refreshing tree - we don't have the workbase data at this point
        self.parents_model = QtGui.QStandardItemModel()

        self.bases_tree_model = QtGui.QStandardItemModel()
        self.menu.treeView.setModel(self.bases_tree_model)
        self.refresh_tree(H3Core.current_job_contract.work_base)

        self.menu.treeView.clicked.connect(self.update_stats)

        self.menu.createButton.clicked.connect(self.create_base)
        self.menu.editButton.clicked.connect(self.edit_base)
        self.menu.deleteButton.clicked.connect(self.close_base)
        self.menu.exportButton.clicked.connect(self.export_bases)

        # Double-click / enter launches edit of the base
        self.menu.treeView.activated.connect(self.edit_base)

        if action == "create":
            self.create_base(base)
        if action == "update":
            self.edit_base(base)
        if action == "delete":
            self.close_base(base)

    def refresh_tree(self, base_code):
        self.bases_tree_model.clear()
        hidden_root = self.bases_tree_model.invisibleRootItem()

        queue_data = H3Core.read_table(Acd.SyncJournal)
        fresh = list()
        temp = list()
        for queue_item in queue_data:
            age = datetime.datetime.utcnow() - queue_item.local_timestamp
            if age.total_seconds() / 60 < 5:
                fresh.append(queue_item.key)
            if queue_item.type == "CREATE" and queue_item.status == "UNSUBMITTED":
                temp.append(queue_item.key)

        base_data = H3Core.read_table(Acd.WorkBase)

        tree_row = list()
        next_row = list()

        for p in base_data:
            item = QtGui.QStandardItem(_("{code} - {fullname}").format(code=p.identifier, fullname=p.full_name))
            item.setData(p, 33)
            self.parents_model.appendRow(item)

        for record in base_data:
            if record.code == base_code:
                # Root of the tree is based on user's home base
                root_record = record
                # Real root which is parent of itself is removed from the list
                if record.parent == record.code:
                    _record = base_data.pop(base_data.index(record))
                root_item = QtGui.QStandardItem(root_record.identifier)
                root_desc = QtGui.QStandardItem(root_record.full_name)
                root_item.setData(root_record, 33)  # includes the base object itself in the first custom data role
                self.selected_base = root_record
                root_child_no = hidden_root.rowCount()
                hidden_root.setChild(root_child_no, 0, root_item)
                hidden_root.setChild(root_child_no, 1, root_desc)
                tree_row.append(root_item)

        while tree_row:
            for parent in tree_row:
                for base in base_data:
                    if base.parent == parent.data(33).code:
                        base_item = QtGui.QStandardItem(base.identifier)
                        base_desc = QtGui.QStandardItem(base.full_name)
                        base_item.setData(base, 33)
                        parent_child_no = parent.rowCount()
                        self.paint_line(base_item, base_desc, fresh, temp)
                        parent.setChild(parent_child_no, 0, base_item)
                        parent.setChild(parent_child_no, 1, base_desc)
                        next_row.append(base_item)
            tree_row = next_row
            next_row = []

        self.bases_tree_model.setColumnCount(2)
        headers = (_('Base code'), _('Full name'))
        self.bases_tree_model.setHorizontalHeaderLabels(headers)
        self.menu.treeView.expandAll()
        self.menu.treeView.resizeColumnToContents(0)
        self.menu.treeView.resizeColumnToContents(1)

    def paint_line(self, base_item, base_desc, fresh, temp):
        base = base_item.data(33)
        if base.closed_date and base.closed_date <= datetime.date.today():
            base_item.setForeground(QtGui.QBrush(QtGui.QColor('lightgray')))
            base_desc.setForeground(QtGui.QBrush(QtGui.QColor('lightgray')))
            base_desc.setText(_("{name} - closed on {date}")
                              .format(name=base.full_name, date=base.closed_date))
        if base.code in fresh:
            font = QtGui.QFont()
            font.setBold(True)
            base_item.setFont(font)
            base_desc.setFont(font)
        if base.code in temp:
            base_item.setBackground(QtGui.QBrush(QtGui.QColor('pink')))
            base_desc.setBackground(QtGui.QBrush(QtGui.QColor('pink')))

    @QtCore.Slot(int)
    def update_stats(self, _index):
        row_index = self.menu.treeView.currentIndex()
        base_index = self.bases_tree_model.index(row_index.row(), 0, row_index.parent())
        self.selected_base = base_index.data(33) or self.bases_tree_model.invisibleRootItem().child(0).data(33)
        self.menu.statsGroupBox.setTitle(_("{base} stats").format(base=self.selected_base.identifier))
        self.menu.openDate.setText(str(self.selected_base.opened_date))
        count = H3Core.get_user_count(self.selected_base.code)
        if count:
            self.menu.userNo.setText(str(count))
        else:
            count = H3Core.get_user_count(self.selected_base.code, "remote")
            if count:
                self.menu.userNo.setText(str(count))
            else:
                self.menu.userNo.setText(_("Data unavailable without a connection to the remote DB"))
        if self.selected_base.closed_date and self.selected_base.closed_date <= datetime.date.today():
            self.menu.deleteButton.setEnabled(False)
        else:
            self.menu.deleteButton.setEnabled(True)

    def create_base(self, base=None):
        """
        Creates the dialog box for base creation. If base isn't None, prefill with the info contained
        :param base: an Acd.Workbase object
        :return:
        """
        # TODO : Make core check you have the proper rights
        create_base_box = QtUiTools.QUiLoader().load(QtCore.QFile("H3/GUI/QtDesigns/CreateBaseBox.ui"),
                                                     self.gui.root_window)

        create_base_box.countryComboBox.setModel(self.countries_model)
        create_base_box.timeZoneComboBox.setModel(self.timezones_model)
        create_base_box.parentComboBox.setModel(self.parents_model)

        create_base_box.countryComboBox.highlighted[str].connect(self.update_timezones)

        if base:
            create_base_box.baseCodeLineEdit.setText(base.identifier)
            parent_base = H3Core.get_from_primary_key(Acd.WorkBase, base.parent)
            if parent_base:
                create_base_box.parentComboBox.setCurrentIndex(
                    create_base_box.parentComboBox.findText(parent_base.identifier, QtCore.Qt.MatchStartsWith))
            create_base_box.fullNameLineEdit.setText(base.full_name)
            create_base_box.openingDateDateEdit.setDate(base.opened_date)
            create_base_box.countryComboBox.setCurrentIndex(
                create_base_box.countryComboBox.findText(base.country, QtCore.Qt.MatchStartsWith))
            self.update_timezones(base.country)
            create_base_box.timeZoneComboBox.setCurrentIndex(
                create_base_box.timeZoneComboBox.findText(base.time_zone, QtCore.Qt.MatchExactly)
            )
        else:
            create_base_box.parentComboBox.setCurrentIndex(
                create_base_box.parentComboBox.findText(self.selected_base.identifier, QtCore.Qt.MatchStartsWith))
            create_base_box.openingDateDateEdit.setDate(datetime.date.today())
            create_base_box.countryComboBox.setCurrentIndex(
                create_base_box.countryComboBox.findText(self.selected_base.country, QtCore.Qt.MatchStartsWith))
            self.update_timezones(self.selected_base.country)

        if create_base_box.exec_() == QtGui.QDialog.Accepted:
            # noinspection PyArgumentList

            new_base = Acd.WorkBase(base="BASE-1",
                                    period="PERMANENT",
                                    parent=create_base_box.parentComboBox.itemData(
                                        create_base_box.parentComboBox.currentIndex(), 33).code or None,
                                    identifier=create_base_box.baseCodeLineEdit.text(),
                                    full_name=create_base_box.fullNameLineEdit.text(),
                                    opened_date=create_base_box.openingDateDateEdit.date().toPython(),
                                    country=create_base_box.countryComboBox.itemData(
                                        create_base_box.countryComboBox.currentIndex(), 33)[1],
                                    time_zone=create_base_box.timeZoneComboBox.currentText())

            if H3Core.create_base(new_base) == "OK":
                self.refresh_tree(H3Core.current_job_contract.work_base)
            else:
                message_box = QtGui.QMessageBox(QtGui.QMessageBox.Warning, _("Base not created"),
                                                _("H3 could not create this base. Check all data is valid"),
                                                QtGui.QMessageBox.Ok)
                message_box.setWindowIcon(QtGui.QIcon(":/images/H3.png"))
                message_box.exec_()

    def edit_base(self, base=None):
        """
        Creates the dialog box for base creation. If base isn't None, prefill with the info contained
        :param base: an Acd.Workbase object
        :return:
        """
        edit_base_box = QtUiTools.QUiLoader().load(QtCore.QFile("H3/GUI/QtDesigns/EditBaseBox.ui"),
                                                   self.gui.root_window)

        edit_base_box.countryComboBox.setModel(self.countries_model)
        edit_base_box.timeZoneComboBox.setModel(self.timezones_model)
        edit_base_box.parentComboBox.setModel(self.parents_model)

        edit_base_box.countryComboBox.highlighted[str].connect(self.update_timezones)

        if not base:
            base = self.selected_base

        edit_base_box.baseCodeLineEdit.setText(base.identifier)
        parent_base = H3Core.get_from_primary_key(Acd.WorkBase, base.parent)
        if parent_base:
            edit_base_box.parentComboBox.setCurrentIndex(
                edit_base_box.parentComboBox.findText(parent_base.identifier, QtCore.Qt.MatchStartsWith))

        edit_base_box.fullNameLineEdit.setText(base.full_name)
        edit_base_box.openingDateDateEdit.setDate(base.opened_date)
        edit_base_box.countryComboBox.setCurrentIndex(
            edit_base_box.countryComboBox.findText(base.country, QtCore.Qt.MatchStartsWith))
        self.update_timezones(base.country)
        edit_base_box.timeZoneComboBox.setCurrentIndex(
            edit_base_box.timeZoneComboBox.findText(base.time_zone, QtCore.Qt.MatchExactly))

        if edit_base_box.exec_() == QtGui.QDialog.Accepted:
            base.parent = edit_base_box.parentComboBox.itemData(
                edit_base_box.parentComboBox.currentIndex(), 33).code or None
            base.identifier = edit_base_box.baseCodeLineEdit.text()
            base.full_name = edit_base_box.fullNameLineEdit.text()
            base.opened_date = edit_base_box.openingDateDateEdit.date().toPython()
            base.country = edit_base_box.countryComboBox.itemData(
                edit_base_box.countryComboBox.currentIndex(), 33)[1]
            base.time_zone = edit_base_box.timeZoneComboBox.currentText()

            if H3Core.update_base(base) == "OK":
                self.refresh_tree(H3Core.current_job_contract.work_base)
            else:
                message_box = QtGui.QMessageBox(QtGui.QMessageBox.Warning, _("Base not modified"),
                                                _("H3 could not modify this base. Check all data is valid"),
                                                QtGui.QMessageBox.Ok)
                message_box.setWindowIcon(QtGui.QIcon(":/images/H3.png"))
                message_box.exec_()

    def close_base(self, base=None):
        close_base_box = QtUiTools.QUiLoader().load(QtCore.QFile("H3/GUI/QtDesigns/DeleteBaseBox.ui"),
                                                    self.gui.root_window)
        close_base_box.dateEdit.setDate(datetime.date.today())

        if not base:
            base = self.selected_base

        close_base_box.warningLabel.setText(_("Are you sure you want to close base {code} - {name} ?")
                                            .format(code=base.identifier, name=base.full_name))

        if close_base_box.exec_() == QtGui.QDialog.Accepted:
            base.closed_date = close_base_box.dateEdit.date().toPython()
            if H3Core.update_base(base) == "OK":
                self.refresh_tree(H3Core.current_job_contract.work_base)
            else:
                message_box = QtGui.QMessageBox(QtGui.QMessageBox.Warning, _("Base not closed"),
                                                _("H3 could not close this base. Check all data is valid"),
                                                QtGui.QMessageBox.Ok)
                message_box.setWindowIcon(QtGui.QIcon(":/images/H3.png"))
                message_box.exec_()

    def export_bases(self):
        filename = H3Core.export_bases()
        message_box = QtGui.QMessageBox(QtGui.QMessageBox.Information, _("Base data exported successfully"),
                                        _("Base data has been exported to the file {file}. Do you want"
                                          " to open it ?")
                                        .format(file=filename),
                                        QtGui.QMessageBox.Ok | QtGui.QMessageBox.Cancel)
        message_box.setWindowIcon(QtGui.QIcon(":/images/H3.png"))
        if message_box.exec_() == QtGui.QMessageBox.Ok:
            AlchemyCore.open_exported(filename)

    @QtCore.Slot(str)
    def update_timezones(self, country):
        tz_list = pytz.country_timezones(country[0:2])
        self.timezones_model.clear()
        for tz in tz_list:
            tz = babel.dates.get_timezone_location(tz, locale=self.gui.locale)
            self.timezones_model.appendRow(QtGui.QStandardItem(tz))


def run():
    h3app = QtGui.QApplication(sys.argv)
    desk = h3app.desktop()
    # noinspection PyUnusedLocal
    h3gui = H3MainGUI(desk)
    h3app.exec_()


def init_remote(location, password):
    AlchemyCore.init_remote(location, password)


def nuke_remote(location, password):
    AlchemyCore.nuke_remote(location, password)
