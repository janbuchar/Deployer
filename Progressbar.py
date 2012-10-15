import sys, os

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
