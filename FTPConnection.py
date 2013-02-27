import ftplib, socket, os
from exceptions import FileNotFoundError, ConnectionError

class FTPConnection:
	"""
	An FTP object envelope
	"""
	root = "/"
	bufferSize = 4096
	
	def __init__ (self, host, username, password, root = None):
		"""
		Set up the connection
		"""
		self.host = host
		self.username = username
		self.password = password
		self.root = root
		self.connect()
	
	def connect (self):
		ftp = self.ftp = ftplib.FTP()
		try:
			ftp.connect(self.host)
		except socket.error:
			raise ConnectionError("Connecting to FTP server failed")
		try:
			ftp.login(self.username, self.password)
		except ftplib.error_perm:
			raise ConnectionError("Authentication failed")
		
		if self.root:
			if not self.root.startswith("/"):
				self.root = "/" + self.root
			self.cd(self.root)
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
	
	def ls (self, path = None):
		"""
		List a directory
		"""
		if not path:
			path = self.root
		if not path.endswith('/'):
			path += '/'
		for filename, facts in self.ftp.mlsd(path, ['type']):
			if facts['type'] == 'dir':
				yield (path + filename, True)
			if facts['type'] == 'file':
				yield (path + filename, False)
	
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
	
	def remove (self, fileName, isDir = False):
		"""
		Remove a file on the server
		"""
		if isDir:
			for name, dir in self.ls(fileName):
				self.remove(name, dir)
			self.ftp.rmd(fileName)
		else:
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
		try:
			connection = self.ftp.transfercmd("STOR {0}".format(remotePath))
			if listener:
				listener.setValue(0)
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
		except BrokenPipeError:
			self.connect()
			self.upload(stream, path, safe, rename, listener)
		
		self.ftp.voidresp()
		if safe and rename:
			self.rename(remotePath, originalPath)
		self.cdRoot()
	
	def chmod (self, path, perms):
		self.ftp.voidcmd("SITE CHMOD {0} {1}".format(perms, path))
	
	def getSafeFilename (self, filename):
		return filename + '.new'
