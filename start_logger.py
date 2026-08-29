
import os 
import sys
import logging
import pathlib 

from atexit import register
from datetime import datetime
from typing import Callable
# ==============================================================================
class Logger:
  '''
  A crash-resilient logger using Singleton design that maintains consistent
  configuration across modules, ensuring logs are captured even during crashes.

  # Example
  #
  #  In your main.py
    
    from log import Logger
    
    logfile_name = basename(__file__).split('.')[0]
    Logger.configure( name_ = logfile_name, level_ = log_level_)
    
    def main():
      log = logger.get_logger()
      log.info( "This message gets queued" )

  # In module:
  
    from lib.log import Logger
    
    def some_function( ):
      
      log = logger.get_logger( )
      log.info( "Function called" )
      
      log.debug( "Debug info" )
      
      try:
        result = 1 / 0
        
      except Exception as e:
        log.debug( f"Error occurred {e}" )
        Logger.flush_all( )
        raise
  '''

  _loggers = {}
  _configured = False
  _console_level = logging.DEBUG
  _file_handler = None
  _global_logger = None
  # ============================================================================
  @classmethod
  def configure( cls, level_=logging.INFO, name_=f"default" ):
  
    '''
    Explicitly configure the logger. Call this once at program startup.
    Creates the log file immediately to ensure crash logs are captured.
    '''
  
    if cls._configured:
      return cls._global_logger

    _logfile_folder = "./var/log/"
    _logfile = f"{_logfile_folder}_{name_}_{datetime.today( ).strftime( '%Y-%m-%d_-_%H-%M-%S' )}.log"

    cls._logfile = _logfile
    cls._console_level = level_

    log_path = pathlib.Path( cls._logfile )

    if not log_path.parent.exists( ):
    
      try:
        os.makedirs( log_path.parent, exist_ok = True )
        
      except PermissionError as _:
        print( f"WARNING {_}: Permission denied creating {log_path.parent}, logs file may fail" )

    try:
      with open( cls._logfile, 'a', encoding='utf-8' ) as _file:
        _file.write( f"=== Log initialized at {datetime.now( )} ===\n" )

    except Exception as e:
      print( f"WARNING: LOG FILE COULD NOT BE CREATED: {e}" )

    cls._configured = True

    # Create the global LOG instance
    cls._global_logger = cls._create_logger( "GLOBAL" )

    register( cls._cleanup )

    return cls._global_logger
  # ============================================================================
  @classmethod
  def _create_logger(
    cls,
    name_ : str,
    log_format_ : str = "%(asctime)s | %(name)s | %(funcName)s.%(lineno)d | %(levelname)s | %(message)s",
    date_format_ : str = "%Y-%m-%d %H:%M:%S",
  ) -> logging.Logger:
    
    '''
    Internal method for logger instance.
    '''

    if name_ in cls._loggers:
      return cls._loggers[ name_ ]

    logger = logging.getLogger( name_ )
    logger.setLevel( logging.DEBUG )

    logger.handlers.clear( )

    formatter = logging.Formatter(
      fmt = log_format_,
      datefmt = date_format_
    )

    try:
      file_handler = logging.FileHandler(
        cls._logfile,
        mode = "a",
        encoding = "utf-8"
      )
      
      # Debug is default
      file_handler.setLevel( logging.DEBUG )
      file_handler.setFormatter( formatter )

      if cls._file_handler is None:
        cls._file_handler = file_handler

      logger.addHandler( file_handler )

    except Exception as e:
      print( f"Warning: Cannot create file handler: {e}" )

    cli_handler = logging.StreamHandler( sys.stdout )
    cli_handler.setLevel( cls._console_level )
    cli_handler.setFormatter( formatter )
    logger.addHandler( cli_handler )

    cls._loggers[ name_ ] = logger

    return logger
  
  # ============================================================================
  @classmethod
  def get_logger( cls, name_=None ) -> logging.Logger:
    
    '''
    Returns a configured logger with immediate disk flushing.
    If not configured yet, returns the global logger which will be properly
    initialized when configure() is called.
    '''

    # If asking for global or not configured logger, return global logger
    
    if not cls._configured:
      return _Lazy_Logger( )

    if not name_:
      frame = sys._getframe( 1 )
      filepath = pathlib.Path( frame.f_code.co_filename )
      name_ = filepath.stem

    return cls._create_logger( name_ )
  # ============================================================================
  @classmethod
  def get_global( cls ) -> logging.Logger:
    '''
    Returns the global LOG instance. Use this for the global LOG object.
    '''
    
    if not cls._configured:
      return _Lazy_Logger( )
    
    return cls._global_logger
  # ============================================================================
  @classmethod
  def _cleanup( cls ) -> None:
    '''Ensure all handlers are properly flushed and closed.'''
    for logger in cls._loggers.values( ):
      for handler in logger.handlers:
        handler.flush( )
        handler.close( )
        
  # ============================================================================
  @classmethod
  def flush_all( cls ) -> None:
    '''Manually flush all log handlers. Call this before risky operations.'''
    for logger in cls._loggers.values( ):
      for handler in logger.handlers:
        handler.flush( )
        
# ==============================================================================
class _Lazy_Logger( object ):
  
  '''
  Proxy logger that queues messages until Logger.configure() is called.
  This allows modules to create log = get_logger() at import time.
  '''
  
  # ! Why standard python logging does not have this behaviour by default is a mistery!
  
  # ============================================================================
  def __init__( self ):
    self._queue = []
    self._real_logger = None
  
  # ============================================================================
  def _get_real_logger( self ) -> logging.Logger | None:
    if self._real_logger is None:
      if Logger._configured:
        self._real_logger = Logger.get_global( )
        for method, args, kwargs in self._queue:
          getattr( self._real_logger, method )( *args, **kwargs )
        self._queue.clear( )
    return self._real_logger
  
  # ============================================================================
  def _log_method( self, method_name ) -> Callable:
  
    def method( *args, **kwargs ):
  
      real = self._get_real_logger( )
      if real:
        return getattr( real, method_name )( *args, **kwargs )
      else:
        self._queue.append( ( method_name, args, kwargs ) )
    return method
  
  # ============================================================================
  def __getattr__( self, name ) -> Callable:
    
    return self._log_method( name )

# ==============================================================================
class Flushing_File_Handler( logging.FileHandler ):
  '''
  A file handler that flushes after every log entry.
  Use this for maximum crash resistance at the cost of performance.
  Custom logging handler that auto-flushes on every write (use for critical apps)
  '''
  
  def emit( self, record ) -> None:
    super( ).emit( record )
    self.flush( )
    
# ==============================================================================
def get_logger( ) -> logging.Logger:
  '''
  Returns the global LOG instance. Import and call this in every module.
  '''
  return Logger.get_global( )
# ==============================================================================
