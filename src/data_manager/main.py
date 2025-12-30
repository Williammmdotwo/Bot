# Fix relative imports for direct execution
try:
    from ..data_manager.clients.websocket_client import OKXWebSocketClient
    from ..data_manager.clients.rest_client import RESTClient
    from ..data_manager.core.technical_indicators import TechnicalIndicators
    from ..utils.environment_utils import get_data_source_config, get_data_source_label, is_using_mock_data
except ImportError:
    from src.data_manager.clients.websocket_client import OKXWebSocketClient
    from src.data_manager.clients.rest_client import RESTClient
    from src.data_manager.core.technical_indicators import TechnicalIndicators
    from src.utils.environment_utils import get_data_source_config, get_data_source_label, is_using_mock_data
