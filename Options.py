class Options:
	dry = False
	configFile = "deploy.json"
	logFile = "deployer.log"
	section = None
	confirm = True
	quiet = False
	log = True
	host = None
	username = None
	password = None
	path = None
	ignore = None
	keep = None
	generateObjects = False
	
	def __iadd__ (self, options):
		for option, value in options.__dict__.items():
			if value != getattr(type(self), option):
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
		parser.add_argument("-g", "--generate-objects", dest = "generateObjects", action = "store_true", help = "Generate a local copy of the objects file")
		parser.add_argument("-c", "--config-file", dest = "configFile", help = "The name of the (optional) configuration file (defaults to {0})".format(options.configFile))
		parser.add_argument("-s", "--section", dest = "section", help = "The section of a configuration file to read from")
		parser.add_argument("-y", "--yes", dest = "confirm", action = "store_false", help = "Apply changes without confirmation (Use reasonably)")
		parser.add_argument("-q", "--quiet", dest = "quiet", action = "store_true", help = "Process the script quietly, without any output")
		parser.add_argument("-l", "--no-logging", dest = "log", action = "store_true", help = "Don't log anything on the server")
		parser.add_argument("-a", "--address", dest = "host", help = "FTP server address")
		parser.add_argument("-u", "--username", dest = "username", help = "FTP server username")
		parser.add_argument("-p", "--password", dest = "password", help = "FTP server password")
		parser.add_argument("-i", "--ignore", dest = "ignore", nargs = "+", action = "append", help = "Ignored files/directories")
		parser.add_argument("--path", dest = "path", help = "Path to the root of the application on the FTP server")
		for key, value in parser.parse_args().__dict__.items():
			if value:
				options[key] = value
		return options

class ConfigOptionsParser:
	commonSection = "common"
	
	def load (self, configFile, configSection = None):
		import json
		options = Options()
		with open(configFile, 'r') as data:
			config = json.loads(data.read())
			for section in (self.commonSection, configSection):
				try:
					for option, value in config[section].items():
						options[option] = value
				except KeyError:
					pass
		return options
