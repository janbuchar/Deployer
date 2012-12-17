class ConsoleFrontend:
	noticeColor = 36
	errorColor = 31
	
	def getListener (self):
		return Progressbar()
	
	def output (self, message, important = False, error = False, breakLine = True):
		stream = sys.stdout if not error else sys.stderr
		if error:
			message = "\033[00;{0}m{1}\033[0;0m".format(self.errorColor, "Error: ") + message
		elif important:
			message = "\033[00;{0}m{1}\033[0;0m".format(self.noticeColor, message)
		if breakLine:
			message = message + "\n"
		stream.write(message)
			
	def confirm (self, question, default = True):
		answer = input(question + " [Y/n] ")
		if not answer:
				return default
		if answer[0].lower() != "y":
			return False
		return True

import sys, os

class Progressbar:
	"""
	A class that manages progressbar rendering
	"""
	
	def __init__ (self, message = None):
		"""
		Set up the progressbar
		"""
		self.message = message
		self.columns = self.getConsoleWidth()
		self.messageLength = self.columns // 2
	
	def setMessage (self, message):
		self.message = message
	
	def getConsoleWidth (self):
		"""
		Get the width of the terminal window
		"""
		rows, columns = os.popen('stty size', 'r').read().split()
		return int(columns)
	
	def truncateTitle (self, value):
		"""
		Shorten the progressbar's message so that it doesn't mess anything up
		"""
		if len(value) > self.messageLength:
			value = "..." + value[-(self.messageLength - 3) : ]
		else:
			value = value + (" " * (self.messageLength - len(value)))
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
		barLength = self.columns - self.messageLength - 4 - 2 - 2 # Percents, empty spaces and brackets
		bar = str()
		try:
			progress = self.progress
		except AttributeError: # If self.progress is not set, it means the rendering had finished before setting any value
			progress = 100
		for i in range(1, barLength):
			bar += "#" if (i / (barLength / float(100))) < progress else "-"
		percent = ("{0:3}".format(progress)) + "%"
		sys.stdout.write("{0} [{1}] {2}".format(self.truncateTitle(self.message), bar, percent))
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
