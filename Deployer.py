#!/usr/bin/python
# TODO: config file, TESTING, IO encoding/decoding, empty directories with permissions...
import re, os, sys, io, time

class Options:
	defaults = {
		"dry": False,
		"configFile": "deploy.ini",
		"logFile": "deployer.log",
		"section": None,
		"confirm": True,
		"quiet": False,
		"log": True,
		"host": None,
		"username": None,
		"password": None,
		"path": None,
		"_ignored": []
	}
	
	def __init__ (self):
		for option, value in self.defaults.items():
			setattr(self, option, value)
	
	@property
	def ignored (self):
		return self._ignored
	
	@ignored.setter
	def ignored (self, value):
		self._ignored += value.split(':') if isinstance(value, str) else value
	
	def __iadd__ (self, options):
		for option, value in options.__dict__.items():
			if value != self.defaults[option]:
				setattr(self, option, value)
		return self
	
	def __repr__ (self):
		return 'Options({0})'.format(repr(self.__dict__));
	
	def __setitem__ (self, attr, value):
		setattr(self, attr, value)

class ArgumentOptionsParser:
	def load (self):
		"""
		Parse command line arguments
		"""
		from argparse import ArgumentParser
		options = Options()
		parser = ArgumentParser(description = "Deploy web applications to an FTP server")
		parser.add_argument("-d", "--dry-run", dest = "dry", action = "store_true", help = "Perform a check without changing the files at the destination")
		parser.add_argument("-c", "--config-file", dest = "configFile", help = "The name of the (optional) configuration file (defaults to {0})".format(options.configFile))
		parser.add_argument("-s", "--section", dest = "section", help = "The section of a configuration file to read from")
		parser.add_argument("-y", "--yes", dest = "confirm", action = "store_false", help = "Apply changes without confirmation (Use reasonably)")
		parser.add_argument("-q", "--quiet", dest = "quiet", action = "store_true", help = "Process the script quietly, without any output")
		parser.add_argument("-l", "--no-logging", dest = "log", action = "store_true", help = "Don't log anything on the server")
		parser.add_argument("-a", "--address", dest = "host", help = "FTP server address")
		parser.add_argument("-u", "--username", dest = "username", help = "FTP server username")
		parser.add_argument("-p", "--password", dest = "password", help = "FTP server password")
		parser.add_argument("-i", "--ignore", dest = "ignored", nargs = "+", action = "append", help = "Ignored files/directories")
		parser.add_argument("--path", dest = "path", help = "Path to the root of the application on the FTP server")
		for key, value in parser.parse_args().__dict__.items():
			if value:
				options[key] = value
		return options

class ConfigOptionsParser:
	commonSection = "common"
	
	def load (self, configFile, section = None):
		"""
		Load and parse the configuration file
		"""
		import configparser
		options = Options()
		parser = configparser.ConfigParser()
		parser.read(configFile)
		try:
			for option, value in parser.items(self.commonSection):
				options[option] = value
		except configparser.NoSectionError:
			pass
		if section:
			try:
				for option, value in parser.items(section):
					options[option] = value
			except configparser.NoSectionError:
				pass
		return options
	
	def loadJson (self, configFile, configSection = None):
		import json
		options = Options()
		with open(configFile, 'r') as data:
			config = json.loads(config)
			for section in (self.commonSection, configSection)
				try:
					for option, value in config[section].items():
						options[option] = value
				except KeyError:
					pass
		return options

class Deployer:
	"""
	The script's controller class
	"""
	noticeColor = 36
	errorColor = 31
	
	ignorePatterns = None
	
	sourceFiles = {}
	updatedFiles = {}
	redundantFiles = []
	
	def isIgnored (self, fileName):
		"""
		Check if given file should be ignored according to configuration
		"""
		if fileName == self.options.configFile:
			return True
		if self.ignorePatterns is None:
			self.ignorePatterns = []
			try:
				for item in self.options.ignored:
					if item.endswith("/"):
						item = item + ".*"
					self.ignorePatterns.append(re.compile(item))
			except AttributeError:
				pass
		for rule in self.ignorePatterns:
			if rule.match(fileName):
				return True
		return False
	
	def connect (self):
		"""
		Connect to FTP server
		"""
		options = self.options
		try:
			self.connection = FTPConnection(options.host, options.username, options.password, options.path)
		except ConnectionError as error:
			self.output(str(error), error = True)
			sys.exit(1)
	
	def getSourceFiles (self, source):
		"""
		Get a file name: file sum dictionary of source files
		"""
		if not self.sourceFiles:
			for fileName, fileSum in source.getFiles():
				if not self.isIgnored(fileName):
					self.sourceFiles[fileName] = fileSum
		return self.sourceFiles
	
	def getUpdatedFiles (self, source, destination):
		"""
		Get a file name: file sum dictionary of updated files
		"""
		if not self.updatedFiles:
			for fileName, fileSum in self.getSourceFiles(source).items():
				if not (destination.hasFile(fileName) and destination.getHash(fileName) == fileSum):
					self.updatedFiles[fileName] = fileSum
		return self.updatedFiles
	
	def getRedundantFiles (self, source, destination):
		"""
		Get a list of files that are no longer present in the source but are still in the destination
		"""
		if not self.redundantFiles:
			self.redundantFiles = destination.getFileList()
			for fileName in (list(self.getSourceFiles(source).keys()) + [self.options.logFile]):
				if fileName in self.redundantFiles:
					self.redundantFiles.remove(fileName)
		return self.redundantFiles
	
	def renameUpdatedFiles (self, destination, updatedFiles, listener = None):
		"""
		Rename successfully updated files in the destination
		"""
		if listener:
			fileCount = len(updatedFiles)
			finished = 0
		for fileName in updatedFiles:
			destination.rename(fileName + ".new", fileName)
			if listener:
				finished += 1
				listener.setValue((finished/fileCount) * 100)
		if listener:
			listener.finish()
	
	def run (self, options):
		"""
		Process the deployment
		"""
		self.options = options
		self.connect()
		destination = Destination(self, self.connection)
		source = Source(self, os.getcwd())
		sourceFiles = self.getSourceFiles(source)
		updatedFiles = self.getUpdatedFiles(source, destination)
		updatedFileNames = sorted(updatedFiles.keys())
		redundantFiles = self.getRedundantFiles(source, destination)
		if updatedFiles:
			self.output("Files to be uploaded:", important = True)
			self.output("\n".join(updatedFileNames))
		else:
			self.output("No files to be uploaded.", important = True)
		if redundantFiles:
			self.output("Files to be deleted:", important = True)
			self.output("\n".join(redundantFiles))
		if not options.dry and (updatedFiles or redundantFiles):
			if options.confirm and not options.quiet:
				self.confirm("Do you want to apply these changes?")
			if updatedFiles: 
				self.output("Uploading new files...", important = True) 
				for fileName in updatedFileNames:
					destination.upload(fileName)
			if redundantFiles: 
				self.output("Removing redundant files...", important = True) 
				for fileName in redundantFiles:
					destination.remove(fileName)
			self.renameUpdatedFiles(destination, updatedFiles, self.getListener("Renaming successfully uploaded files"))
			destination.rebuildFileList(sourceFiles)
			self.log(updatedFiles, redundantFiles)
	
	def log (self, updatedFiles, redundantFiles):
		"""
		Log changes to a file in the destination
		"""
		if self.options.log:
			with io.StringIO() as logFile:
				self.output("Logging changes...", important = True)
				try:
					self.connection.download(self.options.logFile, logFile)
					logFile.read() # We want to append to the log file
				except FileNotFoundError:
					pass
				date = time.strftime("%d/%b/%Y %H:%M", time.gmtime())
				changeList = []
				if updatedFiles:
					changeList.append("\t" + "Updated Files:")
					for fileName in sorted(updatedFiles.keys()):
						changeList.append("\t\t" + fileName)
				if redundantFiles:
					changeList.append("\t" + "Removed Files:")
					for fileName in redundantFiles:
						changeList.append("\t\t" + fileName)
				logFile.write("[{0}]\n{1}\n".format(date, "\n".join(changeList)))
				self.connection.upload(logFile, self.options.logFile, safe = True)
	
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
	
	def getListener (self, message):
		"""
		Get a progress listener
		"""
		return Progressbar(message) if not self.options.quiet else None
	
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
	
	def remove (self, fileName):
		"""
		Remove a file on the server
		"""
		try:
			self.ftp.delete(fileName)
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
			remotePath = self.getSafeFilename(remotePath)
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
	
	def getSafeFilename (self, filename):
		return filename + '.new'

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
	
	files = []
	dirs = []
	
	def __init__ (self, controller, path = None):
		"""
		Set up the source object, get a list of available files
		"""
		self.controller = controller
		self.scanFiles(path)
	
	def scanFiles (self, path = None):
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
			self.dirs.append(subdir + "/")
			self.scanFiles(subdir)
		self.files += result
	
	def getFiles (self):
		"""
		A generator of (File name, File's hash) tuples
		"""
		import hashlib
		for fileName in self.files:
			try:
				yield (fileName, hashlib.sha1(open(fileName, "rb").read()).hexdigest())
			except IOError:
				pass
			
	def getDirs (self):
		"""
		Get a list of subdirectories in the source
		"""
		return self.dirs

class Destination:
	"""
	An object representation of the deployment's destination
	"""
	def __init__ (self, controller, connection):
		"""
		Set up the destination object
		"""
		self.controller = controller
		self.connection = connection
		self.files = DestinationInfo(controller, self.connection)
	
	def getRedundantFiles (self, sourceFiles):
		"""
		Get a list of files that are no longer present in the source but remain in the destination
		"""
		result = self.files.getNames()
		for fileName in sourceFiles.keys():
			if fileName in result:
				result.remove(fileName)
		return result
	
	def getFileList (self):
		return self.files.getNames()
	
	def download (self, path, fileName):
		"""
		Download a file from the destination
		"""
		try:
			with open(fileName, "wb") as destinationFile:
				self.connection.download(path, destinationFile, self.controller.getListener(fileName))
		except FileNotFoundError:
			os.remove(fileName)
			raise FileNotFoundError
	
	def mkdir (self, path):
		"""
		Create a directory in the destination with its permissions preserved
		"""
		perms = oct(os.stat(path).st_mode & 0o777).split("o")[1]
		self.connection.mkdir(path)
		self.connection.chmod(path, perms)
	
	def upload (self, path, fileName = None, rename = False):
		"""
		Upload a file to the destination
		"""
		if fileName is None:
			fileName = path
		with open(path, "rb") as sourceFile:
			self.connection.upload(sourceFile, fileName, safe = True, rename = rename, listener = self.controller.getListener(fileName))
		fileStat = os.stat(path)
		perms = oct(fileStat.st_mode & 0o777).split("o")[1]
		self.connection.chmod(self.connection.getSafeFilename(path) if not rename else path, perms)
	
	def rename (self, original, new):
		"""
		Rename a file in the destination
		"""
		self.connection.rename(original, new)
	
	def remove (self, fileName):
		"""
		Remove a file from the destination
		"""
		self.controller.output("Removing {0}...".format(fileName))
		try:
			self.connection.remove(fileName)
		except FileNotFoundError:
			pass
	
	def rebuildFileList (self, sourceFiles):
		"""
		Parse the list of source files into a new destination info file
		"""
		self.files.rebuild(sourceFiles)
	
	def hasFile (self, fileName):
		"""
		Is given file name present in the destination?
		"""
		return fileName in self.files
		
	def getHash (self, fileName):
		"""
		Get the hash of given file
		"""
		return self.files[fileName]

class DestinationInfo:
	"""
	An object representation of the file contatining the information about the destination
	"""
	files = {}
	
	def __init__ (self, controller, connection, objectsFileName = ".objects"):
		"""
		Try to download the destination information file from the server and parse it
		"""
		self.connection = connection
		self.controller = controller
		self.objectsFileName = objectsFileName
		with io.StringIO() as objectsFile:
			try:
				connection.download(objectsFileName, objectsFile, listener = controller.getListener("Getting object list"))
				for line in objectsFile:
					(objectName, objectHash) = line.split(":")
					self.files[objectName.strip()] = objectHash.strip()
			except FileNotFoundError:
				pass
	
	def __getitem__ (self, fileName):
		"""
		Get a file's hash
		"""
		return self.files[fileName]
	
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
	
	def rebuild (self, sourceFiles):
		"""
		Create a new destination information file and upload it to the destination
		"""
		with io.StringIO() as objectsFile:
			objectsFile.write("\n".join(["{0}: {1}".format(fileName, fileSum) for fileName, fileSum in sourceFiles.items()]))
			self.connection.upload(objectsFile, self.objectsFileName, safe = True, listener = self.controller.getListener("Updating object list"))

if __name__ == "__main__":
	deployer = Deployer()
	try:
		args = ArgumentOptionsParser().load()
		config = ConfigOptionsParser().load(args.configFile, args.section)
		config += args
		deployer.run(config)
	except KeyboardInterrupt:
		deployer.interrupt()