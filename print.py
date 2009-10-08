#!/usr/bin/env python

try:
    import pygtk
    pygtk.require( "2.0" )
except ImportError:
    print "You need to install pygtk!"
    raise SystemExit
import gtk
import sys
import os
import re
try:
    import pexpect
except ImportError:
    print "You need to install pexpect!\neg. sudo apt-get install pexpect"
    raise SystemExit
import base64
import cPickle
from subprocess import *
from exceptions import Exception

class GetPrinterError(Exception):
    pass

class Printer:
    """
    Printer handler
    """
    printers = []
    known_printers = {
        "ituniv-pa-443c-laser1": "Torg green (1st year SE&M)",
        "ituniv-pa-469-laser1": "Torg orange (2nd year SE&M)",
        "ituniv-pa-234-laser1":  "By the scanner",
        "ituniv-pa-227-laser1":  "By basic",
        }

    def __init__(self):
        self.printers = self.known_printers.items()

    def getDefaultPrinter(self):
        # TODO: get from saved list
        return self.printers[0][0]

    def get_printers(self):
        itu_printers = []
        output = ""
        try:
            output = pexpect.run("lpstat -d -p", timeout=3)
        except pexpect.ExceptionPexpect:
            print "Could not run lpstat"
        for i in output.rsplit("\n"):
            if re.findall("itu",i):
                itu_printers.append(i.rsplit(" ")[1])

        if not itu_printers:
            raise GetPrinterError()

        locations = {}
        
        for printer_name in itu_printers: 
            locations[printer_name.strip()] = ""

        locations.update(self.known_printers)
        locations = locations.items()
        locations.sort()
        return locations

    def update_printers(self):
        # fetch all available printers
        self.printers = self.get_printers()
        
class PrintApp( object ):
    """
    A printing application that logs in to kerberos and provides an easy
    to use GUI for printing.

    A file can be passed at the command-line, eg. "printApp.py spamspam.pdf", or
    selected in with the GUI. 

    Printers are loaded using cups.

    It also tries to catch and notify the user of any error that occurs. A more
    elaborate output is printed to stdout.

    TODO:
    * Add more printer descriptions.
    * Make folders unselectable
    """

    printer = None
    fileToPrint = None
    options = ""
    copies = 1
    loggedIn = 0
    save = False
    loginDetails = {}
    glade_file = "print.glade"
    printerHandler = Printer()

    # Messages
    loadPrinterError = "Could not find which printers are available, are you connected to the network?"
    loadPrinterErrorStatusBar = "Error: Could not load printers"
    connectionRefusedErrorStatusbar = "Error: Connection refused"
    connectionRefusedError = "The connection to the printer was refused"
    choosePrinterMsg = "Choose a printer!"
    chooseFileMsg = "Choose a file!"
    enterRangeMsg = "Enter a range!"
    enterCidMsg = "Enter your CID!"
    enterPasswordMsg = "Enter your password!"
    doneMsg = "Done!"
    doneMsgStatusbar = "Done!"
    loggedOutMsg = "Logged out"
    startPrintingMsg = "Starting to print..."
    timeoutError = "Call to lpr timed out"
    timeoutErrorStatusbar = "Error: request timed out"
    loadingPrintersMsg = "Loading printers..."
    printingMsgStatusbar = "Printing..."
    fileNotFoundError = "No such file"
    fileNotFoundErrorStatusbar = "File not found"
    cupsError = "The printer or class was not found"
    cupsErrorStatusbar = "You need a .cups.rc file. See wiki.ituniv.org"
    kerberosError = "Do you have kerberos installed?\napt-get install krb-5-kdc"
    kerberosErrorStatusbar = "Do you have kerberos installed? See wiki.ituniv.org"
    gladeError = """printApp: Cannot find '%s', or the file is corrupt"""

    def __init__( self ):
        self.loadWidgets()
        self.setDefaultValues()
        self.loadSettings()
        
    def loadSettings(self):
        try:
            FILE = open(".printappsettings")
            loginDetails = cPickle.load(FILE)
            if loginDetails:
                print loginDetails
                try:
                    self.save = True
                    self.saveLogin.set_active(True)
                    self.cidEntry.set_text(loginDetails["login"])
                    self.passwordEntry.set_text(base64.b64decode(loginDetails["pass"]))
                    self.setPrinter(loginDetails["printer"])
                except KeyError:
                    print "Setting file corrupt, skipping..."

        except IOError:
            pass

    def setDefaultValues(self):
        self.copiesSpin.set_value(1)
        self.printButton .grab_focus()
        self.isLoggedIn()
        self.setPrinter(self.printerHandler.getDefaultPrinter())
        
    def loadWidgets(self):
        builder = gtk.Builder()
        (path, filename) = os.path.split(os.path.abspath(__file__))
        gladePath = os.path.join(path, self.glade_file)
        try:
            builder.add_from_file( gladePath )
        except:
            print self.gladeError % self.glade_file
            raise SystemExit

        self.win              = builder.get_object( "window1" )
        self.fileButton       = builder.get_object( "fileButton" )
        self.printerButton    = builder.get_object( "printerButton" )
        self.fileLabel        = builder.get_object( "fileLabel" )
        self.printerLabel     = builder.get_object( "printerLabel" )
        self.doubleSidedCheck = builder.get_object( "doubleSidedCheck" )
        self.copiesSpin       = builder.get_object( "copiesSpin" )
        self.printDialog      = builder.get_object( "printDialog" )
        self.statusBar        = builder.get_object( "statusBar" )
        self.cidEntry         = builder.get_object( "cidEntry" )
        self.passwordEntry    = builder.get_object( "passwordEntry" )
        self.saveLogin        = builder.get_object( "saveLogin" )
        self.rangeEntry       = builder.get_object( "rangeEntry" )
        self.rangeRadio       = builder.get_object( "rangeRadio" )
        self.printButton      = builder.get_object( "printButton" )
        self.logoutButton     = builder.get_object( "logoutButton" )
        self.printDialog      = builder.get_object( "printDialog" )
        self.dataStore        = builder.get_object( "dataStore" )
        self.treeView         = builder.get_object( "treeView" )

        builder.connect_signals( self )

    # Callbacks
    def on_logoutButton_clicked( self, button ):
        os.popen("kdestroy")
        print self.loggedOutMsg
        self.hideLogoutButton()
 
    def on_printButton_clicked( self, button ):
        if self.updateStatusbar(None):
            self.CID = self.cidEntry.get_text()
            self.password = self.passwordEntry.get_text()
            self.doSaveLogin()
            self.startPrinting()

    def on_rangeRadio_toggled( self, button ):
        self.rangeEntry.set_sensitive(True)
    
    def on_allPagesRadio_toggled( self, button ):
        self.rangeEntry.set_sensitive(False)

    def on_saveLogin_toggled( self, button ):
        if button.get_active():
            self.save = True
        else:
            self.save = False

    def on_fileButton_clicked( self, button ):
        builder = gtk.Builder()
        builder.add_from_file( self.glade_file )
        fileChooser = builder.get_object( "fileChooser" )
        if fileChooser.run() is 0:
            self.setFileToPrint( fileChooser.get_filename() )
        fileChooser.hide()
        fileChooser.destroy()
        self.updateStatusbar(None)
        
        
    def gtk_main_quit( self, object ):
        gtk.main_quit()

    def on_copiesSpin_value_changed( self, button ):
        self.copies = button.get_adjustment().get_value()

    def on_printerButton_clicked( self, button ):
        try:
            self.printerHandler.update_printers()
        except GetPrinterError:
            print "Could not get printers"
        self.dataStore.clear()
        self.fill_dataStore( self.dataStore )
        
        if self.printDialog.run() is 0:
            (model, iterator) = self.treeView.get_selection().get_selected()
            if iterator:
                self.setPrinter(model.get_value(iterator,column=0))

        self.printDialog.hide()

    # Functions
    def setPrinter(self, selectedPrinter):
        self.printer = selectedPrinter
        self.printerLabel.set_text(selectedPrinter)
        
    def fill_dataStore( self, dataStore ):
        for printer in self.printerHandler.printers:
            dataStore.append(printer)

    def parseArgs(self):
        args = sys.argv[1:]
        if len(args) > 0:
            theFile = []
            for x in args:
                theFile.append(x)
                theFile.append(" ")
            self.setFileToPrint( "".join(theFile).rstrip() )
            

    def setFileToPrint(self, filePath):
        (_, _, last) = filePath.rpartition("/")
        self.fileLabel.set_text( "".join(last) )
        self.fileToPrint = filePath

    def doSaveLogin( self ):
        print "SAving mode?", self.save
        if self.save:
            self.loginDetails = {'login': self.CID, 
                                     'pass': base64.b64encode(self.password),
                                     'printer': self.printer}
        else:
            self.loginDetails = {}
        FILE = open(".printappsettings", 'w')
        cPickle.dump(self.loginDetails, FILE)
        
    def startPrinting( self ):
        if not self.isLoggedIn():
            try:
                s = pexpect.spawn("kinit %s@CHALMERS.SE" % self.CID)
            except pexpect.ExceptionPexpect:
                print self.kerberosError
                self.updateStatusbar(self.kerberosErrorStatusbar)
            else:
                try: 
                    s.expect("Password for %s@CHALMERS.SE:" % self.CID)
                except pexpect.EOF:
                    print "User not found: " + s.before
                    self.updateStatusbar("User not found")
                    self.cidEntry.grab_focus()
                else:
                    s.sendline(self.password)
                    s.expect(pexpect.EOF)
                    if not self.isLoggedIn():
                        print "Wrong password " + s.before
                        self.updateStatusbar("Wrong password")
                        self.passwordEntry.grab_focus()

                    else:
                        self.callLpr()
        else:
            self.callLpr()

    def getOptionsString(self):
        if self.doubleSidedCheck.get_active():
            self.doubleSided = ""
        else:
            self.doubleSided = "sides=one-sided"

        if self.rangeRadio.get_active():
            self.rangeToPrint = "".join(["page-ranges=", self.rangeEntry.get_text()])
        else:
            self.rangeToPrint = ""

        if self.rangeToPrint or self.doubleSided:
            self.options = "-o " + self.rangeToPrint +" "+ self.doubleSided
        

    def callLpr(self):
        self.getOptionsString()
       
        s = pexpect.spawn("""lpr -P %s -U %s -#%d "%s" %s""" % 
                          (self.printer, self.CID, 
                           self.copies, self.fileToPrint,
                           self.options))
        print s.args
        try:
            s.expect(pexpect.EOF, timeout=10)
        except pexpect.TIMEOUT:
            print self.timeoutError
            self.updateStatusbar(self.timeoutErrorStatusbar)
            return
        if  re.findall("No such file",s.before):
            print s.before
            print self.fileNotFoundError
            self.updateStatusbar(self.fileNotFoundErrorStatusbar)
        elif  re.findall("printer or class",s.before):
            print self.cupsError
            self.updateStatusbar(self.cupsErrorStatusbar)
        elif  re.findall("refused",s.before):
            print s.before,
            print self.connectionRefusedError
            self.updateStatusbar(self.connectionRefusedErrorStatusbar)
        else:
            print s.before,
            print self.doneMsg
            self.updateStatusbar(self.doneMsgStatusbar)

    def isLoggedIn( self ):
        """
        Returns true/false if logged in
        """
        str_list = []
        ret = os.popen("klist 2> /dev/null")
        for i in ret:
            str_list.append(i)
        result = "".join(str_list)
        if re.findall("CHALMERS", result):
            self.updateStatusbar("Logged in")
            self.showLogoutButton()
            self.loggedIn = 1
            return True
        else:
            return False

    def showLogoutButton( self ):
        self.logoutButton.show()
        self.cidEntry.set_sensitive(False)
        self.passwordEntry.set_sensitive(False)

    def hideLogoutButton( self ):
        self.logoutButton.hide()
        self.cidEntry.set_sensitive(True)
        self.passwordEntry.set_sensitive(True)

    def updateStatusbar( self, msg ):
        """
        If msg is None this function checks if all fields are
        filled in correctly, and updates the statusbar if they
        are not.
        If msg is _not_ None the statusbar is updated with msg.
        """
        ret_val = True
        if not hasattr(self, "contextId"):
            self.contextId = self.statusBar.get_context_id("print_status")
        if msg is None:
            ret_val = False
            if self.printer is None:
                msg = self.choosePrinterMsg
                self.printerButton.grab_focus()
            elif self.rangeRadio.get_active() and \
                    self.rangeEntry.get_text_length() is 0:
                msg = self.enterRangeMsg
                self.rangeEntry.grab_focus()
            elif self.fileToPrint is None:
                msg = self.chooseFileMsg
                self.fileButton.grab_focus()
            elif self.cidEntry.get_text_length() is 0 and not self.loggedIn:
                msg = self.enterCidMsg
                self.cidEntry.grab_focus()
            elif self.passwordEntry.get_text_length() is 0 and not self.loggedIn:
                msg = self.enterPasswordMsg
                self.passwordEntry.grab_focus()
            else:
                #print self.startPrintingMsg
                msg = ""
                ret_val = True
            
        self.statusBar.pop(self.contextId)
        self.statusBar.push(self.contextId, msg)
        return ret_val

if __name__ == "__main__":
    app = PrintApp()
    app.parseArgs()
    app.win.show()
    gtk.main()
