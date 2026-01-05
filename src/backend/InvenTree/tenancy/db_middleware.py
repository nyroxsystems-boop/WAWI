"""Database connection health middleware."""
import logging
from django.db import connection, OperationalError, close_old_connections
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('inventree.db')


class DatabaseHealthMiddleware(MiddlewareMixin):
    """Ensure database connections are healthy before processing requests."""
    
    def process_request(self, request):
        """Close stale connections before first DB query."""
        try:
            close_old_connections()
        except Exception as e:
            logger.warning(f"Error closing old connections: {e}")
        return None
    
    def process_exception(self, request, exception):
        """Log database connection errors with full context."""
        if isinstance(exception, OperationalError):
            error_msg = str(exception).lower()
            
            # Detect SSL/connection errors
            if any(kw in error_msg for kw in ['ssl', 'eof', 'connection', 'closed', 'decryption', 'bad record mac']):
                db_cfg = connection.settings_dict
                logger.error(
                    "PostgreSQL connection error",
                    extra={
                        'error_type': 'SSL/Connection',
                        'error_message': str(exception),
                        'db_host': db_cfg.get('HOST'),
                        'db_port': db_cfg.get('PORT'),
                        'db_name': db_cfg.get('NAME'),
                        'conn_max_age': db_cfg.get('CONN_MAX_AGE'),
                        'sslmode': db_cfg.get('OPTIONS', {}).get('sslmode'),
                        'request_path': request.path,
                        'request_method': request.method,
                    }
                )
                
                # Force close the bad connection
                try:
                    connection.close()
                except Exception:
                    pass
        
        return None  # Let Django's exception handler take over
