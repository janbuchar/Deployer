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

class FileNotFoundError (Exception):
	"""
	An error raised if a file was not found on the server
	"""

class ConnectionError (Exception):
	"""
	An error raised if there is a problem with the connection
	"""