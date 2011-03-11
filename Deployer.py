#!/usr/bin/python
# TODO: config file, TESTING, IO encoding/decoding, empty directories with permissions...
import re, os, sys, io, time

class Deployer:
	"""
	The script's controller class
	"""
	noticeColor = 36
	errorColor = 31
	ignoreDirs = None
	commonSection = "common"
	configFileName = "deploy.ini"
	logFileName = "deployer.log"
	
	def __init__ (self):
		"""
		Set up the deployer
		"""
		self.options = Namespace()
	
	def loadArgs (self):
		"""
		Parse command line arguments
		"""
		from argparse import ArgumentParser
		parser = ArgumentParser(description = "Deploy web applications to an FTP server")
		parser.add_argument("-d", "--dry-run", dest = "dry", default = False, action = "store_true", help = "Perform a check without changing the files at the destination")
		parser.add_argument("-c", "--config-file", dest = "config", default = self.configFileName, help = "The name of the configuration file")
		parser.add_argument("-s", "--section", dest = "section", default = None, help = "The section of a configuration file to read from")
		parser.add_argument("-y", "--yes", dest = "confirm", default = True, action = "store_false", help = "Apply changes without confirmation (Use reasonably)")
		parser.add_argument("-q", "--quiet", dest = "quiet", default = False, action = "store_true", help = "Process the script quietly, whithout any output")
		parser.add_argument("-l", "--no-logging", dest = "log", default = True, action = "store_true", help = "Don't log anything on the server")
		parser.add_argument("-a", "--address", dest = "host", default = None, help = "FTP server address")
		parser.add_argument("-u", "--username", dest = "username", default = None, help = "FTP server username")
		parser.add_argument("-p", "--password", dest = "password", default = None, help = "FTP server password")
		parser.add_argument("--path", dest = "path", default = None, help = "Path to the root of the application on the FTP server")
		parser.parse_args(namespace = self.options)
	
	def loadConfig (self, path = None):
		"""
		Load and parse the configuration file
		"""
		import configparser
		parser = configparser.ConfigParser()
		parser.read(self.options.config)
		try:
			for option, value in parser.items(self.commonSection):
				setattr(self.options, option, value)
		except configparser.NoSectionError:
			pass
		if self.options.section:
			try:
				for option, value in parser.items(self.options.section):
					setattr(self.options, option, value)
			except configparser.NoSectionError:
				self.output("There is no section named {0} in the configuration file".format(self.options.section), error = True) 
	
	def isIgnored (self, filename):
		"""
		Check if given file should be ignored according to configuration
		"""
		if filename == self.options.config:
			return True
		if self.ignoreDirs is None:
			self.ignoreDirs = []
			for item in self.options.ignoredirs.split(":"):
				if item.endswith("/"):
					item = item + ".*"
				self.ignoreDirs.append(re.compile(item))
		for rule in self.ignoreDirs:
			if rule.match(filename):
				return True
		return False
	
	def run (self):
		"""
		Process the deployment
		"""
		options = self.options
		try:
			self.connection = FTPConnection(options.host, options.username, options.password, options.path)
		except ConnectionError as error:
			self.output(str(error), error = True)
			sys.exit(1)
		destination = Destination(self, self.connection, self.options.quiet)
		source = Source(self, os.getcwd(), self.options.quiet)
		updatedFiles = {}
		sourceFiles = {}
		for filename, filesum in source.getFiles():
			if not self.isIgnored(filename):
				if not destination.isHashEqual(filename, filesum):
					updatedFiles[filename] = filesum
				sourceFiles[filename] = filesum
		updatedFileNames = sorted(updatedFiles.keys())
		if updatedFiles:
			self.output("Files to be uploaded:", important = True)
			self.output("\n".join(updatedFileNames))
		else:
			self.output("No files to be uploaded.", important = True)
		redundantFiles = destination.getRedundantFiles(sourceFiles)
		if self.logFileName in redundantFiles: 
			redundantFiles.remove(self.logFileName)
		if redundantFiles:
			self.output("Files to be deleted:", important = True)
			self.output("\n".join(redundantFiles))
		if not options.dry and (updatedFiles or redundantFiles):
			if options.confirm and not options.quiet:
				self.confirm("Do you want to apply these changes?")
			if updatedFiles: self.output("Uploading new files...", important = True) 
			for filename in updatedFileNames:
				destination.upload(filename)
			if redundantFiles: self.output("Removing redundant files...", important = True) 
			for filename in redundantFiles:
				destination.remove(filename)
			destination.applyChanges(updatedFiles, sourceFiles)
			if options.log:
				with io.StringIO() as logFile:
					self.output("Logging changes...", important = True)
					try:
						self.connection.download(self.logFileName, logFile)
						logFile.read() # We want to append to the log file
					except FileNotFoundError:
						pass
					date = time.strftime("%d/%b/%Y %H:%M", time.gmtime())
					changeList = []
					if updatedFiles:
						changeList.append("\t" + "Updated Files:")
						for filename in updatedFileNames:
							changeList.append("\t\t" + filename)
					if redundantFiles:
						changeList.append("\t" + "Removed Files:")
						for filename in redundantFiles:
							changeList.append("\t\t" + filename)
					logFile.write("[{0}]\n{1}\n".format(date, "\n".join(changeList)))
					self.connection.upload(logFile, self.logFileName, safe = True)
	
	def output (self, message, important = False, error = False, breakLine = True):
		"""
		Output a message on the screen
		"""
		if not self.options.quiet:
			stream = sys.stdout if not error else sys.stderr
			if error:
				message = "\033[00;{0}m{1}\033[0;0m".format(self.errorColor, "Error: ") + message
			elif important:
				message = "\033[00;{0}m{1}\033[0;0m".format(self.noticeColor, message)
			if breakLine:
				message = message + "\n"
			stream.write(message)
	
	def confirm (self, question):
		"""
		Ask for confirmation by user
		"""
		answer = input(question + " [Y/n] ")
		if not answer:
			return
		if answer[0].lower() != "y":
			self.interrupt()
	
	def interrupt (self):
		"""
		Stop the deployer from running and terminate it
		"""
		self.connection.disconnect()
		self.output("Deployer aborted", important = True)
		sys.exit(1)

class Namespace:
	"""
	A variable container object
	"""
	def __init__ (self, **kwargs):
		"""
		Set up the namespace, save construction arguments
		"""
		for key, value in kwargs.items():
			setattr(self, key, value)
	
	def __repr__ (self):
		"""
		Return a string representation of the namespace
		"""
		return "Namespace({0})".format(", ".join(["%s: %s" % (key, value) for key, value in self.__dict__.items()]))

import sys

class Progressbar:
	"""
	A class that manages progressbar rendering
	"""
	
	def __init__ (self, title):
		"""
		Set up the progressbar
		"""
		self.title = title
		self.columns = self.getConsoleWidth()
		self.titleLength = self.columns // 2
	
	def getConsoleWidth (self):
		"""
		Get the width of the terminal window
		"""
		rows, columns = os.popen('stty size', 'r').read().split()
		return int(columns)
	
	def truncateTitle (self, value):
		"""
		Shorten the progressbar's title so that it doesn't mess anything up
		"""
		if len(value) > self.titleLength:
			value = "..." + value[-(self.titleLength - 3) : ]
		else:
			value = value + (" " * (self.titleLength - len(value))) 
		return value
	
	def setValue (self, progress):
		"""
		Set the value of progressbar's progress and repaints it to show this progress
		"""
		self.progress = int(progress)
		self.repaint()
	
	def clear (self):
		"""
		Clear the progressbar's row
		"""
		for i in range(1, self.columns):
			sys.stdout.write("\b \b")
	
	def repaint (self, finish = False):
		"""
		Repaint the progressbar to keep it up to date with any changes
		"""
		self.clear()
		barLength = self.columns - self.titleLength - 4 - 2 - 2 # Percents, empty spaces and brackets
		bar = str()
		try:
			progress = self.progress
		except AttributeError: # If self.progress is not set, it means the rendering had finished before setting any value
			progress = 100
		for i in range(1, barLength):
			bar += "#" if (i / (barLength / float(100))) < progress else "-"
		percent = ("{0:3}".format(progress)) + "%"
		sys.stdout.write("{0} [{1}] {2}".format(self.truncateTitle(self.title), bar, percent))
		if not finish:
			sys.stdout.flush()
		else:
			sys.stdout.write("\n")
	
	def finish (self):
		"""
		Finalize the rendering of the progressbar
		"""
		self.progress = 100
		self.repaint(True)

import ftplib, socket, os

class FTPConnection:
	"""
	An FTP object envelope
	"""
	root = "/"
	bufferSize = 4096
	
	def __init__ (self, host, username, password, path = None):
		"""
		Set up the connection
		"""
		ftp = self.ftp = ftplib.FTP()
		try:
			ftp.connect(host)
		except socket.error:
			raise ConnectionError("Connecting to FTP server failed")
		try:
			ftp.login(username, password)
		except ftplib.error_perm:
			raise ConnectionError("Authentication failed")
		
		if path:
			if not path.startswith("/"):
				path = "/" + path
			self.cd(path)
			self.root = path
			self.cdRoot()
	
	def disconnect (self):
		"""
		Disconnect from FTP server
		"""
		self.ftp.quit()
	
	def cdRoot (self):
		"""
		Change the working directory to root
		"""
		self.ftp.cwd(self.root)
	
	def cd (self, path):
		"""
		Change the working directory to given path (if it doesn't exist, create it)
		"""
		try:
			self.ftp.cwd(path)
		except ftplib.error_perm:
			self.mkdir(path)
			self.ftp.cwd(path)
	
	def mkdir (self, path):
		"""
		Make a directory on the server
		"""
		path = path.strip("/")
		diff = path.split("/")
		self.cdRoot()
		existing = True
		for directory in diff:
			if directory:
				if existing:
					try:
						self.ftp.cwd(directory)
					except ftplib.error_perm:
						existing = False
						self.ftp.mkd(directory)
						self.ftp.cwd(directory)
				else:
					self.ftp.mkd(directory)
					self.ftp.cwd(directory)
		self.cdRoot()
	
	def rename (self, original, new):
		"""
		Rename a file on the server
		"""
		self.ftp.rename(original, new)
	
	def remove (self, filename):
		"""
		Remove a file on the server
		"""
		try:
			self.ftp.delete(filename)
		except ftplib.error_perm:
			raise FileNotFoundError
	
	def download (self, path, stream, listener = None):
		"""
		Download a file from the server into a stream (preferably binary)
		"""
		if listener:
			try:
				size = self.ftp.size(path)
			except ftplib.error_perm:
				size = 0
		self.ftp.voidcmd("TYPE I")
		try:
			connection = self.ftp.transfercmd("RETR {0}".format(path))
		except ftplib.error_perm:
			raise FileNotFoundError
		while True:
			fileBuffer = connection.recv(self.bufferSize)
			if not fileBuffer:
				if listener:
					listener.finish()
				stream.seek(0)
				break
			try:
				stream.write(fileBuffer)
			except TypeError: # We aren't a byte stream, are we?
				stream.write(fileBuffer.decode(stream.encoding if stream.encoding else "utf-8"))
			if listener:
				position = stream.tell()
				stream.seek(0)
				content = stream.read()
				stream.seek(position)
				if not isinstance(content, bytes):
					content = content.encode(stream.encoding if stream.encoding else "utf-8")
				percent = round((len(content)/float(size)) * 100) if size else 0
				listener.setValue(percent)
		connection.close()
		self.ftp.voidresp()
		self.cdRoot()
	
	def upload (self, stream, path, safe = False, rename = True, listener = None):
		"""
		Upload a stream (preferably binary) to the server
		"""
		stream.seek(0)
		if listener:
			size = len(stream.read())
			stream.seek(0)
			finished = 0
		slashPosition = path.rfind("/")
		if slashPosition < 0:
			slashPosition = False
		remotePath = path[slashPosition + 1 : ] if slashPosition else path
		if safe:
			originalPath = remotePath
			remotePath += ".new"
		if slashPosition:
			self.cd(path[0 : slashPosition])
		self.ftp.voidcmd("TYPE I")
		connection = self.ftp.transfercmd("STOR {0}".format(remotePath))
		while True:
			fileBuffer = stream.read(self.bufferSize)
			if not fileBuffer:
				if listener:
					listener.finish()
				break
			if not isinstance(fileBuffer, bytes):
				fileBuffer = fileBuffer.encode(stream.encoding if stream.encoding else "utf-8")
			sent = connection.send(fileBuffer)
			if listener:
				finished += sent
				if size is None:
					listener.setValue(0)
				else:
					listener.setValue(round((finished/float(size))*100))
		connection.close()
		self.ftp.voidresp()
		if safe and rename:
			self.rename(remotePath, originalPath)
		self.cdRoot()
	
	def chmod (self, path, perms):
		self.ftp.voidcmd("SITE CHMOD {0} {1}".format(perms, path))

class FileNotFoundError (BaseException):
	"""
	An error raised if a file was not found on the server
	"""

class ConnectionError (BaseException):
	"""
	An error raised if there is a problem with the connection
	"""

class Source:
	"""
	A representation of the local directory to be deployed
	"""
	def __init__ (self, controller, path = None, quiet = False):
		"""
		Set up the source object, get a list of available files
		"""
		self.controller = controller
		self.quiet = quiet
		self.files = self.scanFiles(path)
	
	def scanFiles (self, path):
		"""
		Scan the source directory for available files
		"""
		result = []
		subdirs = []
		if path is None:
			path = os.getcwd()
		for item in os.listdir(path):
			itemPath = os.path.join(path, item) if path != os.getcwd() else item
			if os.path.isdir(itemPath):
				subdirs.append(itemPath)
			else:
				result.append(itemPath)
		for subdir in subdirs:
			result += self.scanFiles(subdir)
		return result
	
	def getFiles (self):
		"""
		A generator of (File name, File's hash) tuples
		"""
		import hashlib
		for filename in self.files:
			try:
				yield (filename, hashlib.sha1(open(filename, "rb").read()).hexdigest())
			except IOError:
				pass

class Destination:
	"""
	An object representation of the deployment's destination
	"""
	def __init__ (self, controller, connection, quiet = False):
		"""
		Set up the destination object
		"""
		self.controller = controller
		self.connection = connection
		self.quiet = quiet
		self.files = DestinationInfo(self.connection)
	
	def isHashEqual (self, path, filesum):
		"""
		Check if the given file and hash correspond to the state of the destination
		"""
		if path in self.files:
			return self.files[path] == filesum
		else:
			return False
	
	def getRedundantFiles (self, sourceFiles):
		"""
		Get a list of files that are no longer present in the source but remain in the destination
		"""
		result = self.files.getNames()
		for filename in sourceFiles.keys():
			if filename in result:
				result.remove(filename)
		return result
	
	def download (self, path, filename):
		"""
		Download a file from the destination
		"""
		try:
			with open(filename, "wb") as destinationFile:
				self.connection.download(path, destinationFile, Progressbar(filename))
		except FileNotFoundError:
			os.remove(filename)
			raise FileNotFoundError
	
	def upload (self, path, filename = None, rename = False):
		"""
		Upload a file to the destination
		"""
		if filename is None:
			filename = path
		with open(path, "rb") as sourceFile:
			self.connection.upload(sourceFile, filename, safe = True, rename = rename, listener = Progressbar(filename) if not self.quiet else None)
		fileStat = os.stat(path)
		perms = oct(fileStat.st_mode & 0o777).split("o")[1]
		self.connection.chmod(path, perms)
	
	def remove (self, filename):
		"""
		Remove a file from the destination
		"""
		self.controller.output("Removing {0}...".format(filename))
		try:
			self.connection.remove(filename)
		except FileNotFoundError:
			pass
	
	def applyChanges (self, updatedFiles, sourceFiles):
		"""
		Update the destination information and rename the uploaded files to their original names
		"""
		self.files.update(sourceFiles)
		if not self.quiet:
			renaming = Progressbar("Renaming successfully uploaded files")
		fileCount = len(updatedFiles.keys())
		renamedFiles = 0
		for item in updatedFiles.keys():
			self.connection.rename(item + ".new", item)
			renamedFiles += 1
			if not self.quiet:
				renaming.setValue((renamedFiles/fileCount) * 100)
		if not self.quiet:
			renaming.finish()

class DestinationInfo:
	"""
	An object representation of a file contatining the information about the destination
	"""
	files = {}
	
	def __init__ (self, connection, quiet = False, objectsFileName = ".objects"):
		"""
		Try to download the destination information file from the server and parse it
		"""
		self.connection = connection
		self.quiet = quiet
		self.objectsFileName = objectsFileName
		with io.StringIO() as objectsFile:
			try:
				connection.download(objectsFileName, objectsFile, listener = Progressbar("Getting object list") if not self.quiet else None)
				for line in objectsFile:
					(objectName, objectHash) = line.split(":")
					self.files[objectName.strip()] = objectHash.strip()
			except FileNotFoundError:
				pass
	
	def __getitem__ (self, filename):
		"""
		Get a file's hash
		"""
		return self.files[filename]
	
	def __contains__ (self, key):
		"""
		Check if a file is present in the destination
		"""
		return key in self.files
	
	def getNames (self):
		"""
		Get a list of files present in the destination
		"""
		return list(self.files.keys())
	
	def update (self, data):
		"""
		Create a new destination information file and upload it to the destination
		"""
		with io.StringIO() as objectsFile:
			objectsFile.write("\n".join(["{0}: {1}".format(filename, filesum) for filename, filesum in data.items()]))
			self.connection.upload(objectsFile, self.objectsFileName, safe = True, listener = Progressbar("Updating object list") if not self.quiet else None)

if __name__ == "__main__":
	deployer = Deployer()
	try:
		deployer.loadArgs()
		deployer.loadConfig()
		deployer.run()
	except KeyboardInterrupt:
		deployer.interrupt()