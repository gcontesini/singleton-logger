
import os 
import sys
import logging
import pathlib 
import types
import typing

from atexit import register
from datetime import datetime
# ==============================================================================
class _Lazy_Logger( object ):
  
  '''
  Proxy logger that queues messages until Logger.configure() is called.
  This allows modules to create log = get_logger() at import time.
  '''
  
  # ! Why standard python logging does not have this behaviour by default instead a global logger.
  
  # ============================================================================
  def __init__( self ) -> None:
    self._queue : list = []
    self._real_logger : logging.Logger | _Lazy_Logger | None = None
  
  # ============================================================================
  def _get_real_logger( self ):
    
    if self._real_logger is None:
      
      if Logger._configured:
        
        self._real_logger : logging.Logger | _Lazy_Logger | None = Logger.get_global( )
      
        for method, args, kwargs in self._queue:
      
          getattr( self._real_logger, method )( *args, **kwargs )
      
        self._queue.clear( )
    
    return self._real_logger
  
  # ============================================================================
  def _log_method( self, method_name ) -> typing.Callable:
  
    def method( *args, **kwargs ):
  
      real : logging.Logger | None | _Lazy_Logger = self._get_real_logger( )
      
      if real:
        return getattr( real, method_name )( *args, **kwargs )
      
      else:
        self._queue.append( ( method_name, args, kwargs ) )
        
    return method
  
  # ============================================================================
  def __getattr__( self, name ) -> typing.Callable:
    
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
def get_logger( ) -> logging.Logger | _Lazy_Logger | None:
  '''
  Returns the global LOG instance. Import and call this in every module.
  '''
  
  return Logger.get_global( )
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

  _loggers : dict = {}
  _configured : bool = False
  _console_level : int = logging.DEBUG
  _file_handler : logging.FileHandler | None = None
  _global_logger : logging.Logger | None = None
  # ============================================================================
  @classmethod
  def configure(
    cls,
    name_ : str = "default",
    level_ : int = logging.INFO,
    var_log_dir_path_ : str = "./var/log/"
  ) -> None | logging.Logger:
  
    '''
    Explicitly configure the logger. Call this once at program startup.
    Creates the log file immediately to ensure crash logs are captured.
    '''
  
    if cls._configured:
      return cls._global_logger

    _logfile_folder = var_log_dir_path_
    _logfile_format : str = f"{_logfile_folder}_{name_}_{datetime.today( ).strftime( '%Y-%m-%d_-_%H-%M-%S' )}.log"

    cls._logfile = _logfile_format
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
    name_ : str = "default",
    log_format_ : str = "%(asctime)s | %(name)s | %(funcName)s.%(lineno)d | %(levelname)s | %(message)s",
    date_format_ : str = "%Y-%m-%d %H:%M:%S",
  ) -> logging.Logger:
    
    '''
    Internal method for logger instance.
    '''

    if name_ in cls._loggers:
      return cls._loggers[ name_ ]

    logger : logging.Logger = logging.getLogger( name_ )
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
  def get_logger(
    cls,
    name_ : str = "default",
  ) -> _Lazy_Logger | logging.Logger:
    
    '''
    Returns a configured logger with immediate disk flushing.
    If not configured yet, returns the global logger which will be properly
    initialized when configure() is called.
    '''
    # If asking for global or not configured logger, return global logger
    if not cls._configured:
      return _Lazy_Logger( )
    
    _name : str = name_
    if name_ == "default" :
      _frame : types.FrameType= sys._getframe( 1 )
      _filepath : pathlib.Path = pathlib.Path( _frame.f_code.co_filename )
      _name = _filepath.stem

    return cls._create_logger( _name )
  # ============================================================================
  @classmethod
  def get_global( cls ) -> _Lazy_Logger | logging.Logger | None:
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
