# coding: utf-8
__author__ = 'Man'

import sys
import logging

from PySide import QtGui, QtCore, QtSql, QtUiTools

from core.AlchemyCore import H3AlchemyCore


H3Core = H3AlchemyCore()

logger = logging.getLogger(__name__)


class H3MainGUI(QtGui.QWidget):
    """
    This is the main visual interface init for the program.
    It pops the Login Box by default, and handles creation of other dialogs,
    as well as switching the main window's central widget.
    """

    def __init__(self):
        super(H3MainGUI, self).__init__()  # Calls the QWidget constructor.
        self.load_resource_file()  # loads H3.rcc, skinnable
        self.root_window = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/Main.ui"), self)
        # TODO : Have Status bar watch the log file for messages (store in a tablemodel)+"local DB Accessible" indicator

        while not H3Core.ready():
            self.run_setup_wizard()

        self.root_window.show()

        LoginBox(self)  # Builds the all-important login box as a child of root

        self.root_window.setWindowTitle(_("{name}, {job}, {base}")
                                        .format(name=H3Core.full_name,
                                                job=H3Core.job_desc,
                                                base=H3Core.base_name))
        # self.ui_switcher(user.job_desc)
        self.root_window.listView.setModel(QtGui.QStringListModel(["Messages",
                                                                   "Manage bases",
                                                                   "Manage users",
                                                                   "Action 4"]))

        self.root_window.listView.clicked.connect(self.do_something)

        MessagesList(self, H3Core.current_user)

    @staticmethod
    def load_resource_file():
        QtCore.QResource.registerResource("H3.rcc")

    @QtCore.Slot(int)
    def do_something(self, num):
        if num.row() == 2:
            ManageUsersScreen(self)

    def ui_switcher(self, screen='jobhome'):
        if screen == 'jobhome':
            self.ui_switcher(H3Core.current_user.job_desc)
        elif screen == 'PM':
            PMMenu(self)
        elif screen == 'project':
            ProjectMenu(self)
        elif screen == 'FP':
            FPMenu(self)
        elif screen == 'LOG':
            pass
            # log_menu = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/LogMenu.ui"))
            # self.H3_root_window.setCentralWidget(LogMenu)

    def run_setup_wizard(self):
        SetupWizard(self)

    def set_status(self, status_string):
        self.root_window.statusbar.showMessage(status_string, 2000)


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
        self.login_box = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/LoginBox.ui"), self)
        self.login_attempts = 0

        self.login_box.pushButton.clicked.connect(self.login_clicked)
        self.login_box.new_user_pushButton.clicked.connect(self.parent().run_setup_wizard)

        if self.login_box.exec_() == QtGui.QDialog.Rejected:
            sys.exit()

    def login_clicked(self):
        if self.login_attempts < 4:
            self.login_attempts += 1
            username = self.login_box.loginLineEdit.text()
            password = self.login_box.passwordLineEdit.text()
            if H3Core.local_login(username, password):
                self.login_box.accept()
                self.parent().set_status(_("Successfully logged in as %(name)s") % {"name": username})
            else:
                self.parent().set_status("login failed, " + str((5 - self.login_attempts)) + " remaining")
        else:
            self.login_box.reject()


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
        self.wizard = loader.load(QtCore.QFile("GUI/QtDesigns/Wizard.ui"), self)

        logo_template = QtGui.QPixmap(":/GUI/images/H3wizardlogo.png")
        self.wizard.setPixmap(QtGui.QWizard.LogoPixmap, logo_template)
        bg_template = QtGui.QPixmap(":/GUI/images/H3wizardbg.png")
        self.wizard.setPixmap(QtGui.QWizard.BackgroundPixmap, bg_template)

        self.wizard.wizardPage2.setCommitPage(True)
        self.wizard.wizardPage3.setCommitPage(True)

        if H3Core.local_db:
            self.wizard.localAddress.setText(H3Core.local_db.location)
            self.local_ok = True

        if H3Core.remote_db:
            self.wizard.remoteAddress.setText(H3Core.remote_db.location)
            self.remote_ok = True

        self.wizard.browseButton.clicked.connect(self.browse)

        self.wizard.localAddress.textChanged.connect(self.check_local)
        self.wizard.remoteAddress.textChanged.connect(self.invalidate_remote)
        self.wizard.connectButton.clicked.connect(self.check_remote)

        self.wizard.usernameLineEdit.textChanged.connect(self.invalidate_user)
        self.wizard.searchButton.clicked.connect(self.check_user)

        self.wizard.accepted.connect(self.setup_user)

        if (self.wizard.exec_() == QtGui.QDialog.Rejected
           and not H3Core.ready()):
            sys.exit()

    def setup_user(self):
        user = self.wizard.usernameLineEdit.text()
        pw = self.wizard.passwordLineEdit.text()

        if H3Core.user_state == "new":
            H3Core.remote_pw_change(user, 'YOUPIE', pw)
        elif H3Core.user_state == "remote":
            # TODO: download base data
            pass

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
        elif H3Core.user_state == "remote":
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
        elif H3Core.user_state == "remote":
            if len(pw1) > 5:
                temp_pw_ok = True
                self.wizard.passwordStatusLabel.setText(_(""))
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

        self.wizard().nameRecap.setText(H3Core.full_name)

        if H3Core.user_state == "no_job":
            self.wizard().jobRecap.setText(_("No current contract"))
            self.wizard().baseRecap.setText(_("No current posting"))
            self.wizard().userActionRecap.setText(_("The user profile can not be used in H3"
                                                    " because it's not currently active"))
        else:
            self.wizard().jobRecap.setText(H3Core.current_job.job_code + " - "
                                           + H3Core.job_desc)
            self.wizard().baseRecap.setText(H3Core.base_code + " - "
                                            + H3Core.base_name)

            if H3Core.user_state == "local":
                self.wizard().userActionRecap.setText(_("The user profile was already set up in the local database."
                                                        "This wizard will only update the user info."))
            elif H3Core.user_state == "remote":
                self.wizard().userActionRecap.setText(_("The user profile will be downloaded into the local database. "
                                                        "You can then login. Welcome back to H3 !"))
            elif H3Core.user_state == "new":
                self.wizard().userActionRecap.setText(_("The user profile will be initialized and downloaded into the"
                                                        " local database. Welcome to H3 !"))
            elif H3Core.user_state == "new_base":
                self.wizard().userActionRecap.setText(_("The user profile will be initialized and downloaded into the"
                                                        " local database. Welcome to H3 !"))

                message_box = QtGui.QMessageBox(QtGui.QMessageBox.Information, _("New base data needed"),
                                                _("H3 will now download the data for the office your new user is "
                                                  "affected to. If this is not a new H3 installation, "
                                                  "please consider deleting and rebuilding your local Database file, "
                                                  "or use the administrative options in H3 to remove old data."),
                                                QtGui.QMessageBox.Ok)
                message_box.setWindowIcon(QtGui.QIcon(":/GUI/images/H3.png"))
                message_box.exec_()

            H3Core.download_user(H3Core.current_user)


class MessagesList(QtGui.QWidget):
    def __init__(self, parent, user):
        super(MessagesList, self).__init__(parent)
        self.messages_list = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/MsgList.ui"), self)

        self.parent().root_window.setCentralWidget(self.messages_list)

        self.dummy_model = QtGui.QStandardItemModel()
        self.dummy_item1 = QtGui.QStandardItem("")
        self.dummy_item2 = QtGui.QStandardItem("")
        self.dummy_item3 = QtGui.QStandardItem("")
        self.dummy_item4 = QtGui.QStandardItem("")
        self.dummy_model.appendRow(self.dummy_item1)
        self.dummy_model.appendRow(self.dummy_item2)
        self.dummy_model.appendRow(self.dummy_item3)
        self.dummy_model.appendRow(self.dummy_item4)
        self.dummy_index1 = self.dummy_model.indexFromItem(self.dummy_item1)
        self.dummy_index2 = self.dummy_model.indexFromItem(self.dummy_item2)
        self.dummy_index3 = self.dummy_model.indexFromItem(self.dummy_item3)
        self.dummy_index4 = self.dummy_model.indexFromItem(self.dummy_item4)

        self.messages_list.tableView.setModel(self.dummy_model)

        self.message1 = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/Message1.ui"))
        self.message2 = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/Message1.ui"))
        self.message3 = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/Message1.ui"))
        self.message4 = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/Message1.ui"))

        self.messages_list.tableView.setIndexWidget(self.dummy_index1, self.message1)
        self.messages_list.tableView.setIndexWidget(self.dummy_index2, self.message2)
        self.messages_list.tableView.setIndexWidget(self.dummy_index3, self.message3)
        self.messages_list.tableView.setIndexWidget(self.dummy_index4, self.message4)
        self.messages_list.tableView.resizeColumnsToContents()
        self.messages_list.tableView.resizeRowsToContents()


class FPMenu(QtGui.QWidget):
    def __init__(self, parent):
        super(FPMenu, self).__init__(parent)
        self.menu = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/FPMenu.ui"), self)
        self.parent().root_window.setCentralWidget(self.menu)
        self.parent().root_window.setFocusProxy(self.menu.pushButton_5)
        # self.parent().root_window.setFocus(QtCore.Qt.OtherFocusReason)
        self.menu.pushButton_5.clicked.connect(self.new_user_slot)
        self.menu.pushButton_6.clicked.connect(self.new_base)

    def new_user_slot(self):
        ManageUsersScreen(self.parent())

    def new_base(self):
        CreateBaseBox(self.parent())


class ManageUsersScreen(QtGui.QWidget):
    """
    The UI to manage users.
    """
    # TODO: options to create and terminate contracts, change users job and set up an interim period.
    # Dbl click to view career.
    def __init__(self, parent):
        super(ManageUsersScreen, self).__init__(parent)
        self.new_user_box = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/ManageUsers.ui"), self)
        self.parent().root_window.setCentralWidget(self.new_user_box)
        # No modifications of an existing username are allowed so that history remains consistent
        # This means that creation needs to be online-only.
        # Other actions can be based on "career" table with begin + end dates.
        # A "jobs permissions" table should exist on a per-base basis, serving as an authorization matrix.

        self.model = QtGui.QStandardItemModel()
        self.filtered_model = QtGui.QSortFilterProxyModel()
        self.filtered_model.setSourceModel(self.model)
        self.base_model = None

        self.make_list()
        # Combos change -> filter list.

        self.new_user_box.tableView.setModel(self.filtered_model)
        self.new_user_box.tableView.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft)
        self.new_user_box.baseCombo.setModel(self.base_model)

        # Generate usernames : get the international users column and parse it. Append a number for dupes.
        # Manage : does changing a user's role invalidate the previous one ? serial numbers, dates, both ?
        # proposal : if username equal, propose new profile with a number behind the scenes. What about interims ?

        self.new_user_box.baseCombo.activated.connect(self.filter_by_base)
        # self.new_user_box.pushButton.clicked.connect(self.core_create)

    # def core_create(self):
    #     login = self.new_user_box.userIDLineEdit.text().lower()
    #     first_name = self.new_user_box.firstNameLineEdit.text()
    #     last_name = self.new_user_box.lastNameLineEdit.text()
    #     base = self.new_user_box.baseCombo.currentText()
    #     H3Core.remote_create_user(login, 'YOUPIE', first_name, last_name)
    #     self.make_list()

    def filter_by_base(self):
        self.filtered_model.setFilterKeyColumn(4)
        self.filtered_model.setFilterFixedString(self.new_user_box.baseCombo.currentText())

    def make_list(self):
        base_list = list()
        base_list.append("")
        self.model.setHorizontalHeaderLabels([_('Username'),
                                              _('First Name'),
                                              _('Last Name'),
                                              _('Current Job title'),
                                              _('Current Work base')])
        list_source = H3Core.get_visible_users()

        for row in list_source:
            row_list = []
            base_list.append(row[4])
            for value in row:
                row_list.append(QtGui.QStandardItem(value))
            self.model.appendRow(row_list)

        base_set = set(base_list)
        base_list = sorted(base_set)
        self.base_model = QtGui.QStringListModel(base_list)


class CreateBaseBox(QtGui.QWidget):
    """
    A UI to create a base. Talks to the remote DB - should have a way to warn user he can't work offline.
    Updates local DB immediately.
    """

    def __init__(self, parent):
        super(CreateBaseBox, self).__init__(parent)
        self.new_base_box = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/CreateBase.ui"), self)

        validator = QtGui.QRegExpValidator(QtCore.QRegExp("[A-Z]{3,3}"))
        self.new_base_box.baseCodeLineEdit.setValidator(validator)
        self.new_base_box.parentCodeLineEdit.setValidator(validator)

        H3Core.download_hierarchy()

        # Make the Qt SQL Database Object
        h3local = QtSql.QSqlDatabase('QSQLITE')
        h3local.setDatabaseName("H3ALocal.txt")
        h3local.open()
        # Make the table model from a single SQLite table
        self.table_model = QtSql.QSqlTableModel(None, h3local)
        self.table_model.setTable("bases")
        self.table_model.select()

        tree = TreeModel(self.table_model)

        self.new_base_box.tableView.setModel(self.table_model)
        self.new_base_box.treeView.setModel(tree)
        self.new_base_box.treeView.expandAll()
        self.new_base_box.treeView.resizeColumnToContents(0)

        self.table_model.dataChanged.connect(self.update_tree)
        self.new_base_box.pushButton.clicked.connect(self.create_base_gui)

        self.new_base_box.exec_()

    def update_tree(self):
        new_tree = TreeModel(self.table_model)
        self.new_base_box.treeView.setModel(new_tree)
        self.new_base_box.treeView.expandAll()
        self.new_base_box.treeView.resizeColumnToContents(0)

    def create_base_gui(self):
        base_code = self.new_base_box.baseCodeLineEdit.text()
        parent_code = self.new_base_box.parentCodeLineEdit.text()
        full_name = self.new_base_box.fullNameLineEdit.text()
        try:
            H3Core.remote_create_base(base_code, parent_code, full_name)
        except Exception as exc:
            msgbox = QtGui.QMessageBox(QtGui.QMessageBox.Information, _("Base invalid"),
                                       str(exc) + _("Please check that the parent code exists"), QtGui.QMessageBox.Ok)
            msgbox.setWindowIcon(QtGui.QIcon(":/GUI/images/H3.png"))
            msgbox.exec_()
        H3Core.download_hierarchy()
        self.table_model.select()
        self.update_tree()


class PMMenu(QtGui.QWidget):
    """
    There will be one class per screen or dialog of the interface.
    """

    def __init__(self, parent):
        super(PMMenu, self).__init__(parent)
        self.menu = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/ProjectMenu.ui"), self)
        self.parent().root_window.setCentralWidget(self.menu)
        self.parent().root_window.setFocusProxy(self.menu.pushButton_5)
        # self.parent().root_window.setFocus(QtCore.Qt.OtherFocusReason)
        self.menu.pushButton_5.clicked.connect(self.project_view)

    def project_view(self):
        self.parent().ui_switcher('project')


class ProjectMenu(QtGui.QWidget):
    """
    For now mostly a sandbox for model / view widgets testing, with interesting capabilities
    of SQLite table display / edit
    Can make a StandardItemModel representing a tree from a SQL Table model, extracting the
    parent / child relationship.
    """

    def __init__(self, parent):
        super(ProjectMenu, self).__init__(parent)
        self.menu = QtUiTools.QUiLoader().load(QtCore.QFile("GUI/QtDesigns/NewProjectMenu.ui"))
        self.parent().root_window.setCentralWidget(self.menu)

        # Make the Qt SQL Database Object
        h3local = QtSql.QSqlDatabase('QSQLITE')
        h3local.setDatabaseName("H3Alocal.txt")
        h3local.open()

        # Make a Pygal
        # bar_chart = pygal.Bar()
        # bar_chart.add('Fibonacci', [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55])
        #
        # scene = QtGui.QGraphicsScene()
        # bar_chart.render_to_file('KK.svg')
        # self.svgitem = QtSvg.QGraphicsSvgItem('KK.svg')
        # scene.addItem(self.svgitem)
        # self.menu.graphicsView.setScene(scene)
        # # self.menu.graphicsView.fitInView(self.svgitem, QtCore.Qt.KeepAspectRatioByExpanding)
        # self.menu.graphicsView.setDragMode(QtGui.QGraphicsView.DragMode.ScrollHandDrag)
        # scene.sceneRectChanged.connect(self.recenter)

        # Make the table model from a single SQLite table
        table_model = QtSql.QSqlTableModel(None, h3local)
        table_model.setTable("bases")
        table_model.select()

        # Extract unique parents from the table's second column
        parent_list = list()
        for row in range(0, table_model.rowCount()):
            parent_list.append(table_model.data(table_model.index(row, 1)))
        print parent_list
        parent_set = set(parent_list)
        sorted_parents = sorted(parent_set)
        print sorted_parents

        # Make a list model out of the unique parents string list
        list_model = QtGui.QStringListModel(sorted_parents)

        # Build the Tree Standard Item Model from the SQL Table
        tree_model = TreeModel(table_model)

        # each widget gets their model, with an extra manipulation on the ComboBox to preselect root
        self.menu.tableView.setModel(table_model)
        self.menu.comboBox.setModel(list_model)
        self.menu.treeView.setModel(tree_model)

        root_index = self.menu.comboBox.findData('root', QtCore.Qt.DisplayRole)
        self.menu.comboBox.setCurrentIndex(root_index)
        self.update_tree()
        self.paint_tree()

        # connect the various signals and slots - UI Switcher will default to current user's job
        self.menu.comboBox.activated.connect(self.update_tree)
        table_model.dataChanged.connect(self.update_tree)
        self.menu.pushButton.clicked.connect(self.parent().ui_switcher)

    def update_tree(self):
        new_base = self.menu.comboBox.currentText()
        new_tree = TreeModel(self.menu.tableView.model(), new_base)
        self.menu.treeView.setModel(new_tree)
        self.menu.treeView.expandAll()
        self.menu.treeView.resizeColumnToContents(0)

    def paint_tree(self):
        # Try to get every cell to be painted with a gradient
        gradient = QtGui.QLinearGradient()
        gradient.setCoordinateMode(QtGui.QGradient.StretchToDeviceMode)
        gradient.setStart(1, 0)
        gradient.setFinalStop(1, 1)
        gradient.setColorAt(1, QtCore.Qt.blue)
        gradient.setColorAt(0.24999999, QtCore.Qt.blue)
        gradient.setColorAt(0.24, QtCore.Qt.white)
        gradient.setColorAt(0, QtCore.Qt.white)
        gradbrush = QtGui.QBrush(gradient)

        model = self.menu.treeView.model()
        root = model.invisibleRootItem()

        tree_row = [root]
        next_row = list()
        while tree_row:
            for node in tree_row:
                node.setBackground(gradbrush)
                for child_no in range(0, node.rowCount()):
                    next_row.append(node.child(child_no))
            tree_row = next_row
            next_row = list()


class TreeModel(QtGui.QStandardItemModel):
    """
    Builds a tree model from a SQL Table model, where second column holds the parent.
    Root should have 'root' as a parent
    """

    def __init__(self, sql_source, root='root'):
        super(TreeModel, self).__init__()
        self.clear()

        # headers = list()
        # for i in range(0, sql_source.columnCount()):
        # headers.append(sql_source.headerData(i, QtCore.Qt.Horizontal))
        headers = ('Base code', 'Full name')

        self.setHorizontalHeaderLabels(headers)
        # self.setColumnCount(len(headers))
        self.setColumnCount(2)

        tree_row = list()
        self.invisibleRootItem().setData(root)
        invisible_root = self.invisibleRootItem()
        tree_row.append(invisible_root)
        next_row = list()

        while tree_row:  # current tree row, will end up empty as we get to the last row with no children
            for node in tree_row:
                node_name = node.data()
                for row in range(0, sql_source.rowCount()):  # read all lines from source's AbstractView super
                    record = list()
                    for column in range(0, sql_source.columnCount()):
                        index = sql_source.index(row, column)
                        if index is not None:
                            data = sql_source.data(index)
                            if data is not None:
                                record.append(data)  # this builds records as a list of 3 strings

                    record_parent = record[1]
                    if record_parent == node_name and record_parent != record[0]:
                        item = QtGui.QStandardItem(record[0])  # make a tree item out of the current record
                        # item.setSizeHint(QtCore.QSize(200, 100))
                        desc = QtGui.QStandardItem(record[2])  # make another one for description
                        item.setData(record[0])
                        desc.setData(record[2])
                        node.appendRow(item)  # set child relationship
                        node.setChild(node.rowCount() - 1, 1, desc)  # put description in column 2
                        next_row.append(item)
            tree_row = next_row
            next_row = []


def run():
    h3app = QtGui.QApplication(sys.argv)
    H3MainGUI()
    h3app.exec_()


def init_remote(location, password):
    H3Core.init_remote(location, password)


def nuke_remote(location, password):
    H3Core.nuke_remote(location, password)
