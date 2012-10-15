#!/usr/bin/python
# TODO: config file, TESTING, IO encoding/decoding, empty directories with permissions...
import re, os, sys, io, time

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
	
	def run (self, connection, options):
		"""
		Process the deployment
		"""
		self.options = options
		self.connection = connection
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
		from Progressbar import Progressbar
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
	from FTPConnection import FTPConnection
	from Options import *
	deployer = Deployer()
	try:
		args = ArgumentOptionsParser().load()
		options = ConfigOptionsParser().load(args.configFile, args.section)
		options += args
		connection = FTPConnection(options.host, options.username, options.password, options.path)
		deployer.run(connection, options)
	except KeyboardInterrupt:
		deployer.interrupt()
	except ConnectionError as error:
		self.output(str(error), error = True)
		sys.exit(1)