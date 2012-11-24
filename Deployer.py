#!/usr/bin/python
# TODO: config file, TESTING, IO encoding/decoding, empty directories with permissions... exceptions
import re, os, sys, io, time

class Deployer:
	"""
	The script's controller class
	"""
	
	def __init__ (self, frontend = None):
		self.frontend = frontend
		
		self.ignorePatterns = None
		self.keepPatterns = None
		
		self.sourceFiles = {}
		self.updatedFiles = {}
		self.redundantFiles = []
	
	def parseFilePatterns (self, patterns):
		if patterns:
			for item in patterns:
				if item.endswith("/"):
					item = item + ".*"
				yield re.compile(item)
		else:
			return []
	
	def isIgnored (self, fileName):
		"""
		Check if given file should be ignored according to configuration
		"""
		if fileName == self.options.configFile:
			return True
		if self.ignorePatterns is None:
			try:
				self.ignorePatterns = list(self.parseFilePatterns(self.options.ignore))
			except AttributeError:
				pass
		for rule in self.ignorePatterns:
			if rule.match(fileName):
				return True
		return False
	
	def isKept (self, fileName):
		if self.keepPatterns is None:
			try:
				self.keepPatterns = list(self.parseFilePatterns(self.options.keep))
			except AttributeError:
				pass
		for rule in self.keepPatterns:
			if rule.match(fileName):
				return True
		return False
	
	def getSourceFiles (self, source):
		"""
		Get a file name: file sum dictionary of source files
		"""
		if not self.sourceFiles:
			self.sourceFiles = {name: checksum for name, checksum in source.getFiles() if not self.isIgnored(name)}
		return self.sourceFiles
	
	def getUpdatedFiles (self, source, destination):
		"""
		Get a file name: file sum dictionary of updated files
		"""
		if not self.updatedFiles:
			self.updatedFiles = {name: checksum for name, checksum in self.getSourceFiles(source).items() if not destination.hasFile(name, checksum)}
		return self.updatedFiles
	
	def getRedundantFiles (self, source, destination):
		"""
		Get a list of files that are no longer present in the source but are still in the destination
		"""
		if not self.redundantFiles:
			sourceFiles = list(self.getSourceFiles(source).keys()) + [self.options.logFile]
			self.redundantFiles = [name for name in destination.getFiles() if not name in sourceFiles]
		return self.redundantFiles
	
	def renameUpdatedFiles (self, destination, updatedFiles, listener = None):
		"""
		Rename successfully updated files in the destination
		"""
		if listener:
			fileCount = len(updatedFiles)
			finished = 0
		for fileName in updatedFiles:
			if (not self.isKept(fileName)) or (not destination.hasFile(fileName)):
				destination.rename(fileName + ".new", fileName)
			if listener:
				finished += 1
				listener.setValue((finished/fileCount) * 100)
		if listener:
			listener.finish()
	
	def generateObjects (self, options):
		self.options = options
		with open("objects", "w") as objectsFile:
			objectsFile.write('\n'.join([(name + ': ' + checksum) for name, checksum in self.getSourceFiles(Source(os.getcwd())).items()]))
	
	def run (self, connection, options):
		"""
		Process the deployment
		"""
		self.options = options
		self.connection = connection
		destination = Destination(self.connection)
		source = Source(os.getcwd())
		sourceFiles = self.getSourceFiles(source)
		destinationFiles = destination.getFiles(self.getListener("Getting object list"))
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
				if not self.confirm("Do you want to apply these changes?"):
					self.interrupt()
			if updatedFiles: 
				self.output("Uploading new files...", important = True) 
				for fileName in updatedFileNames:
					destination.upload(fileName, listener = self.getListener(fileName))
			if redundantFiles: 
				self.output("Removing redundant files...", important = True) 
				for fileName in redundantFiles:
					self.output("Removing {0}...".format(fileName))
					destination.remove(fileName)
			self.renameUpdatedFiles(destination, updatedFiles, self.getListener("Renaming successfully uploaded files"))
			destination.rebuildFileList(sourceFiles, self.getListener("Updating object list"))
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
		if self.frontend:
			self.frontend.output(message, important, error, breakLine)
	
	def getListener (self, message):
		"""
		Get a progress listener
		"""
		if self.frontend:
			listener = self.frontend.getListener()
			listener.setMessage(message)
			return listener
		else:
			return None
	
	def confirm (self, question):
		"""
		Ask for confirmation by user
		"""
		if self.frontend:
			return self.frontend.confirm(question)
		return True
	
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
	
	def __init__ (self, path = None):
		"""
		Set up the source object, get a list of available files
		"""
		self.files = []
		self.dirs = []
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
	def __init__ (self, connection):
		"""
		Set up the destination object
		"""
		self.connection = connection
		self.files = None
	
	def getFiles (self, listener = None):
		if not self.files:
			self.files = DestinationInfo(self.connection, listener = listener)
		return self.files.getNames()
	
	def download (self, path, fileName, listener = None):
		"""
		Download a file from the destination
		"""
		try:
			with open(fileName, "wb") as destinationFile:
				self.connection.download(path, destinationFile, listener)
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
	
	def upload (self, path, fileName = None, rename = False, listener = None):
		"""
		Upload a file to the destination
		"""
		if fileName is None:
			fileName = path
		with open(path, "rb") as sourceFile:
			self.connection.upload(sourceFile, fileName, safe = True, rename = rename, listener = listener)
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
		try:
			self.connection.remove(fileName)
		except FileNotFoundError:
			pass
	
	def rebuildFileList (self, sourceFiles, listener = None):
		"""
		Parse the list of source files into a new destination info file
		"""
		self.files.rebuild(sourceFiles, listener)
	
	def hasFile (self, fileName, checksum = None):
		"""
		Is given file name present in the destination?
		"""
		if checksum:
			return fileName in self.files and checksum == self.getHash(fileName)
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
	
	def __init__ (self, connection, objectsFileName = ".objects", listener = None):
		"""
		Try to download the destination information file from the server and parse it
		"""
		self.files = {}
		self.connection = connection
		self.objectsFileName = objectsFileName
		with io.StringIO() as objectsFile:
			try:
				connection.download(objectsFileName, objectsFile, listener = listener)
				if objectsFile.read().find(':') >= 0:
					objectsFile.seek(0)
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
	
	def rebuild (self, sourceFiles, listener = None):
		"""
		Create a new destination information file and upload it to the destination
		"""
		with io.StringIO() as objectsFile:
			objectsFile.write("\n".join(["{0}: {1}".format(fileName, fileSum) for fileName, fileSum in sourceFiles.items()]))
			self.connection.upload(objectsFile, self.objectsFileName, safe = True, listener = listener)

if __name__ == "__main__":
	from FTPConnection import FTPConnection
	from Options import *
	try:
		args = ArgumentOptionsParser().load()
		options = ConfigOptionsParser().load(args.configFile, args.section)
		options += args
		if options.quiet:
			deployer = Deployer()
		else:
			from ConsoleFrontend import ConsoleFrontend
			deployer = Deployer(ConsoleFrontend())
		if options.generateObjects:
			deployer.generateObjects(options)
		else:
			connection = FTPConnection(options.host, options.username, options.password, options.path)
			deployer.run(connection, options)
	except KeyboardInterrupt:
		deployer.interrupt()
	except ConnectionError as error:
		deployer.output(str(error), error = True)
		sys.exit(1)